"""Market Hockey control panel (Tkinter). Every setting from the schema, live-linked to the running game."""

from __future__ import annotations

import re
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from ..config import TABS, Config, get_schema
from ..config.live_link import LiveLinkClient
from ..paths import BACKUP_PATH, PRESETS_DIR, ROOT, SETTINGS_PATH
from ..powerups import registry
from ..render.colors import delta_e, hex_rgb
from . import theme
from .preview import draw_preview
from .widgets import SettingRow

SEARCH_TAB = "🔍 Search results"


def color_warnings(cfg) -> list[str]:
    names = {"p1": "Player 1", "p2": "Player 2", "good": "Good (green)", "bad": "Bad (red)", "neutral": "Neutral"}
    pairs = [("p1", "good"), ("p1", "bad"), ("p2", "good"), ("p2", "bad"), ("p1", "p2"), ("good", "bad"),
             ("p1", "neutral"), ("p2", "neutral")]
    out = []
    for a, b in pairs:
        d = delta_e(hex_rgb(cfg[f"colors.{a}"]), hex_rgb(cfg[f"colors.{b}"]))
        if d < 25:
            out.append(f"{names[a]} and {names[b]} colors look alike (ΔE {d:.0f})")
    return out


class ControlPanel:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.schema = get_schema()
        self.cfg = Config.load(SETTINGS_PATH)
        self.saved = self.cfg.snapshot()
        self.link = LiveLinkClient(self.cfg["live_link.game_port"])
        self.rows: dict[str, SettingRow] = {}
        self.pending: dict = {}
        self.undo: list = []
        self.current_tab = TABS[0]
        self.was_connected = False
        self.game_proc = None
        self._preview_job = None
        self._last_hello = 0.0
        self.telemetry: dict = {}

        root.title("Market Hockey — Control Panel · هاکی بازار")
        root.geometry("1360x860")
        root.minsize(1100, 680)
        theme.apply(root)
        self._build()
        self.show_tab(TABS[0])
        self.redraw_preview()
        for w in self.cfg.warnings:
            self.status(w, warn=True)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        mod = "Command" if sys.platform == "darwin" else "Control"
        root.bind_all(f"<{mod}-s>", lambda e: self.save())
        root.bind_all(f"<{mod}-z>", lambda e: self.undo_last())
        root.bind_all(f"<{mod}-f>", lambda e: self.search_entry.focus_set())
        root.after(100, self.poll)
        root.after(33, self.flush)

    # ================================================================== layout
    def _build(self) -> None:
        r = self.root
        top = ttk.Frame(r, padding=(14, 10))
        top.pack(side="top", fill="x")
        ttk.Label(top, text="Market Hockey", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="  هاکی بازار · Control Panel", style="MutedBg.TLabel").pack(side="left")
        self.pill = tk.Label(top, text="○ Game offline — editing file", bg=theme.CARD2, fg=theme.MUTED, padx=10, pady=4)
        self.pill.pack(side="left", padx=16)
        btns = ttk.Frame(top)
        btns.pack(side="right")
        self.windowed = tk.BooleanVar(value=True)
        ttk.Checkbutton(btns, text="windowed", variable=self.windowed, style="Bg.TCheckbutton").pack(side="left", padx=4)
        for text, cmd, style in (
                ("▶ Launch Game", self.launch_game, "TButton"),
                ("Start Match", lambda: self.link.command("start_match"), "TButton"),
                ("Pause / Resume", lambda: self.link.command("toggle_pause"), "TButton"),
                ("Reset Match", lambda: self.link.command("reset_match"), "TButton"),
                ("Save", self.save, "Accent.TButton"),
                ("Save Preset…", self.save_preset, "TButton")):
            ttk.Button(btns, text=text, command=cmd, style=style).pack(side="left", padx=3)
        self.preset_btn = ttk.Menubutton(btns, text="Load Preset ▾")
        self.preset_menu = tk.Menu(self.preset_btn, tearoff=False, bg=theme.CARD2, fg=theme.FG,
                                   activebackground=theme.ACCENT)
        self.preset_btn["menu"] = self.preset_menu
        self.preset_btn.configure(command=None)
        self.preset_btn.bind("<Button-1>", lambda e: self._fill_presets(), add="+")
        self.preset_btn.pack(side="left", padx=3)
        ttk.Button(btns, text="Revert", command=self.revert).pack(side="left", padx=3)
        ttk.Button(btns, text="Defaults", command=self.reset_all, style="Danger.TButton").pack(side="left", padx=3)

        body = ttk.Frame(r)
        body.pack(side="top", fill="both", expand=True, padx=10)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # sidebar
        side = ttk.Frame(body, padding=(4, 4))
        side.grid(row=0, column=0, sticky="ns")
        self.search = tk.StringVar()
        self.search_entry = ttk.Entry(side, textvariable=self.search, width=24)
        self.search_entry.pack(fill="x", pady=(0, 6))
        self.search_entry.insert(0, "")
        self.search.trace_add("write", lambda *_: self._on_search())
        ttk.Label(side, text="Search (⌘/Ctrl+F)", style="MutedBg.TLabel").pack(anchor="w")
        self.nav = tk.Listbox(side, bg=theme.CARD, fg=theme.FG, selectbackground=theme.ACCENT,
                              selectforeground="#00110F", activestyle="none", highlightthickness=0, bd=0,
                              font=("TkDefaultFont", 13), width=22, height=22, exportselection=False)
        self.nav.pack(fill="y", expand=True, pady=6)
        for t in TABS:
            self.nav.insert("end", "  " + t)
        self.nav.bind("<<ListboxSelect>>", self._on_nav)

        # content
        mid = ttk.Frame(body)
        mid.grid(row=0, column=1, sticky="nsew", padx=6)
        mid.rowconfigure(1, weight=1)
        mid.columnconfigure(0, weight=1)
        self.header = ttk.Label(mid, text="", style="Header.TLabel")
        self.header.grid(row=0, column=0, sticky="w", pady=(4, 6))
        self.canvas = tk.Canvas(mid, bg=theme.BG, highlightthickness=0, bd=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.canvas.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=sb.set)
        self.inner = ttk.Frame(self.canvas)
        self._inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._inner_id, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))

        # right panel
        right = ttk.Frame(body, padding=(6, 4))
        right.grid(row=0, column=2, sticky="ns")
        pv = ttk.LabelFrame(right, text="Live preview", style="Card.TLabelframe", padding=6)
        pv.pack(fill="x")
        self.pv_size = 340
        self.preview = tk.Canvas(pv, width=self.pv_size, height=self.pv_size, bg="#000000", highlightthickness=0)
        self.preview.pack()
        tel = ttk.LabelFrame(right, text="Game telemetry", style="Card.TLabelframe", padding=8)
        tel.pack(fill="x", pady=8)
        self.tel_labels = {}
        for key in ("state", "time", "scores", "balls", "effects", "inputs", "fps", "text"):
            row = ttk.Frame(tel, style="Card.TFrame")
            row.pack(fill="x")
            ttk.Label(row, text=key.capitalize(), style="Muted.TLabel", width=8).pack(side="left")
            lb = ttk.Label(row, text="—", style="Card.TLabel", wraplength=250, justify="left")
            lb.pack(side="left", fill="x")
            self.tel_labels[key] = lb
        act = ttk.LabelFrame(right, text="Test actions (game must be running)", style="Card.TLabelframe", padding=8)
        act.pack(fill="x")
        rowa = ttk.Frame(act, style="Card.TFrame")
        rowa.pack(fill="x", pady=2)
        self.spawn_var = tk.StringVar(value="expand")
        ttk.Combobox(rowa, textvariable=self.spawn_var, values=list(registry.all_types()), state="readonly",
                     width=18).pack(side="left")
        ttk.Button(rowa, text="Spawn orb",
                   command=lambda: self.link.command("spawn_powerup", id=self.spawn_var.get())).pack(side="left", padx=4)
        rowb = ttk.Frame(act, style="Card.TFrame")
        rowb.pack(fill="x", pady=2)
        for text, cmd in (("Extra ball", "spawn_ball"), ("Debug F3", "toggle_debug"), ("Calibrate F2", "toggle_calibration")):
            ttk.Button(rowb, text=text, command=lambda c=cmd: self.link.command(c)).pack(side="left", padx=2)
        rowc = ttk.Frame(act, style="Card.TFrame")
        rowc.pack(fill="x", pady=2)
        ttk.Button(rowc, text="Apply display settings", command=lambda: self.link.command("apply_display")).pack(side="left", padx=2)
        ttk.Button(rowc, text="Quit game", command=lambda: self.link.command("quit")).pack(side="left", padx=2)

        foot = ttk.Frame(r, padding=(14, 6))
        foot.pack(side="bottom", fill="x")
        self.status_lbl = ttk.Label(foot, text="Ready", style="Status.TLabel")
        self.status_lbl.pack(side="left")
        self.dirty_lbl = ttk.Label(foot, text="", style="Status.TLabel")
        self.dirty_lbl.pack(side="right")
        self.warn_lbl = tk.Label(foot, text="", bg=theme.BG, fg=theme.WARN)
        self.warn_lbl.pack(side="right", padx=16)

    def _wheel(self, e):
        d = e.delta
        if abs(d) >= 120:
            d = d / 120
        self.canvas.yview_scroll(int(-d * (1 if sys.platform == "darwin" else 3)), "units")

    # ================================================================== tabs
    def _on_nav(self, _e=None) -> None:
        sel = self.nav.curselection()
        if not sel:
            return
        name = self.nav.get(sel[0]).strip()
        if name == SEARCH_TAB.strip():
            self._on_search()
            return
        self.show_tab(name)

    def _clear(self) -> None:
        for w in self.inner.winfo_children():
            w.destroy()
        self.rows.clear()
        self.canvas.yview_moveto(0)

    def show_tab(self, tab: str) -> None:
        self.current_tab = tab
        self._clear()
        self.header.configure(text=tab)
        if tab in TABS:
            i = TABS.index(tab) + (1 if self.nav.get(0).strip() == SEARCH_TAB.strip() else 0)
            self.nav.selection_clear(0, "end")
            self.nav.selection_set(i)
        params = [p for p in self.schema.values() if p.tab == tab]
        groups: dict[str, list] = {}
        for p in params:
            groups.setdefault(p.group, []).append(p)
        linked = self.cfg["paddles.link_players"]
        for gname, plist in groups.items():
            if tab == "Paddles" and linked and gname.startswith("Player 2"):
                continue
            self._group(gname, plist)
        if tab == "Paddles" and linked:
            note = ttk.Label(self.inner, text="Player 2 uses Player 1's paddle settings. Turn off "
                                              "'Same settings for both players' to edit Player 2 separately.",
                             style="MutedBg.TLabel", wraplength=700)
            note.pack(anchor="w", pady=8)
        if tab == "Power-ups":
            ttk.Label(self.inner, text="Add a power-up: drop a file in market_hockey/powerups/types/ — it appears "
                                       "here automatically.", style="MutedBg.TLabel").pack(anchor="w", pady=8)

    def _group(self, title: str, plist: list) -> None:
        lf = ttk.LabelFrame(self.inner, text=title, style="Card.TLabelframe", padding=(4, 6))
        lf.pack(fill="x", pady=6, padx=2)
        lf.columnconfigure(1, weight=1)
        for row, p in enumerate(plist):
            self.rows[p.path] = SettingRow(lf, self, p, row)

    def _on_search(self) -> None:
        q = self.search.get().strip().lower()
        has_tab = self.nav.get(0).strip() == SEARCH_TAB.strip()
        if not q:
            if has_tab:
                self.nav.delete(0)
                self.show_tab(self.current_tab if self.current_tab in TABS else TABS[0])
            return
        if not has_tab:
            self.nav.insert(0, "  " + SEARCH_TAB)
        self.nav.selection_clear(0, "end")
        self.nav.selection_set(0)
        self._clear()
        hits = [p for p in self.schema.values()
                if q in p.label.lower() or q in p.path.lower() or q in p.group.lower() or q in p.help.lower()]
        self.header.configure(text=f"{len(hits)} settings match “{q}”")
        groups: dict[str, list] = {}
        for p in hits[:150]:
            groups.setdefault(f"{p.tab} › {p.group}", []).append(p)
        for gname, plist in groups.items():
            self._group(gname, plist)

    # ================================================================== changes
    def on_change(self, p, value, record_undo: bool = True):
        old = self.cfg[p.path]
        ok, v, warn = self.cfg.set(p.path, value)
        if v != old:
            if record_undo:
                self.undo.append((p.path, old))
                del self.undo[:-200]
            self.pending[p.path] = v
            self._mark_dirty()
            self.schedule_preview()
            if p.path == "paddles.link_players" and self.current_tab == "Paddles":
                self.root.after(50, lambda: self.show_tab("Paddles"))
            if p.path.startswith("colors."):
                self._update_warnings()
        if warn:
            self.status(warn, warn=True)
        return v

    def flush(self) -> None:
        if self.pending:
            vals, self.pending = self.pending, {}
            if len(vals) == 1:
                (path, v), = vals.items()
                self.link.set(path, v)
            else:
                self.link.set_many(vals)
        self.root.after(33, self.flush)

    def push_all(self) -> None:
        self.link.set_many(self.cfg.snapshot())

    def _mark_dirty(self) -> None:
        dirty = self.cfg.values != self.saved
        self.dirty_lbl.configure(text="● unsaved changes" if dirty else "all changes saved",
                                 foreground=theme.ORANGE if dirty else theme.MUTED)

    def _refresh_rows(self) -> None:
        for path, row in self.rows.items():
            row.set_value(self.cfg[path])
        self._mark_dirty()
        self.schedule_preview()
        self._update_warnings()

    def undo_last(self) -> None:
        if not self.undo:
            self.status("Nothing to undo")
            return
        path, old = self.undo.pop()
        self.on_change(self.schema[path], old, record_undo=False)
        if path in self.rows:
            self.rows[path].set_value(self.cfg[path])
        self.status(f"Undid {path}")

    # ================================================================== file actions
    def save(self) -> None:
        try:
            self.cfg.save(SETTINGS_PATH, BACKUP_PATH)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.root)
            return
        self.saved = self.cfg.snapshot()
        self._mark_dirty()
        self.status(f"Saved {time.strftime('%H:%M:%S')} → {SETTINGS_PATH.relative_to(ROOT)}")

    def save_preset(self) -> None:
        name = simpledialog.askstring("Save preset", "Preset name:", parent=self.root)
        if not name:
            return
        safe = re.sub(r"[^A-Za-z0-9_\-]+", "_", name.strip()).strip("_") or "preset"
        PRESETS_DIR.mkdir(parents=True, exist_ok=True)
        self.cfg.save(PRESETS_DIR / f"{safe}.json")
        self.status(f"Preset saved → config/presets/{safe}.json")

    def _fill_presets(self) -> None:
        self.preset_menu.delete(0, "end")
        files = sorted(PRESETS_DIR.glob("*.json")) if PRESETS_DIR.exists() else []
        if not files:
            self.preset_menu.add_command(label="(no presets)", state="disabled")
        for f in files:
            self.preset_menu.add_command(label=f.stem, command=lambda f=f: self.load_preset(f))

    def load_preset(self, path) -> None:
        try:
            pc = Config.load(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Preset", str(exc), parent=self.root)
            return
        self.cfg.update(pc.values)
        self.push_all()
        self._refresh_rows()
        self.status(f"Loaded preset {path.stem} (not saved yet; press Save to keep it)")

    def revert(self) -> None:
        loaded = Config.load(SETTINGS_PATH)
        self.cfg.update(loaded.values)
        self.saved = self.cfg.snapshot()
        self.push_all()
        self._refresh_rows()
        self.status("Reverted to the saved settings")

    def reset_all(self) -> None:
        if not messagebox.askyesno("Reset all settings",
                                   "Reset every setting to its default value?\n(Nothing is written until you press Save.)",
                                   parent=self.root):
            return
        self.cfg.reset_defaults()
        self.push_all()
        self._refresh_rows()
        self.status("All settings reset to defaults (press Save to keep)")

    def launch_game(self) -> None:
        if self.game_proc is not None and self.game_proc.poll() is None:
            self.status("The game is already running from this panel")
            return
        args = [sys.executable, str(ROOT / "main.py")]
        if self.windowed.get():
            args.append("--windowed")
        try:
            self.game_proc = subprocess.Popen(args, cwd=str(ROOT))
            self.status("Launching the game… (it reads config/settings.json; unsaved edits are pushed when it connects)")
        except OSError as exc:
            messagebox.showerror("Launch failed", str(exc), parent=self.root)

    # ================================================================== status / preview / telemetry
    def status(self, text: str, warn: bool = False) -> None:
        self.status_lbl.configure(text=text, foreground=theme.WARN if warn else theme.MUTED)

    def _update_warnings(self, extra: list[str] | None = None) -> None:
        warns = color_warnings(self.cfg) + (extra or self._layout_warnings)
        self.warn_lbl.configure(text=("⚠ " + " · ".join(warns[:3])) if warns else "")

    _layout_warnings: list = []

    def schedule_preview(self) -> None:
        if self._preview_job is None:
            self._preview_job = self.root.after(60, self.redraw_preview)

    def redraw_preview(self) -> None:
        self._preview_job = None
        try:
            self._layout_warnings = draw_preview(self.preview, self.cfg, self.pv_size)
        except Exception as exc:  # noqa: BLE001 - a bad value must never kill the panel
            self._layout_warnings = [f"preview error: {exc}"]
        self._update_warnings(self._layout_warnings)

    def poll(self) -> None:
        now = time.monotonic()
        if now - self._last_hello > 1.0:
            self._last_hello = now
            self.link.hello()
        for msg in self.link.poll():
            if msg.get("type") == "state":
                self.telemetry = msg
            elif msg.get("type") == "ack" and msg.get("warning"):
                self.status(f"Game: {msg['warning']}", warn=True)
        connected = self.link.connected
        if connected and not self.was_connected:
            self.push_all()  # the game mirrors the panel (including unsaved edits)
            self.status("Connected to the game — all current values pushed")
        self.was_connected = connected
        if connected:
            self.pill.configure(text="● Connected to game (live)", bg="#0E3B33", fg=theme.GOOD)
            t = self.telemetry
            self.tel_labels["state"].configure(text=f"{t.get('state')}{' (paused)' if t.get('paused') else ''}  phase {t.get('phase')}")
            self.tel_labels["time"].configure(text="golden goal" if t.get("golden") else f"{t.get('time_left')} s")
            sc = t.get("scores", [0, 0])
            self.tel_labels["scores"].configure(text=f"P1 {sc[0]}  —  P2 {sc[1]}")
            self.tel_labels["balls"].configure(text=f"{t.get('balls')} balls · {t.get('orbs')} orbs")
            effs = t.get("effects") or []
            self.tel_labels["effects"].configure(
                text=", ".join(f"{e['id']} {e['left']}s" for e in effs) if effs else "—")
            ins = t.get("inputs") or []
            self.tel_labels["inputs"].configure(text="   ".join(
                f"P{i + 1} {d['u']:.2f}{'' if d['present'] else ' (absent)'}" for i, d in enumerate(ins)))
            self.tel_labels["fps"].configure(text=str(t.get("fps")))
            self.tel_labels["text"].configure(text=str(t.get("text_backend")))
        else:
            self.pill.configure(text="○ Game offline — editing file", bg=theme.CARD2, fg=theme.MUTED)
        self.root.after(100, self.poll)

    def on_close(self) -> None:
        if self.cfg.values != self.saved:
            ans = messagebox.askyesnocancel("Unsaved changes", "Save changes to config/settings.json before closing?",
                                            parent=self.root)
            if ans is None:
                return
            if ans:
                self.save()
        self.link.close()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ControlPanel(root)
    root.mainloop()
