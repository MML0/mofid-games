"""Setting rows generated from schema Params."""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk

from . import theme

WIDGET_FOR_KIND = {"float": "scale", "int": "scale", "bool": "check", "color": "color", "enum": "combo",
                   "font": "combo", "str": "entry", "key": "key"}

TK_TO_PYGAME = {"return": "return", "kp_enter": "enter", "shift_l": "left shift", "shift_r": "right shift",
                "control_l": "left ctrl", "control_r": "right ctrl", "alt_l": "left alt", "alt_r": "right alt",
                "space": "space", "tab": "tab", "backspace": "backspace", "escape": "escape"}


def widget_kind(p) -> str:
    return WIDGET_FOR_KIND[p.kind]


def decimals(step) -> int:
    if step is None or step >= 1:
        return 0
    s = f"{step:.6f}".rstrip("0")
    return min(4, len(s.split(".")[1])) if "." in s else 0


def fmt(p, v) -> str:
    if p.kind == "int":
        return str(int(v))
    return f"{float(v):.{decimals(p.step)}f}"


class Tooltip:
    def __init__(self, widget, text: str):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _e=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left", bg="#05141B", fg=theme.FG, padx=8, pady=5,
                 wraplength=420, relief="solid", bd=1).pack()

    def hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class SettingRow:
    def __init__(self, parent, panel, p, row: int):
        self.p = p
        self.panel = panel
        self._mute = False
        value = panel.cfg[p.path]
        lbl = ttk.Label(parent, text=p.label, style="Card.TLabel")
        lbl.grid(row=row, column=0, sticky="w", padx=(12, 8), pady=3)
        Tooltip(lbl, (p.help + "\n\n" if p.help else "") + p.path)
        kind = widget_kind(p)
        self.kind = kind
        if kind == "scale":
            self.var = tk.DoubleVar(value=float(value))
            self.svar = tk.StringVar(value=fmt(p, value))
            self.scale = ttk.Scale(parent, from_=p.min, to=p.max, orient="horizontal", variable=self.var,
                                   command=self._on_scale, length=250)
            self.scale.grid(row=row, column=1, sticky="ew", padx=4)
            self.entry = ttk.Entry(parent, textvariable=self.svar, width=9, justify="right")
            self.entry.grid(row=row, column=2, sticky="w", padx=4)
            self.entry.bind("<Return>", self._on_entry)
            self.entry.bind("<FocusOut>", self._on_entry)
        elif kind == "check":
            self.var = tk.BooleanVar(value=bool(value))
            ttk.Checkbutton(parent, variable=self.var, command=lambda: self.apply(self.var.get())).grid(
                row=row, column=1, sticky="w", padx=4)
        elif kind == "combo":
            self.var = tk.StringVar(value=str(value))
            cb = ttk.Combobox(parent, textvariable=self.var, values=list(p.options), state="readonly", width=24)
            cb.grid(row=row, column=1, sticky="w", padx=4)
            cb.bind("<<ComboboxSelected>>", lambda _e: self.apply(self.var.get()))
        elif kind == "color":
            self.var = tk.StringVar(value=str(value))
            self.swatch = tk.Label(parent, bg=value, width=6, relief="flat", cursor="hand2", bd=0)
            self.swatch.grid(row=row, column=1, sticky="w", padx=4, ipady=3)
            self.swatch.bind("<Button-1>", self._pick)
            self.entry = ttk.Entry(parent, textvariable=self.var, width=9)
            self.entry.grid(row=row, column=2, sticky="w", padx=4)
            self.entry.bind("<Return>", lambda _e: self.apply(self.var.get()))
            self.entry.bind("<FocusOut>", lambda _e: self.apply(self.var.get()))
        elif kind == "entry":
            self.var = tk.StringVar(value=str(value))
            ent = ttk.Entry(parent, textvariable=self.var, width=36, justify="right" if p.rtl else "left")
            ent.grid(row=row, column=1, columnspan=2, sticky="ew", padx=4)
            ent.bind("<Return>", lambda _e: self.apply(self.var.get()))
            ent.bind("<FocusOut>", lambda _e: self.apply(self.var.get()))
        elif kind == "key":
            self.var = tk.StringVar(value=str(value))
            self.btn = ttk.Button(parent, textvariable=self.var, command=self._capture, width=14)
            self.btn.grid(row=row, column=1, sticky="w", padx=4)
        ttk.Label(parent, text=p.unit, style="Muted.TLabel").grid(row=row, column=3, sticky="w", padx=(2, 6))
        rb = ttk.Button(parent, text="↺", style="Small.TButton", width=2, command=self.reset)
        rb.grid(row=row, column=4, padx=2)
        Tooltip(rb, f"Reset to default ({p.default})")
        badge = tk.Label(parent, text="●", bg=theme.CARD, fg=theme.GOOD if p.live else theme.ORANGE)
        badge.grid(row=row, column=5, padx=(2, 10))
        Tooltip(badge, "Applies live" if p.live else "Applies on restart / next match")

    # ---- events -----------------------------------------------------------------
    def _snap(self, v: float) -> float:
        p = self.p
        step = p.step or 1
        v = round((v - p.min) / step) * step + p.min
        v = min(max(v, p.min), p.max)
        return int(round(v)) if p.kind == "int" else round(v, decimals(step) + 1)

    def _on_scale(self, _s):
        if self._mute:
            return
        v = self._snap(self.var.get())
        self.svar.set(fmt(self.p, v))
        self.apply(v, from_scale=True)

    def _on_entry(self, _e=None):
        try:
            v = float(self.svar.get().replace(",", "."))
        except ValueError:
            self.entry.configure(style="Bad.TEntry")
            self.panel.status(f"'{self.svar.get()}' is not a number", warn=True)
            return
        self.entry.configure(style="TEntry")
        self.apply(v)

    def _pick(self, _e=None):
        res = colorchooser.askcolor(color=self.var.get(), parent=self.swatch, title=self.p.label)
        if res and res[1]:
            self.apply(res[1])

    def _capture(self):
        self.var.set("press a key…")
        top = self.btn.winfo_toplevel()

        def on_key(e):
            top.unbind("<KeyPress>", bid)
            name = TK_TO_PYGAME.get(e.keysym.lower(), e.keysym.lower())
            self.apply(name)

        bid = top.bind("<KeyPress>", on_key)

    def apply(self, value, from_scale=False):
        v = self.panel.on_change(self.p, value)
        self.set_value(v, keep_scale=from_scale)

    def reset(self):
        self.apply(self.p.default)

    def set_value(self, v, keep_scale=False):
        self._mute = True
        try:
            if self.kind == "scale":
                if not keep_scale:
                    self.var.set(float(v))
                self.svar.set(fmt(self.p, v))
                self.entry.configure(style="TEntry")
            elif self.kind == "color":
                self.var.set(v)
                try:
                    self.swatch.configure(bg=v)
                except tk.TclError:
                    pass
            else:
                self.var.set(v)
        finally:
            self._mute = False


class ScrollFrame(ttk.Frame):
    """Vertical scrolling without a Canvas.

    Tk 9 on macOS lays out widgets embedded in a Canvas window item in roughly quadratic time (140 rows took
    ~16 s and froze the panel), so the content frame is simply `place`d inside a clipping viewport and moved.
    """

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.viewport = ttk.Frame(self)
        self.viewport.pack(side="left", fill="both", expand=True)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self._on_scrollbar)
        self.sb.pack(side="right", fill="y")
        self.inner = ttk.Frame(self.viewport)
        self.inner.place(x=0, y=0, relwidth=1.0)
        self.offset = 0.0
        self.inner.bind("<Configure>", lambda e: self._sync())
        self.viewport.bind("<Configure>", lambda e: self._sync())

    def _limits(self):
        h = max(1, self.inner.winfo_reqheight())
        vh = max(1, self.viewport.winfo_height())
        return h, vh

    def _sync(self):
        h, vh = self._limits()
        self.offset = max(0.0, min(self.offset, max(0.0, h - vh)))
        self.inner.place_configure(y=-int(self.offset))
        if h <= vh:
            self.sb.set(0.0, 1.0)
        else:
            self.sb.set(self.offset / h, (self.offset + vh) / h)

    def _on_scrollbar(self, *args):
        h, vh = self._limits()
        if args and args[0] == "moveto":
            self.offset = float(args[1]) * h
        elif args and args[0] == "scroll":
            n = int(args[1])
            self.offset += n * (vh * 0.9 if args[2] == "pages" else 40)
        self._sync()

    def scroll_units(self, n: float):
        self.offset += n * 40
        self._sync()

    def to_top(self):
        self.offset = 0.0
        self._sync()
