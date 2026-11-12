"""The application layer: main-loop frame, hotkeys, commands from the panel and the supervisor page, output transforms."""

import csv
import json

import pygame
import pytest

from land_hockey import app as app_mod
from land_hockey.app import GameApp
from land_hockey.config import Config
from land_hockey.config.live_link import LiveLinkClient, LiveLinkServer
from land_hockey.core.engine import ATTRACT, INTRO, RESULT
from land_hockey.web import history

from conftest import free_udp_port, wait_for


@pytest.fixture
def game(tmp_path):
    path = tmp_path / "settings.json"
    Config({"web.enabled": False, "live_link.enabled": False}).save(path)
    g = GameApp(config_path=path, headless=True, seed=4)
    yield g
    g.shutdown()


def key(k, type_=pygame.KEYDOWN):
    return pygame.event.Event(type_, key=k, mod=0, unicode="")


def frames(game, n=5, dt=1 / 60):
    game._t = getattr(game, "_t", 0.0)
    out = None
    for _ in range(n):
        game._t += dt
        out = game.tick(dt, game._t)
    return out


def test_tick_returns_a_full_frame_and_advances_the_game(game):
    frame = frames(game, 5)
    assert frame.get_size() == (game.cfg["display.canvas_width"], game.cfg["display.canvas_height"])
    assert game.engine.time > 0


def test_a_slow_frame_cannot_spiral(game):
    t0 = game.engine.time
    game.tick(5.0, 1.0)
    assert game.engine.time - t0 < 0.2  # capped; the game slows down instead of freezing to catch up


def test_physics_is_independent_of_frame_rate(game):
    game.tick(1 / 240, 0.0)
    t0 = game.engine.time
    for k in range(240):
        game.tick(1 / 240, k / 240)
    assert game.engine.time - t0 == pytest.approx(1.0, abs=0.02)


def test_run_loop_finishes_and_shuts_down(tmp_path):
    path = tmp_path / "s.json"
    Config({"web.enabled": False, "live_link.enabled": False}).save(path)
    g = GameApp(config_path=path, headless=True, seed=1)
    g.run(seconds=0.2)
    assert not g.running


@pytest.mark.parametrize("k", [pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER])
def test_start_keys_begin_a_match(game, k):
    assert game.engine.state == ATTRACT
    game._handle_event(key(k), 0.0)
    assert game.engine.state == INTRO


def test_start_keys_do_nothing_mid_match(game):
    game._handle_event(key(pygame.K_SPACE), 0.0)
    count = game.engine.match_count
    game._handle_event(key(pygame.K_SPACE), 0.1)
    assert game.engine.match_count == count


def test_space_restarts_from_the_result_screen(game):
    game.engine.state = RESULT
    game._handle_event(key(pygame.K_SPACE), 0.0)
    assert game.engine.state == INTRO


def test_p_pauses(game):
    game._handle_event(key(pygame.K_p), 0.0)
    assert game.engine.paused
    game._handle_event(key(pygame.K_p), 0.0)
    assert not game.engine.paused


def test_escape_needs_two_presses(game):
    game._handle_event(key(pygame.K_ESCAPE), 10.0)
    assert game.running
    game._handle_event(key(pygame.K_ESCAPE), 15.0)  # too late: this is a new first press
    assert game.running
    game._handle_event(key(pygame.K_ESCAPE), 15.5)
    assert not game.running


def test_window_close_quits(game):
    game._handle_event(pygame.event.Event(pygame.QUIT), 0.0)
    assert not game.running


def test_holding_r_resets_but_tapping_does_not(game):
    game.engine.start_match()
    game._handle_event(key(pygame.K_r), 0.0)
    game._handle_event(key(pygame.K_r, pygame.KEYUP), 0.1)
    game._check_hold_keys(1.0)
    assert game.engine.state == INTRO
    game._handle_event(key(pygame.K_r), 2.0)
    game._check_hold_keys(2.1)
    assert game.engine.state == INTRO
    game._check_hold_keys(2.6)
    assert game.engine.state == ATTRACT


def test_debug_and_calibration_keys(game):
    game._handle_event(key(pygame.K_F3), 0.0)
    assert game.cfg["debug.overlay"]
    frames(game, 2)  # the overlay draws
    game._handle_event(key(pygame.K_F2), 0.0)
    assert game.cfg["debug.calibration"]
    frames(game, 2)


def test_debug_number_keys_spawn_power_ups_only_with_the_overlay_on(game):
    game.engine.start_match()
    game._handle_event(key(pygame.K_1), 0.0)
    assert not game.engine.orbs
    game.cfg.set("debug.overlay", True)
    game._handle_event(key(pygame.K_1), 0.0)
    assert game.engine.orbs


def test_exhibition_mode_locks_the_operator_keys(game, monkeypatch):
    game.cfg.set("display.exhibition_mode", True)
    opened = []
    monkeypatch.setattr(game, "open_panel", lambda: opened.append(1))
    game._handle_event(key(pygame.K_F1), 0.0)
    game._handle_event(key(pygame.K_F3), 0.0)
    assert not opened and not game.cfg["debug.overlay"]
    game._handle_event(key(pygame.K_SPACE), 0.0)
    assert game.engine.state == INTRO  # visitors can still start a game


def test_f11_toggles_fullscreen_setting(game):
    before = game.cfg["display.fullscreen"]
    game._handle_event(key(pygame.K_F11), 0.0)
    assert game.cfg["display.fullscreen"] != before


def test_panel_opens_once_and_missing_panel_is_harmless(game, monkeypatch):
    calls = []

    class Proc:
        def poll(self):
            return None

    def popen(cmd, cwd=None):
        calls.append(cmd)
        return Proc()

    monkeypatch.setattr(app_mod.subprocess, "Popen", popen)
    game.open_panel()
    game.open_panel()
    assert len(calls) == 1
    game.panel_proc = None

    def fail(*a, **k):
        raise OSError("not found")

    monkeypatch.setattr(app_mod.subprocess, "Popen", fail)
    game.open_panel()


# ---------------------------------------------------------------- live link
@pytest.fixture
def linked(game):
    game.live = LiveLinkServer(0)
    cl = LiveLinkClient(game.live.port)
    yield game, cl
    cl.close()


def until(game, cond, tries=500):
    import time

    for _ in range(tries):
        game._poll_live()
        if cond():
            return True
        time.sleep(0.002)
    return False


def test_panel_edits_apply_live_with_an_ack(linked):
    game, cl = linked
    cl.set("ball.radius", 25)
    assert until(game, lambda: game.cfg["ball.radius"] == 25)
    msgs = wait_for(cl.poll)
    assert msgs[0]["type"] == "ack" and msgs[0]["ok"] and msgs[0]["value"] == 25


def test_invalid_panel_edit_is_clamped_and_reported(linked):
    game, cl = linked
    cl.set_many({"ball.max_speed": 1e12, "ball.radius": 22})
    assert until(game, lambda: game.cfg["ball.radius"] == 22)
    assert game.cfg["ball.max_speed"] == game.cfg.schema["ball.max_speed"].max


@pytest.mark.parametrize("msg", [
    {"type": "set"}, {"type": "set", "path": None, "value": None}, {"type": "set", "path": "ball.radius", "value": "x"},
    {"type": "set_many"}, {"type": "set_many", "values": 5}, {"type": "set_many", "values": [1]},
    {"type": "command"}, {"type": "command", "name": None}, {"type": "command", "name": "spawn_powerup", "args": 5},
    {"type": "command", "name": "spawn_powerup", "args": [1]}, {"type": "command", "name": "no_such"},
    {"type": 5}, {},
])
def test_strange_panel_messages_do_not_crash_the_game(linked, msg):
    game, cl = linked
    cl.send(msg)
    cl.hello()
    assert until(game, lambda: bool(game.live.clients))
    frames(game, 2)


@pytest.mark.parametrize("name", ["start_match", "pause", "resume", "toggle_pause", "reset_match", "spawn_ball",
                                  "toggle_debug", "toggle_calibration", "apply_display", "reload_from_disk"])
def test_every_panel_command_runs(game, name):
    game._command(name, {})
    frames(game, 2)


def test_pause_and_resume_commands_are_idempotent(game):
    game._command("pause", {})
    game._command("pause", {})
    assert game.engine.paused
    game._command("resume", {})
    game._command("resume", {})
    assert not game.engine.paused


def test_spawn_command_uses_its_argument(game):
    game.engine.start_match()
    game._command("spawn_powerup", {"id": "expand"})
    assert game.engine.orbs and game.engine.orbs[0].type_id == "expand"


def test_quit_command(game):
    game._command("quit", {})
    assert not game.running


def test_reload_picks_up_the_saved_file(game):
    Config({"ball.radius": 27}).save(game.config_path)
    game._command("reload_from_disk", {})
    assert game.cfg["ball.radius"] == 27


def test_telemetry_reaches_the_panel(linked):
    game, cl = linked
    cl.hello()
    assert until(game, lambda: bool(game.live.clients))
    game._send_state(100.0)
    got = wait_for(lambda: [m for m in cl.poll() if m["type"] == "state"])
    assert got[0]["state"] == game.engine.state and len(got[0]["inputs"]) == 2 and cl.connected
    json.dumps(got[0])


def test_telemetry_is_rate_limited(linked):
    game, cl = linked
    cl.hello()
    assert until(game, lambda: bool(game.live.clients))
    game._send_state(100.0)
    t = game._state_t
    game._send_state(100.0001)
    assert game._state_t == t


# ---------------------------------------------------------------- supervisor page commands
class FakeWeb:
    url = "http://127.0.0.1:1/"

    def __init__(self):
        self.cmds = []
        self.snap = None

    def drain(self):
        out, self.cmds = self.cmds, []
        return out

    def publish(self, snap):
        self.snap = snap

    def stop(self):
        pass


@pytest.fixture
def web(game):
    game.web = FakeWeb()
    return game, game.web


def test_names_flow_from_the_page_to_the_game(web):
    game, w = web
    w.cmds = [("names", {"p1": "سارا", "p2": "Ali"})]
    game._poll_web(1.0)
    assert game.engine.names == ["سارا", "Ali"]
    w.cmds = [("name", {"player": 1, "name": "Reza"})]
    game._poll_web(2.0)
    assert game.engine.names == ["سارا", "Reza"]
    w.cmds = [("clear_names", {})]
    game._poll_web(3.0)
    assert game.engine.names == ["", ""]


def test_start_pause_reset_from_the_page(web):
    game, w = web
    w.cmds = [("start", {})]
    game._poll_web(1.0)
    assert game.engine.state == INTRO
    w.cmds = [("start", {})]  # pressing it twice must not restart a running match
    count = game.engine.match_count
    game._poll_web(1.1)
    assert game.engine.match_count == count
    w.cmds = [("pause", {})]
    game._poll_web(1.2)
    assert game.engine.paused
    w.cmds = [("reset", {})]
    game._poll_web(1.3)
    assert game.engine.state == ATTRACT and not game.engine.paused


def test_start_while_paused_unpauses(web):
    game, w = web
    game.engine.toggle_pause()
    w.cmds = [("start", {})]
    game._poll_web(1.0)
    assert game.engine.state == INTRO and not game.engine.paused


def test_published_state_is_json_and_throttled(web):
    game, w = web
    game._poll_web(1.0)
    snap = w.snap
    json.dumps(snap)
    assert snap["state"] == ATTRACT and len(snap["colors_glow"]) == 2 and snap["colors_glow"][0].startswith("#")
    w.snap = None
    game._poll_web(1.01)
    assert w.snap is None


def test_supervisor_browser_failure_is_harmless(web, monkeypatch):
    game, _w = web

    def boom(url):
        raise RuntimeError("no browser")

    monkeypatch.setattr(app_mod.webbrowser, "open", boom)
    game.open_supervisor()


def test_web_port_in_use_keeps_the_game_running(tmp_path):
    from land_hockey.web.server import SupervisorServer

    blocker = SupervisorServer("127.0.0.1", 0)
    assert blocker.start()
    path = tmp_path / "s.json"
    Config({"web.enabled": True, "web.bind": "127.0.0.1", "web.port": blocker.port, "live_link.enabled": False,
            "web.open_browser": False}).save(path)
    g = GameApp(config_path=path, windowed=True, seed=1)
    try:
        assert g.web is None
        g.tick(1 / 60, 0.0)
    finally:
        blocker.stop()
        g.shutdown()


def test_real_servers_start_with_the_game_and_stop_with_it(tmp_path):
    import urllib.request

    path = tmp_path / "s.json"
    Config({"web.bind": "127.0.0.1", "web.port": free_udp_port(), "live_link.game_port": free_udp_port(),
            "web.open_browser": False}).save(path)
    g = GameApp(config_path=path, windowed=True, seed=1)
    try:
        assert g.live.ok and g.web_urls == [g.web.url]
        g._poll_web(1.0)
        with urllib.request.urlopen(g.web.url + "api/state", timeout=3) as r:
            assert json.loads(r.read())["state"] == ATTRACT
    finally:
        g.shutdown()


def finished_match(game):
    game.engine.names = ["سارا", ""]
    return [{"type": "match_end", "scores": [5, 3], "winner": 0, "duration": 60.0, "golden": False,
             "stats": {"powerups": [1, 2], "smart": [0, 1], "hits": [9, 8]}}]


def test_finished_matches_are_logged_for_the_real_game(game, tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_PATH", tmp_path / "history.jsonl")
    game.headless = False
    game._log_events(finished_match(game))
    game._log_events(finished_match(game))
    rows = list(csv.reader((tmp_path / "matches.csv").open(encoding="utf-8")))
    assert rows[0][0] == "datetime" and len(rows) == 3 and rows[1][2:5] == ["5", "3", "p1"]
    assert history.read_all(tmp_path / "history.jsonl")[0]["players"][0]["name"] == "سارا"
    assert game.last_result["winner"] == 0
    game.headless = True


def test_headless_runs_never_touch_the_logs(game, tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(app_mod, "LOGS_DIR", logs)
    monkeypatch.setattr(history, "HISTORY_PATH", logs / "history.jsonl")
    game._log_events(finished_match(game))
    assert game.last_result is not None and not list(logs.iterdir())


def test_unwritable_logs_do_not_stop_the_game(game, tmp_path, monkeypatch):
    blocked = tmp_path / "file"
    blocked.write_text("x", encoding="utf-8")
    monkeypatch.setattr(app_mod, "LOGS_DIR", blocked)
    monkeypatch.setattr(history, "HISTORY_PATH", blocked / "history.jsonl")
    game.headless = False
    game._log_events(finished_match(game))
    game.headless = True


# ---------------------------------------------------------------- projector output
@pytest.mark.parametrize("rot", ["0", "90", "180", "270"])
@pytest.mark.parametrize("flip", [(False, False), (True, False), (False, True)])
def test_every_output_transform_presents(game, rot, flip):
    game.cfg.set("display.rotation", rot)
    game.cfg.set("display.flip_h", flip[0])
    game.cfg.set("display.flip_v", flip[1])
    game._present(frames(game, 1))


def test_rotating_the_output_really_rotates_the_picture(game):
    frame = pygame.Surface(game.screen.get_size())
    w, h = frame.get_size()
    frame.set_at((w - 2, h // 2), (255, 0, 0))
    game.cfg.set("display.rotation", "90")
    game._present(frame)
    assert game.screen.get_at((w // 2, 1))[:3] == (255, 0, 0)  # the right edge turned to the top


def test_output_scale_and_offset_keep_the_screen_size(game):
    game.cfg.set("display.output_scale", 0.5)
    game.cfg.set("display.output_offset_x", 30)
    size = game.screen.get_size()
    game._present(frames(game, 1))
    assert game.screen.get_size() == size
    assert game.screen.get_at((2, 2))[:3] == (0, 0, 0)  # outside the scaled image stays black


def test_canvas_size_change_reopens_the_display(game):
    game.cfg.set("display.canvas_width", 800)
    game.cfg.set("display.canvas_height", 800)
    game._open_display()
    assert game.screen.get_size() == (800, 800)
    assert frames(game, 1).get_size() == (800, 800)


@pytest.fixture
def windowed_game(tmp_path):
    """Not headless, so F11 really switches between fullscreen and a window."""
    path = tmp_path / "s.json"
    Config({"web.enabled": False, "live_link.enabled": False}).save(path)
    g = GameApp(config_path=path, windowed=True, seed=4)
    yield g
    g.shutdown()


def record_set_mode(monkeypatch):
    calls = []
    real = pygame.display.set_mode

    def spy(size, flags=0, **kw):
        calls.append(flags)
        return real(size, flags, **kw)

    monkeypatch.setattr(pygame.display, "set_mode", spy)
    return calls


@pytest.mark.parametrize("change", ["resize", "fullscreen", "monitor"])
def test_a_scaled_window_is_never_changed_directly(windowed_game, monkeypatch, change):
    """pygame can crash, only sometimes, when it changes a SCALED window directly. Reopen through a plain window."""
    g = windowed_game
    calls = record_set_mode(monkeypatch)
    if change == "resize":
        g.cfg.set("display.canvas_width", 800)
    elif change == "fullscreen":
        g.cfg.set("display.fullscreen", True)
    else:
        g.cfg.set("display.display_index", 1)
    g._open_display()
    assert len(calls) >= 2 and calls[0] == 0 and calls[1] & pygame.SCALED


def test_f11_goes_back_and_forth_while_playing(windowed_game):
    g = windowed_game
    g.engine.start_match()
    size = g.screen.get_size()
    for _ in range(4):
        g._handle_event(key(pygame.K_F11), 0.0)
        g._open_display()
        g._present(frames(g, 2))
        assert g.screen.get_size() == size


def test_repeated_resizes_keep_rendering(windowed_game):
    g = windowed_game
    for s in (800, 640, 1080, 720):
        g.cfg.set("display.canvas_width", s)
        g.cfg.set("display.canvas_height", s)
        g._open_display()
        g._present(frames(g, 2))
        assert g.screen.get_size() == (s, s)


def test_bad_display_index_falls_back(game):
    game.cfg.set("display.display_index", game.cfg.schema["display.display_index"].max)
    game._display_key = None
    game._open_display()
    assert game.screen is not None


def test_a_corrupt_settings_file_still_starts_the_game(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{ broken", encoding="utf-8")
    Config.load(path)
    g = GameApp(config_path=path, headless=True, seed=1)
    try:
        assert g.tick(1 / 60, 0.0) is not None
    finally:
        g.shutdown()
