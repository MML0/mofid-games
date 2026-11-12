"""The LiDAR input: the OSC link, the angle mapping, absent players, and the real tracker on its sample recording."""

import math
import socket
import struct
import time
from pathlib import Path

import pytest

from conftest import free_udp_port, playing, wait_for
from land_hockey.inputs import osc
from land_hockey.inputs.lidar import LidarAdapter, tracker_command

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "LIdar" / "samples" / "session_2players.pkl"


def paddle(player, angle, active=1, conf=1.0):
    return osc.encode("/paddle", [player, 100.0, 200.0, float(angle), active, float(conf)])


@pytest.fixture
def lidar(cfg):
    cfg.set("input.lidar.port", free_udp_port())
    a = LidarAdapter(cfg)
    yield a
    a.stop()


def test_osc_messages_and_bundles_decode():
    assert osc.decode(paddle(2, 45.5, 1, 0.5)) == [("/paddle", [2, 100.0, 200.0, 45.5, 1, 0.5])]
    two = [paddle(1, 10), osc.encode("/foot", [3, 1.0, 2.0, 1])]
    bundle = b"#bundle\0" + b"\0" * 8 + b"".join(struct.pack(">i", len(m)) + m for m in two)
    assert [a for a, _ in osc.decode(bundle)] == ["/paddle", "/foot"]
    assert osc.decode(osc.encode("/x", ["héllo", True, 7])) == [("/x", ["héllo", True, 7])]


@pytest.mark.parametrize("junk", [b"", b"\0\0\0\0", b"paddle", b"/paddle\0,iffffif\0\0\0\0", b"#bundle\0" + b"\xff" * 12,
                                  b"/paddle\0,q\0\0", bytes(range(256))])
def test_garbage_is_dropped_and_never_raises(lidar, junk):
    lidar.feed(junk, 0.0)
    assert lidar.latest == {}


def test_the_paddle_goes_to_the_same_angle_on_the_game_circle(lidar, engine):
    playing(engine)
    lidar.feed(paddle(1, 180.0), 1.0)  # straight left: the middle of player 1's arc
    lidar.feed(paddle(2, 0.0), 1.0)  # straight right: the middle of player 2's
    s1, s2 = lidar.sample(0, 1.0, 1 / 60, engine), lidar.sample(1, 1.0, 1 / 60, engine)
    assert s1.present and s2.present
    assert s1.u == pytest.approx(0.5, abs=0.01) and s2.u == pytest.approx(0.5, abs=0.01)
    w = engine.paddle_width(0)
    for ang in (150.0, 200.0):
        lidar.feed(paddle(1, ang), 1.0)
        u = lidar.sample(0, 1.0, 1 / 60, engine).u
        assert engine.geom.u_to_theta(0, u, w) == pytest.approx(ang, abs=0.5)  # under the player's feet
    lidar.feed(paddle(1, 95.0), 1.0)  # in the top wall's span: held at the nearest end
    assert lidar.sample(0, 1.0, 1 / 60, engine).u in (0.0, 1.0)


def test_mirror_offset_and_swap(lidar, engine, cfg):
    playing(engine)
    cfg.set("input.lidar.mirror_x", True)
    assert lidar.game_angle(0.0) == pytest.approx(180.0)
    cfg.set("input.lidar.mirror_x", False)
    cfg.set("input.lidar.mirror_y", True)
    assert lidar.game_angle(30.0) == pytest.approx(330.0)
    cfg.set("input.lidar.mirror_y", False)
    cfg.set("input.lidar.angle_offset_deg", 90.0)
    assert lidar.game_angle(90.0) == pytest.approx(180.0)
    cfg.set("input.lidar.angle_offset_deg", 0.0)
    cfg.set("input.lidar.swap_players", True)
    lidar.feed(paddle(2, 180.0), 1.0)
    assert lidar.sample(0, 1.0, 1 / 60, engine).present  # tracker player 2 now drives game player 1
    assert not lidar.sample(1, 1.0, 1 / 60, engine).present


def test_nobody_there_silence_and_odd_values_read_as_absent(lidar, engine):
    playing(engine)
    lidar.feed(paddle(1, 180.0, active=0), 1.0)
    assert not lidar.sample(0, 1.0, 1 / 60, engine).present
    lidar.feed(paddle(1, 180.0), 1.0)
    assert lidar.sample(0, 1.2, 1 / 60, engine).present
    assert not lidar.sample(0, 1.0 + lidar.cfg["input.lidar.timeout_s"] + 0.01, 1 / 60, engine).present
    lidar.feed(paddle(1, float("nan")), 2.0)
    lidar.feed(paddle(9, 180.0), 2.0)
    lidar.feed(osc.encode("/paddle", [1, 0.0, 0.0]), 2.0)
    assert lidar.latest[1][0] == 1.0  # none of those replaced the good message
    lidar.feed(paddle(1, 180.0, conf=7.0), 3.0)
    assert lidar.sample(0, 3.0, 1 / 60, engine).confidence == 1.0


def test_it_listens_on_its_port(lidar, engine):
    playing(engine)
    out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        def got():
            out.sendto(paddle(1, 170.0), ("127.0.0.1", lidar.cfg["input.lidar.port"]))
            lidar.update(time.perf_counter(), 1 / 60, engine)
            return lidar.sample(0, time.perf_counter(), 1 / 60, engine).present
        assert wait_for(got)
    finally:
        out.close()


def test_the_tracker_command_follows_the_settings(cfg):
    cfg.set("input.lidar.serial_port", "COM9")
    cmd = tracker_command(cfg)
    assert cmd[1].endswith("lidar_tracker.py") and "--headless" in cmd
    assert cmd[cmd.index("--port") + 1] == "COM9" and "--replay" not in cmd
    assert Path(cmd[cmd.index("--settings") + 1]) == ROOT / "LIdar" / "game_settings.json"
    cfg.set("input.lidar.replay_file", "LIdar/samples/session_2players.pkl")
    cfg.set("input.lidar.tracker_window", "setup")
    cmd = tracker_command(cfg)
    assert "--port" not in cmd and "--headless" not in cmd and "--loop" in cmd
    assert int(cmd[cmd.index("--parent") + 1]) > 0


@pytest.mark.real_tracker
@pytest.mark.skipif(not SAMPLE.exists(), reason="no sample recording")
def test_the_real_tracker_drives_the_paddles_from_its_recording(cfg, engine):
    """The game starts the real tracker on the recorded session (10 s empty-floor scan, then a player walking in the
    left half) and its paddle walks along player 1's arc: never out of range, never jumping."""
    cfg.set("input.lidar.port", free_udp_port())
    cfg.set("input.lidar.replay_file", str(SAMPLE))
    cfg.set("input.lidar.settings_file", str(SAMPLE.with_suffix(".settings.json")))
    playing(engine)
    a = LidarAdapter(cfg)
    try:
        assert a.tracker_running
        us, start, last = [], time.perf_counter(), None
        while time.perf_counter() - start < 60 and (len(us) < 240 or max(us) - min(us) < 0.15):
            now = time.perf_counter()
            a.update(now, 1 / 60, engine)
            s = a.sample(0, now, 1 / 60, engine)
            if s.present:
                assert 0.0 <= s.u <= 1.0 and math.isfinite(s.u)
                if last is not None:
                    assert abs(s.u - last) < 0.2  # smooth: no jumps from frame to frame
                us.append(s.u)
                last = s.u
            time.sleep(1 / 60)
        assert a.packets > 0, "no OSC from the tracker: see logs/lidar_tracker.log"
        assert len(us) >= 240 and max(us) - min(us) >= 0.15, "player 1 never walked along the arc"
    finally:
        tracker = a.tracker
        a.stop()
    assert tracker.poll() is not None  # stopping the game's input stops the tracker

def test_a_lidar_paddle_follows_at_once_but_others_keep_the_slide_limit(lidar, engine, cfg):
    """The tracker already smooths and teleports on a jump, so the game adds no speed limit of its own (a switch)."""
    from land_hockey.inputs.base import PlayerSample

    playing(engine)
    dt = 1 / 60
    p = engine.paddles[0]

    def go(u, instant):
        engine.step(dt, {0: PlayerSample(True, u, 1.0, 0.0, None, "test", instant)})
        return p.theta

    go(0.05, True)
    lo, hi = engine.geom.paddle_range(0, engine.paddle_width(0))
    assert go(0.95, True) == pytest.approx(lo + (hi - lo) * 0.95)  # the whole arc in one frame
    limit = cfg["paddles.p1.max_speed_deg_s"] * dt
    before = p.theta
    assert abs(go(0.05, False) - before) <= limit + 1e-9  # keyboard, AI, ...: still slide
    lidar.feed(paddle(1, 180.0), 1.0)
    assert lidar.sample(0, 1.0, dt, engine).instant
    cfg.set("input.lidar.instant_paddle", False)
    assert not lidar.sample(0, 1.0, dt, engine).instant  # switched off: the old slide
