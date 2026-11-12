"""The Tkinter control panel, driven for real (needs a display; skipped where there is none)."""

import json
import tkinter as tk

import pytest

from conftest import free_udp_port, wait_for
from land_hockey.config import TABS, Config, get_schema
from land_hockey.config.live_link import LiveLinkServer
from land_hockey.ui import settings_window as sw
from land_hockey.ui import widgets
from land_hockey.ui.preview import draw_preview


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display for Tk: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def panel(root, tmp_path, monkeypatch):
    """A panel working on throwaway files, so tests never touch the real settings or a running game."""
    settings = tmp_path / "settings.json"
    Config({"live_link.game_port": free_udp_port()}).save(settings)
    monkeypatch.setattr(sw, "SETTINGS_PATH", settings)
    monkeypatch.setattr(sw, "BACKUP_PATH", tmp_path / "settings.prev.json")
    monkeypatch.setattr(sw, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(sw, "ROOT", tmp_path)
    p = sw.ControlPanel(root)
    yield p
    p.link.close()


def row(panel, path):
    panel.show_tab(panel.schema[path].tab)
    return panel.rows[path]


def nav_pages(panel):
    return [(tab, sub) for _label, tab, sub in panel.nav_items]


def test_every_page_opens(panel):
    for tab, sub in nav_pages(panel):
        panel.show_tab(tab, sub)
        panel.root.update_idletasks()
        assert panel.current_tab == tab


def test_every_setting_has_a_control_on_some_page(panel):
    panel.cfg.set("paddles.link_players", False)
    seen = set()
    for tab, sub in nav_pages(panel):
        panel.show_tab(tab, sub)
        seen |= set(panel.rows)
    assert seen == set(get_schema())


def test_no_page_is_big_enough_to_freeze_the_panel(panel):
    """Tk layout is slow on huge pages. Power-ups froze the panel once: keep every page reasonable."""
    panel.cfg.set("paddles.link_players", False)
    for tab, sub in nav_pages(panel):
        panel.show_tab(tab, sub)
        assert len(panel.rows) <= 150, (tab, sub, len(panel.rows))


def test_sidebar_click_opens_the_page(panel):
    i = next(k for k, (_l, t, s) in enumerate(panel.nav_items) if t == "Power-ups" and s not in (None, sw.GLOBAL))
    panel.nav.selection_clear(0, "end")
    panel.nav.selection_set(i)
    panel._on_nav()
    assert panel.current_tab == "Power-ups" and panel.current_sub == panel.nav_items[i][2]
    assert "Power-ups ›" in panel.header.cget("text")


def test_power_up_pages_show_only_that_power_up(panel):
    for label, tab, sub in panel.nav_items:
        if tab == "Power-ups" and sub not in (None, sw.GLOBAL):
            panel.show_tab(tab, sub)
            assert panel.rows and all(p.group.startswith(sub) for p in map(panel.schema.get, panel.rows))


def test_linked_players_hide_player_2_until_unlinked(panel):
    panel.cfg.set("paddles.link_players", True)
    panel.show_tab("Paddles")
    assert not any(k.startswith("paddles.p2.") for k in panel.rows)
    panel.cfg.set("paddles.link_players", False)
    panel.show_tab("Paddles")
    assert any(k.startswith("paddles.p2.") for k in panel.rows)


def test_each_kind_of_row_applies_its_value(panel):
    panel.cfg.set("paddles.link_players", False)
    done = set()
    for tab, sub in nav_pages(panel):
        panel.show_tab(tab, sub)
        for path, r in list(panel.rows.items()):
            kind = r.p.kind
            if kind in done:
                continue
            done.add(kind)
            value = {"float": r.p.max, "int": r.p.max, "bool": not r.p.default, "color": "#123456",
                     "enum": (r.p.options or ("",))[-1], "font": "x.ttf", "str": "متن", "key": "q"}[kind]
            r.apply(value)
            assert panel.cfg[path] == value, path
            assert panel.pending[path] == value
            r.reset()
            assert panel.cfg[path] == r.p.default
    assert done == {"float", "int", "bool", "color", "enum", "font", "str", "key"}


def test_exact_number_field(panel):
    r = row(panel, "ball.base_speed")
    r.svar.set("600")
    r._on_entry()
    assert panel.cfg["ball.base_speed"] == 600
    r.svar.set("600,5")  # Persian keyboards type a comma
    r._on_entry()
    assert panel.cfg["ball.base_speed"] == pytest.approx(600.5, abs=1)


def test_bad_number_field_warns_and_changes_nothing(panel):
    r = row(panel, "ball.base_speed")
    before = panel.cfg["ball.base_speed"]
    r.svar.set("fast")
    r._on_entry()
    assert panel.cfg["ball.base_speed"] == before
    assert "not a number" in panel.status_lbl.cget("text")


def test_out_of_range_number_is_clamped_and_shown(panel):
    r = row(panel, "ball.base_speed")
    r.svar.set("99999999")
    r._on_entry()
    assert panel.cfg["ball.base_speed"] == r.p.max
    assert float(r.svar.get()) == r.p.max


def test_slider_snaps_to_its_step(panel):
    r = row(panel, "ball.base_speed")
    r.var.set(r.p.min + (r.p.step or 1) * 3.2)
    r._on_scale("")
    assert panel.cfg["ball.base_speed"] == pytest.approx(r.p.min + (r.p.step or 1) * 3)


def test_undo_restores_the_previous_value(panel):
    r = row(panel, "ball.radius")
    before = panel.cfg["ball.radius"]
    r.apply(before + 3)
    panel.undo_last()
    assert panel.cfg["ball.radius"] == before and float(r.svar.get()) == before
    panel.undo_last()
    assert "Nothing to undo" in panel.status_lbl.cget("text")


def test_save_is_explicit_and_keeps_a_backup(panel):
    row(panel, "ball.radius").apply(23)
    assert "unsaved" in panel.dirty_lbl.cget("text")
    assert Config.load(sw.SETTINGS_PATH)["ball.radius"] != 23
    panel.save()
    assert Config.load(sw.SETTINGS_PATH)["ball.radius"] == 23
    assert sw.BACKUP_PATH.exists()
    assert "unsaved" not in panel.dirty_lbl.cget("text")


def test_failed_save_is_reported(panel, monkeypatch):
    shown = []

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(panel.cfg, "save", boom)
    monkeypatch.setattr(sw.messagebox, "showerror", lambda *a, **k: shown.append(a))
    panel.save()
    assert shown


def test_revert_goes_back_to_the_file(panel):
    row(panel, "ball.radius").apply(23)
    panel.revert()
    assert panel.cfg["ball.radius"] == Config.load(sw.SETTINGS_PATH)["ball.radius"]


def test_reset_all_asks_first(panel, monkeypatch):
    row(panel, "ball.radius").apply(23)
    monkeypatch.setattr(sw.messagebox, "askyesno", lambda *a, **k: False)
    panel.reset_all()
    assert panel.cfg["ball.radius"] == 23
    monkeypatch.setattr(sw.messagebox, "askyesno", lambda *a, **k: True)
    panel.reset_all()
    assert panel.cfg["ball.radius"] == get_schema()["ball.radius"].default


def test_presets_save_list_and_load(panel, monkeypatch):
    row(panel, "ball.radius").apply(19)
    monkeypatch.setattr(sw.simpledialog, "askstring", lambda *a, **k: "my / preset!")
    panel.save_preset()
    saved = sw.PRESETS_DIR / "my_preset.json"
    assert saved.exists()
    panel._fill_presets()
    assert panel.preset_menu.entrycget(0, "label") == "my_preset"
    row(panel, "ball.radius").apply(22)
    panel.load_preset(saved)
    assert panel.cfg["ball.radius"] == 19


def test_cancelled_preset_name_saves_nothing(panel, monkeypatch):
    monkeypatch.setattr(sw.simpledialog, "askstring", lambda *a, **k: None)
    panel.save_preset()
    assert not sw.PRESETS_DIR.exists()


def test_no_presets_shows_a_placeholder(panel):
    panel._fill_presets()
    assert panel.preset_menu.entrycget(0, "label") == "(no presets)"


def test_search_finds_settings_and_clearing_returns(panel):
    panel.show_tab("Inputs")
    panel.search.set("lidar")
    panel._on_search()
    assert "input.p1.source" in panel.rows and panel.nav.size() == len(panel.nav_items) + 1
    panel.search.set("")
    panel._on_search()
    assert panel.nav.size() == len(panel.nav_items) and panel.current_tab == "Inputs"


def test_search_results_are_capped(panel):
    panel.search.set("a")
    panel._on_search()
    assert len(panel.rows) <= 60


def test_changes_reach_the_game_over_the_link(panel):
    srv = LiveLinkServer(panel.cfg["live_link.game_port"])
    assert srv.ok
    try:
        row(panel, "ball.radius").apply(24)
        row(panel, "ball.base_speed").apply(600)
        panel.flush()
        assert wait_for(srv.poll)[0][0]["values"] == {"ball.radius": 24, "ball.base_speed": 600}
        row(panel, "ball.radius").apply(25)
        panel.flush()
        msg = wait_for(srv.poll)[0][0]
        assert msg["path"] == "ball.radius" and msg["value"] == 25
    finally:
        srv.close()


def connect_fake_game(panel, srv, state):
    """Answer the panel's hello with telemetry, as the game does, until the panel shows it as connected."""
    panel.link.hello()
    addr = wait_for(srv.poll)[0][1]
    srv.send(state, addr)

    def connected():
        panel.poll()
        return panel.was_connected

    wait_for(connected)


def test_connecting_pushes_everything_and_shows_telemetry(panel):
    srv = LiveLinkServer(panel.cfg["live_link.game_port"])
    try:
        connect_fake_game(panel, srv, {
            "type": "state", "state": "PLAYING", "paused": False, "phase": 2, "time_left": 42.0, "golden": False,
            "scores": [3, 1], "balls": 1, "orbs": 2, "effects": [{"id": "expand", "left": 3.2}],
            "inputs": [{"u": 0.5, "present": True}, {"u": 0.2, "present": False}], "fps": 60.0,
            "text_backend": "harfbuzz"})
        assert "Connected" in panel.pill.cget("text")
        assert panel.tel_labels["scores"].cget("text") == "P1 3  —  P2 1"
        assert "absent" in panel.tel_labels["inputs"].cget("text")
        pushed = {}

        def all_pushed():
            for m, _a in srv.poll():
                pushed.update(m.get("values", {}))
            return len(pushed) == len(panel.cfg.values)

        assert wait_for(all_pushed)
    finally:
        srv.close()


def test_a_value_too_large_to_send_live_warns_the_operator(panel):
    row(panel, "text.goal").apply("x" * 9000)
    panel.flush()
    assert "too large" in panel.status_lbl.cget("text")


def test_offline_game_is_shown(panel):
    panel.poll()
    assert "offline" in panel.pill.cget("text")


def test_game_warnings_are_shown(panel):
    srv = LiveLinkServer(panel.cfg["live_link.game_port"])
    try:
        panel.link.hello()
        addr = wait_for(srv.poll)[0][1]
        srv.send({"type": "ack", "warning": "ball too fast"}, addr)

        def shown():
            panel.poll()
            return "ball too fast" in panel.status_lbl.cget("text")

        assert wait_for(shown)
    finally:
        srv.close()


def test_launching_the_game_passes_windowed(panel, monkeypatch):
    calls = []

    class Proc:
        def poll(self):
            return None

    monkeypatch.setattr(sw.subprocess, "Popen", lambda args, cwd=None: calls.append(args) or Proc())
    panel.launch_game()
    panel.launch_game()  # already running
    assert len(calls) == 1 and calls[0][-1] == "--windowed"


def test_failed_launch_is_reported(panel, monkeypatch):
    shown = []

    def boom(*a, **k):
        raise OSError("not found")

    monkeypatch.setattr(sw.subprocess, "Popen", boom)
    monkeypatch.setattr(sw.messagebox, "showerror", lambda *a, **k: shown.append(a))
    panel.launch_game()
    assert shown


def test_supervisor_button_opens_the_page(panel, monkeypatch):
    opened = []
    monkeypatch.setattr(sw.webbrowser, "open", opened.append)
    panel.open_supervisor()
    assert opened == [f"http://127.0.0.1:{panel.cfg['web.port']}/"]


@pytest.mark.parametrize("answer,saved,closed", [(True, True, True), (False, False, True), (None, False, False)])
def test_closing_with_unsaved_changes_asks(panel, monkeypatch, answer, saved, closed):
    row(panel, "ball.radius").apply(21)
    monkeypatch.setattr(sw.messagebox, "askyesnocancel", lambda *a, **k: answer)
    panel.on_close()
    assert (Config.load(sw.SETTINGS_PATH)["ball.radius"] == 21) is saved
    if closed:
        with pytest.raises(tk.TclError):
            panel.root.winfo_exists()
    else:
        assert panel.root.winfo_exists()


def test_color_clash_warning():
    c = Config()
    assert sw.color_warnings(c) == []
    c.set("colors.p1", c["colors.p2"])
    assert any("look alike" in w for w in sw.color_warnings(c))


def test_a_preview_error_cannot_kill_the_panel(panel, monkeypatch):
    def boom(*a):
        raise ValueError("bad layout")

    monkeypatch.setattr(sw, "draw_preview", boom)
    panel.redraw_preview()
    assert "preview error" in panel.warn_lbl.cget("text")


# ---------------------------------------------------------------- widgets and preview
def test_scroll_frame_stays_in_range(root):
    root.deiconify()
    root.geometry("300x200")
    sf = widgets.ScrollFrame(root)
    sf.pack(fill="both", expand=True)
    for k in range(60):
        tk.Label(sf.inner, text=str(k)).pack()
    root.update()
    sf.scroll_units(10000)
    h, vh = sf._limits()
    assert sf.offset == max(0, h - vh)
    sf.scroll_units(-10000)
    assert sf.offset == 0
    sf._on_scrollbar("moveto", "0.5")
    assert 0 < sf.offset < h
    before = sf.offset
    sf._on_scrollbar("scroll", "1", "pages")
    assert sf.offset > before
    sf.to_top()
    assert sf.offset == 0


def test_tooltip_shows_and_hides(root):
    root.deiconify()
    lbl = tk.Label(root, text="x")
    lbl.pack()
    t = widgets.Tooltip(lbl, "help")
    t.show()
    assert t.tip is not None
    t.hide()
    assert t.tip is None
    empty = widgets.Tooltip(lbl, "")
    empty.show()
    assert empty.tip is None


def test_number_formats():
    assert widgets.decimals(1) == 0 and widgets.decimals(None) == 0
    assert widgets.decimals(0.05) == 2 and widgets.decimals(0.001) == 3
    schema = get_schema()
    assert widgets.fmt(schema["match.score_limit"], 7.0) == "7"


@pytest.mark.parametrize("values", [{}, {"arena.layout_rotation_deg": 90}, {"walls.top_percent": 40},
                                    {"display.canvas_width": 640, "display.canvas_height": 360}])
def test_preview_draws_any_layout(root, values):
    cv = tk.Canvas(root, width=340, height=340)
    warnings = draw_preview(cv, Config(values), 340)
    assert isinstance(warnings, list) and len(cv.find_all()) > 5


def test_all_tabs_are_used():
    used = {p.tab for p in get_schema().values()}
    assert used == set(TABS)


def test_saved_settings_are_valid_json_in_utf8(panel):
    row(panel, "ball.radius").apply(23)
    panel.save()
    assert json.loads(sw.SETTINGS_PATH.read_text(encoding="utf-8"))["ball"]["radius"] == 23
