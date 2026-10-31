"""The UDP contract a tracker must speak (see market_hockey/inputs/network.py), tested end to end.

The scan simulator below stands in for a 360° LiDAR at the center of the floor: it produces polar returns from two
pairs of feet, clusters them into one point per person, and sends them to the game the way a real tracker will.
"""

import json
import math
import random
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import free_udp_port, playing
from market_hockey.inputs.base import PlayerSample
from market_hockey.inputs.manager import InputManager
from market_hockey.inputs.network import NetworkAdapter


@pytest.fixture
def net(cfg):
    cfg.set("input.network.port", free_udp_port())
    a = NetworkAdapter(cfg)
    assert a.sock is not None
    yield a
    a.stop()


@pytest.fixture
def sender():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    yield s
    s.close()


def send(sender, adapter, payload):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    sender.sendto(data, ("127.0.0.1", adapter.cfg["input.network.port"]))


def pump(adapter, engine, now=1.0):
    """UDP on loopback is fast but not instant: wait for the datagram to arrive."""
    before = adapter.messages
    for _ in range(100):
        adapter.update(now, 1 / 60, engine)
        if adapter.messages > before:
            return True
        time.sleep(0.002)
    return False


def rim_point(angle_deg, r=0.95):
    a = math.radians(angle_deg)
    return r * math.cos(a), r * math.sin(a)


def lidar_scan(people, rng, noise=0.004, rays=720):
    """Polar returns (angle_deg, range) in the sensor's frame: an arc of hits per foot, plus a few stray points."""
    hits = []
    for (x, y) in people:
        for side in (-1, 1):
            fx, fy = x + side * 0.03 * -y, y + side * 0.03 * x  # two feet, side by side
            r = math.hypot(fx, fy)
            center = math.degrees(math.atan2(fy, fx))
            half = math.degrees(math.atan2(0.025, r))
            for k in range(rays):
                ang = k * 360 / rays - 180
                if abs((ang - center + 180) % 360 - 180) <= half:
                    hits.append((ang, r + rng.gauss(0, noise)))
    hits += [(rng.uniform(-180, 180), rng.uniform(1.2, 3.0)) for _ in range(5)]  # the walls of the hall
    return hits


def cluster(hits, max_range=1.1, gap=0.15):
    """The job of the tracker: keep the floor, join nearby returns, one centroid per person."""
    pts = sorted((math.radians(a), r) for a, r in hits if r <= max_range)
    groups = []
    for a, r in pts:
        x, y = r * math.cos(a), r * math.sin(a)
        for g in groups:
            if math.hypot(x - g[-1][0], y - g[-1][1]) < gap:
                g.append((x, y))
                break
        else:
            groups.append([(x, y)])
    return [{"x": sum(p[0] for p in g) / len(g), "y": sum(p[1] for p in g) / len(g), "conf": 0.9} for g in groups]


# ---------------------------------------------------------------- end to end
def test_players_feet_move_the_paddles_over_real_udp(cfg, engine, sender):
    """A full pass: scan -> clusters -> UDP -> adapter -> filters -> engine, with both players walking the rim."""
    cfg.set("input.network.port", free_udp_port())
    cfg.set("input.p1.source", "network")
    cfg.set("input.p2.source", "network")
    rng = random.Random(5)
    m = InputManager(cfg)
    playing(engine)
    try:
        m.poll(0.0, 1 / 60, engine)  # opens the socket
        now = 0.0
        for k in range(180):
            now = k / 60
            a1 = 180 + 30 * math.sin(k / 40)
            a2 = 30 * math.cos(k / 50)
            blobs = cluster(lidar_scan([rim_point(a1), rim_point(a2)], rng))
            sender.sendto(json.dumps({"type": "blobs", "blobs": blobs}).encode(), ("127.0.0.1", cfg["input.network.port"]))
            time.sleep(0.001)
            samples, presence = m.poll(now, 1 / 60, engine)
            engine.step(1 / 60, samples, presence)
        assert presence == [True, True]
        # the paddles track each person's angle (the filter adds some lag, hence the tolerance)
        p1, p2 = engine.paddles
        assert abs((p1.theta - a1 + 180) % 360 - 180) < 12, (p1.theta, a1)
        assert abs((p2.theta - a2 + 180) % 360 - 180) < 12, (p2.theta, a2)
    finally:
        m.close()


def test_sensor_jitter_does_not_shake_the_paddle(cfg, engine):
    """Someone standing still with ±1 cm of sensor noise: the paddle must look calm."""
    cfg.set("input.network.port", free_udp_port())
    cfg.set("input.p1.source", "network")
    cfg.set("input.p2.source", "network")
    rng = random.Random(9)
    m = InputManager(cfg)
    try:
        a = m.adapter("network")
        us = []
        for k in range(240):
            now = k / 60
            x, y = rim_point(180 + rng.gauss(0, 0.6))
            a.feed({"type": "tracking", "players": [{"id": "p1", "x": x, "y": y}]}, now)
            samples, _ = m.poll(now, 1 / 60, engine)
            us.append(samples[0].u)
        settled = us[60:]
        assert max(settled) - min(settled) < 0.03
    finally:
        m.close()


def test_a_tracker_dropout_holds_then_reports_absent(cfg, engine):
    cfg.set("input.network.port", free_udp_port())
    cfg.set("input.p1.source", "network")
    cfg.set("input.p2.source", "network")
    m = InputManager(cfg)
    try:
        a = m.adapter("network")
        x, y = rim_point(180)
        for k in range(30):
            a.feed({"type": "tracking", "players": [{"id": "p1", "x": x, "y": y}]}, k / 60)
            samples, presence = m.poll(k / 60, 1 / 60, engine)
        assert presence[0] and samples[0].u is not None
        samples, presence = m.poll(1.5, 1 / 60, engine)  # messages stopped: past the timeout, within the hold
        assert presence[0] and samples[0].u is None
        samples, presence = m.poll(1.5 + cfg["input.filters.absent_timeout_s"] + 1, 1 / 60, engine)
        assert not presence[0]
    finally:
        m.close()


# ---------------------------------------------------------------- calibration: the sensor is never mounted square
@pytest.mark.parametrize("mount_deg", [-120, -37, 0, 45, 90, 180])
def test_rotation_calibration_undoes_the_sensor_mount(cfg, net, engine, mount_deg):
    cfg.set("input.network.rotation_deg", mount_deg)
    a = math.radians(-mount_deg)
    x, y = 0.95 * math.cos(a), 0.95 * math.sin(a)  # straight toward P2's goal center in the real world
    net.feed({"type": "tracking", "players": [{"id": "p2", "x": x, "y": y}]}, now=1.0)
    assert net.sample(1, 1.0, 0, engine).u == pytest.approx(0.5, abs=0.02)


def test_scale_offset_and_flip_calibration(cfg, net):
    cfg.set("input.network.scale_x", 2.0)
    cfg.set("input.network.scale_y", 0.5)
    cfg.set("input.network.offset_x", 0.1)
    cfg.set("input.network.offset_y", -0.1)
    assert net.calibrate(0.2, 0.4) == pytest.approx((0.5, 0.1))
    cfg.set("input.network.flip_y", True)
    assert net.calibrate(0.2, 0.4) == pytest.approx((0.5, -0.3))


# ---------------------------------------------------------------- blob assignment
def test_blobs_are_assigned_by_goal_arc_not_by_order(net, engine):
    x1, y1 = rim_point(180)
    x2, y2 = rim_point(0)
    net.feed({"type": "blobs", "blobs": [{"x": x2, "y": y2}, {"x": x1, "y": y1}]}, now=1.0)
    net.update(1.0, 0, engine)
    assert net.sample(0, 1.0, 0, engine).xy == pytest.approx((x1, y1))
    assert net.sample(1, 1.0, 0, engine).xy == pytest.approx((x2, y2))


def test_people_beside_the_walls_do_not_steal_a_paddle(net, engine):
    x, y = rim_point(90)  # standing at the top wall
    net.feed({"type": "blobs", "blobs": [{"x": x, "y": y}]}, now=1.0)
    net.update(1.0, 0, engine)
    assert not net.sample(0, 1.0, 0, engine).present and not net.sample(1, 1.0, 0, engine).present


def test_the_person_nearest_the_rim_plays(net, engine):
    near, far = rim_point(180, 0.95), rim_point(180, 0.4)
    net.feed({"type": "blobs", "blobs": [{"x": far[0], "y": far[1]}, {"x": near[0], "y": near[1]}]}, now=1.0)
    net.update(1.0, 0, engine)
    assert net.sample(0, 1.0, 0, engine).xy == pytest.approx(near)


def test_u_shortcut_skips_the_geometry(net, engine):
    net.feed({"type": "tracking", "players": [{"id": "1", "u": 0.25}, {"id": "player2", "u": 0.75}]}, now=1.0)
    assert net.sample(0, 1.0, 0, engine).u == 0.25
    assert net.sample(1, 1.0, 0, engine).u == 0.75


def test_unknown_player_ids_are_ignored(net, engine):
    net.feed({"type": "tracking", "players": [{"id": "visitor", "x": 0.9, "y": 0}]}, now=1.0)
    assert net.latest == {}


def test_without_an_engine_a_position_cannot_be_mapped(net):
    net.feed({"type": "tracking", "players": [{"id": "p1", "x": -0.9, "y": 0}]}, now=1.0)
    s = net.sample(0, 1.0, 0, None)
    assert not s.present and s.xy == (-0.9, 0.0)


def test_low_confidence_is_gated_by_the_filter(cfg, engine):
    cfg.set("input.network.port", free_udp_port())
    cfg.set("input.p1.source", "network")
    cfg.set("input.p2.source", "network")
    m = InputManager(cfg)
    try:
        x, y = rim_point(180)
        m.adapter("network").feed({"type": "tracking", "players": [{"id": "p1", "x": x, "y": y, "conf": 0.1}]}, 0.0)
        samples, _ = m.poll(0.0, 1 / 60, engine)
        assert samples[0].u is None
    finally:
        m.close()


# ---------------------------------------------------------------- hostile input: the show must go on
BAD_PACKETS = [
    b"",
    b"not json",
    b"\xff\xfe\x00garbage",
    b"[1, 2, 3]",
    b"42",
    b"null",
    b'{"type": "tracking"}',
    b'{"type": "tracking", "players": 5}',
    b'{"type": "tracking", "players": [5, "x", null]}',
    b'{"type": "tracking", "players": [{"id": "p1", "x": "left", "y": 0}]}',
    b'{"type": "tracking", "players": [{"id": "p1", "x": null, "y": null}]}',
    b'{"type": "tracking", "players": [{"id": "p1", "x": NaN, "y": 0}]}',
    b'{"type": "tracking", "players": [{"id": "p1", "x": Infinity, "y": -Infinity}]}',
    b'{"type": "tracking", "players": [{"id": "p1", "x": 1e999, "y": 0}]}',
    b'{"type": "tracking", "players": [{"id": "p1", "x": 0.9, "y": 0, "conf": "high"}]}',
    b'{"type": "tracking", "players": [{"id": "p1", "x": 0.9, "y": 0, "conf": NaN}]}',
    b'{"type": "tracking", "players": [{"id": "p1", "u": "middle"}]}',
    b'{"type": "tracking", "players": [{"id": "p1", "u": NaN}]}',
    b'{"type": "tracking", "players": [{"id": "p1", "u": 99}]}',
    b'{"type": "tracking", "players": [{"id": ["p1"], "x": 0, "y": 0}]}',
    b'{"type": "blobs"}',
    b'{"type": "blobs", "blobs": "many"}',
    b'{"type": "blobs", "blobs": [1, null, {"x": "a"}, {"x": NaN, "y": 1}]}',
    b'{"type": 7}',
    b'{"nothing": "useful"}',
]


@pytest.mark.parametrize("packet", BAD_PACKETS, ids=[repr(p)[:60] for p in BAD_PACKETS])
def test_a_bad_packet_never_crashes_or_corrupts_the_game(cfg, net, engine, sender, packet):
    playing(engine)
    send(sender, net, packet)
    time.sleep(0.005)
    for k in range(3):
        net.update(1.0, 1 / 60, engine)
        for idx in (0, 1):
            s = net.sample(idx, 1.0, 1 / 60, engine)
            assert isinstance(s, PlayerSample)
            assert s.u is None or (math.isfinite(s.u) and 0.0 <= s.u <= 1.0), s
            assert math.isfinite(s.confidence)
        engine.step(1 / 60, {i: net.sample(i, 1.0, 1 / 60, engine) for i in (0, 1)}, [True, True])
    for p in engine.paddles:
        assert math.isfinite(p.theta)


def test_good_data_still_works_after_garbage(net, engine, sender):
    send(sender, net, b"garbage")
    x, y = rim_point(180)
    send(sender, net, {"type": "tracking", "players": [{"id": "p1", "x": x, "y": y}]})
    assert pump(net, engine)
    assert net.sample(0, 1.0, 0, engine).present


def test_a_flood_of_packets_cannot_stall_a_frame(net, engine, sender):
    x, y = rim_point(180)
    msg = json.dumps({"type": "tracking", "players": [{"id": "p1", "x": x, "y": y}]}).encode()
    for _ in range(1000):
        sender.sendto(msg, ("127.0.0.1", net.cfg["input.network.port"]))
    time.sleep(0.02)
    net.update(1.0, 1 / 60, engine)
    assert 0 < net.messages <= 200  # one frame reads a bounded number; the rest wait for the next frames


def test_port_in_use_leaves_the_game_running(cfg, engine, monkeypatch):
    import market_hockey.inputs.network as network

    class NoBind(socket.socket):
        def bind(self, addr):
            raise OSError("address already in use")

    monkeypatch.setattr(network.socket, "socket", NoBind)
    a = NetworkAdapter(cfg)
    assert a.sock is None
    a.update(1.0, 1 / 60, engine)
    assert not a.sample(0, 1.0, 0, engine).present
    a.stop()


def test_the_fake_tracking_tool_speaks_the_protocol(cfg, engine):
    """tools/send_fake_tracking.py is what people use to test without hardware; it must keep working."""
    port = free_udp_port()
    cfg.set("input.network.port", port)
    a = NetworkAdapter(cfg)
    tool = Path(__file__).resolve().parent.parent / "tools" / "send_fake_tracking.py"
    proc = subprocess.Popen([sys.executable, str(tool), "--port", str(port), "--hz", "120"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(500):
            a.update(1.0, 1 / 60, engine)
            if 0 in a.latest and 1 in a.latest:
                break
            time.sleep(0.01)
        assert a.sample(0, 1.0, 0, engine).present and a.sample(1, 1.0, 0, engine).present
    finally:
        proc.terminate()
        proc.wait(timeout=5)
        a.stop()
