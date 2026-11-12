"""Routing, filtering, recording and replay around the individual input sources."""

import json
import math

import pygame
import pytest

from conftest import free_udp_port, playing
from land_hockey.inputs import registry
from land_hockey.inputs.base import InputAdapter, PlayerSample
from land_hockey.inputs.filters import OneEuro, PlayerFilter
from land_hockey.inputs.keyboard import KeyboardAdapter, key_code
from land_hockey.inputs.manager import InputManager
from land_hockey.inputs.mouse import MouseAdapter
from land_hockey.inputs.replay import Recorder, ReplayAdapter


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield


class Scripted(InputAdapter):
    name = "scripted"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.updates = 0
        self.stopped = 0
        self.events = []

    def update(self, now, dt, engine):
        self.updates += 1

    def handle_event(self, event):
        self.events.append(event)

    def sample(self, idx, now, dt, engine):
        return PlayerSample(True, 0.25 if idx == 0 else 0.75, 1.0, now, None, self.name)

    def stop(self):
        self.stopped += 1


class Crashing(InputAdapter):
    name = "crashing"

    def update(self, now, dt, engine):
        raise RuntimeError("sensor unplugged")

    def sample(self, idx, now, dt, engine):
        raise RuntimeError("sensor unplugged")


def use(cfg, monkeypatch, name, cls):
    """Register a test adapter the same way a real sensor module is added."""
    monkeypatch.setitem(registry.ADAPTERS, name, f"test:{cls.__name__}")
    real = registry.load
    monkeypatch.setattr("land_hockey.inputs.manager.load", lambda n: cls if n == name else real(n))
    m = InputManager(cfg)
    m.adapters[name] = m.adapter(name)
    cfg.values["input.p1.source"] = name  # the enum list was built before the test registered this source
    cfg.values["input.p2.source"] = name
    return m


def test_each_player_can_use_a_different_source(cfg, engine):
    cfg.set("input.p1.source", "ai")
    cfg.set("input.p2.source", "keyboard")
    m = InputManager(cfg)
    samples, presence = m.poll(0.0, 1 / 60, engine)
    assert samples[0].source == "ai" and samples[1].source == "keyboard"
    assert presence == [True, True]
    m.close()


def test_adapters_are_created_once_and_only_when_used(cfg, engine):
    m = InputManager(cfg)
    assert m.adapters == {}
    m.poll(0.0, 1 / 60, engine)
    assert set(m.adapters) == {"keyboard"}
    first = m.adapters["keyboard"]
    m.poll(0.1, 1 / 60, engine)
    assert m.adapters["keyboard"] is first
    m.close()


def test_a_source_updates_once_per_frame_even_for_both_players(cfg, engine, monkeypatch):
    m = use(cfg, monkeypatch, "scripted", Scripted)
    m.poll(0.0, 1 / 60, engine)
    assert m.adapters["scripted"].updates == 1
    m.close()
    assert m.adapters["scripted"].stopped == 1


def test_events_reach_the_adapters(cfg, monkeypatch):
    m = use(cfg, monkeypatch, "scripted", Scripted)
    m.handle_event("event")
    assert m.adapters["scripted"].events == ["event"]


def test_demo_mode_plays_the_ai_but_reports_real_presence(cfg, engine, monkeypatch):
    m = use(cfg, monkeypatch, "scripted", Scripted)
    samples, presence = m.poll(0.0, 1 / 60, engine, demo=True)
    assert samples[0].source == "ai" and samples[1].source == "ai"
    assert presence == [True, True]
    assert m.last[0].source == "scripted"  # the real sensor keeps being read while the demo runs
    m.close()


def test_a_crashing_sensor_reads_as_absent_instead_of_stopping_the_game(cfg, engine, monkeypatch):
    m = use(cfg, monkeypatch, "crashing", Crashing)
    playing(engine)
    for k in range(5):
        samples, presence = m.poll(100.0 + k, 1 / 60, engine)
        engine.step(1 / 60, samples, presence)
    assert presence == [False, False]
    m.close()


class Malformed(InputAdapter):
    name = "malformed"

    def sample(self, idx, now, dt, engine):
        return None if idx == 0 else PlayerSample(True, "left")


def test_a_sensor_returning_nonsense_reads_as_absent(cfg, engine, monkeypatch):
    m = use(cfg, monkeypatch, "malformed", Malformed)
    _samples, presence = m.poll(100.0, 1 / 60, engine)
    assert presence == [False, False]
    m.close()


def test_a_full_disk_while_recording_does_not_stop_the_game(cfg, engine, tmp_path):
    class FullDisk:
        def write(self, now, samples):
            raise OSError("disk full")

        def close(self):
            raise OSError("disk full")

    cfg.set("input.record", True)
    m = InputManager(cfg)
    m.recorder = FullDisk()
    m.poll(0.0, 1 / 60, engine)
    assert m.record_failed and m.recorder is None
    m.close()


def test_a_sensor_that_cannot_even_start_reads_as_absent(cfg, engine, monkeypatch):
    def boom(_name):
        raise ImportError("no module named rplidar")

    monkeypatch.setattr("land_hockey.inputs.manager.load", boom)
    m = InputManager(cfg)
    samples, presence = m.poll(100.0, 1 / 60, engine)
    assert presence == [False, False] and samples[0].u is None
    m.close()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_sensor_sending_non_numbers_cannot_reach_the_engine(cfg, bad):
    f = PlayerFilter()
    out = f.apply(PlayerSample(True, bad), 100.0, 1 / 60, cfg, smooth=True)
    assert out.u is None


def test_filter_clamps_positions_to_the_arc(cfg):
    assert PlayerFilter().apply(PlayerSample(True, 5.0), 0.0, 1 / 60, cfg, False).u == 1.0
    assert PlayerFilter().apply(PlayerSample(True, -5.0), 0.0, 1 / 60, cfg, False).u == 0.0


def test_filter_dead_zone_ignores_tiny_changes(cfg):
    f = PlayerFilter()
    f.apply(PlayerSample(True, 0.5), 0.0, 1 / 60, cfg, False)
    assert f.apply(PlayerSample(True, 0.5005), 1 / 60, 1 / 60, cfg, False).u == 0.5


def test_filter_accepts_a_real_jump_once_it_is_confirmed(cfg):
    f = PlayerFilter()
    for k in range(10):
        f.apply(PlayerSample(True, 0.2), k / 60, 1 / 60, cfg, True)
    u = 0.2
    for k in range(10, 40):
        u = f.apply(PlayerSample(True, 0.9), k / 60, 1 / 60, cfg, True).u
    assert u > 0.8


def test_one_euro_follows_a_steady_signal_and_resets():
    e = OneEuro()
    assert e(1.0, 0.0, 1.0, 0.0) == 1.0
    assert e(1.0, 1.0, 1.0, 0.0) == pytest.approx(1.0)
    v = 1.0
    for k in range(2, 400):
        v = e(2.0, k / 60 + 1, 1.0, 0.0)
    assert v == pytest.approx(2.0, abs=0.01)
    e.reset()
    assert e(7.0, 0.0, 1.0, 0.0) == 7.0


# ---------------------------------------------------------------- recording and replay
def test_record_then_replay_reproduces_the_session(cfg, engine, tmp_path):
    path = tmp_path / "session.jsonl"
    cfg.set("input.replay_file", str(path))
    cfg.set("input.record", True)
    cfg.set("input.p1.source", "ai")
    cfg.set("input.p2.source", "ai")
    playing(engine)
    m = InputManager(cfg)
    recorded = []
    for k in range(60):
        samples, presence = m.poll(k / 60, 1 / 60, engine)
        recorded.append(samples[0].u)
        engine.step(1 / 60, samples, presence)
    cfg.set("input.record", False)
    m.poll(1.0, 1 / 60, engine)  # closes the file
    assert m.recorder is None
    m.close()
    assert len(path.read_text(encoding="utf-8").splitlines()) == 60

    r = ReplayAdapter(cfg)
    played = []
    for k in range(60):
        played.append(r.sample(0, k / 60, 1 / 60, engine).u)
        r.update(k / 60, 1 / 60, engine)
    assert played[0] == pytest.approx(recorded[0], abs=1e-6)
    assert played[30] == pytest.approx(recorded[30], abs=0.03)


def test_replay_loops(cfg, tmp_path):
    path = tmp_path / "r.jsonl"
    path.write_text("\n".join(json.dumps({"t": t, "p": [[True, t], [True, 1 - t]]}) for t in (0.0, 0.5, 1.0)) + "\n",
                    encoding="utf-8")
    cfg.set("input.replay_file", str(path))
    r = ReplayAdapter(cfg)
    r.update(0, 0.6, None)
    assert r.sample(0, 0, 0, None).u == 0.5 and r.sample(1, 0, 0, None).u == 0.5
    r.update(0, 1.0, None)
    assert r.sample(0, 0, 0, None).u == 0.0  # wrapped around


@pytest.mark.parametrize("content", ["", "not json\n", "[1,2]\n", '{"t": 0}\n', '{"p": [[true, 0.5]]}\n', "5\n",
                                     '{"t": "x", "p": []}\n', '{"t": 0, "p": 3}\n', '{"t": 0, "p": [3, 4]}\n',
                                     '{"t": 0, "p": [[true]]}\n', '{"t": 0, "p": [[true, "left"], [true, null]]}\n'])
def test_a_wrong_replay_file_does_nothing_instead_of_crashing(cfg, engine, tmp_path, content):
    path = tmp_path / "r.jsonl"
    path.write_text(content, encoding="utf-8")
    cfg.set("input.replay_file", str(path))
    r = ReplayAdapter(cfg)
    r.update(0.0, 1 / 60, engine)
    for idx in (0, 1):
        s = r.sample(idx, 0.0, 1 / 60, engine)
        assert s.u is None or 0.0 <= s.u <= 1.0


def test_missing_replay_file_reads_as_absent(cfg, tmp_path):
    cfg.set("input.replay_file", str(tmp_path / "nope.jsonl"))
    r = ReplayAdapter(cfg)
    r.update(0.0, 1 / 60, None)
    assert not r.sample(0, 0.0, 0.0, None).present


def test_recording_to_an_impossible_path_does_not_stop_the_game(cfg, engine, tmp_path):
    (tmp_path / "file").write_text("x", encoding="utf-8")
    cfg.set("input.replay_file", str(tmp_path / "file" / "cannot" / "be" / "here.jsonl"))
    cfg.set("input.record", True)
    m = InputManager(cfg)
    for k in range(3):
        m.poll(k / 60, 1 / 60, engine)
    m.close()


def test_recorder_times_start_at_zero(tmp_path):
    rec = Recorder(tmp_path / "x.jsonl")
    rec.write(50.0, {0: PlayerSample(True, 0.1), 1: PlayerSample(False, None)})
    rec.write(50.5, {0: PlayerSample(True, 0.2), 1: PlayerSample(False, None)})
    rec.close()
    lines = [json.loads(x) for x in (tmp_path / "x.jsonl").read_text().splitlines()]
    assert lines[0] == {"t": 0.0, "p": [[True, 0.1], [False, None]]} and lines[1]["t"] == 0.5


# ---------------------------------------------------------------- keyboard and mouse
def test_keyboard_settings_rebind_live(cfg):
    kb = KeyboardAdapter(cfg)
    assert kb.direction(0, {pygame.K_d: 1}) == 1
    cfg.set("input.keyboard.p1_right", "j")
    assert kb.direction(0, {pygame.K_d: 1}) == 0 and kb.direction(0, {pygame.K_j: 1}) == 1


def test_unknown_key_names_are_harmless(cfg):
    assert key_code("not-a-key") is None
    cfg.set("input.keyboard.p1_left", "not-a-key")
    assert KeyboardAdapter(cfg).direction(0, {pygame.K_a: 1}) == 0


def test_keyboard_alternate_keys_can_be_disabled(cfg):
    kb = KeyboardAdapter(cfg)
    assert kb.direction(0, {pygame.K_s: 1}) == 1
    cfg.set("input.keyboard.alt_keys_enabled", False)
    assert kb.direction(0, {pygame.K_s: 1}) == 0


def test_keyboard_opposite_keys_cancel(cfg):
    assert KeyboardAdapter(cfg).direction(0, {pygame.K_a: 1, pygame.K_d: 1}) == 0


def test_keyboard_brakes_and_stops_at_the_ends(cfg):
    kb = KeyboardAdapter(cfg)
    for _ in range(300):
        s = kb.integrate(0, 1, 1 / 60)
    assert s.u == 1.0 and kb.v[0] == 0.0
    for _ in range(20):
        kb.integrate(0, -1, 1 / 60)
    moving = abs(kb.v[0])
    assert moving > 0
    for _ in range(120):
        kb.integrate(0, 0, 1 / 60)
    assert kb.v[0] == 0.0  # released: comes to rest
    before = kb.u[0]
    kb.integrate(0, 1, 1 / 60)
    assert kb.u[0] >= before  # reversing is immediate


def test_keyboard_reads_real_key_state(cfg, engine):
    s = KeyboardAdapter(cfg).sample(0, 0.0, 1 / 60, engine)
    assert s.present and s.u == pytest.approx(0.5)


def test_mouse_maps_screen_angle_to_the_arc(cfg, engine, monkeypatch):
    m = MouseAdapter(cfg)
    assert not m.sample(0, 0.0, 0.0, None).present
    g = engine.geom
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (int(g.cx - g.R), int(g.cy)))
    s = m.sample(0, 0.0, 0.0, engine)
    assert s.present and s.u == pytest.approx(0.5, abs=0.02)
    assert math.hypot(*s.xy) == pytest.approx(1.0, abs=0.01)


def test_mouse_without_a_display_holds_position(cfg, engine, monkeypatch):
    def boom():
        raise pygame.error("video system not initialized")

    monkeypatch.setattr(pygame.mouse, "get_pos", boom)
    s = MouseAdapter(cfg).sample(0, 0.0, 0.0, engine)
    assert s.present and s.u is None
