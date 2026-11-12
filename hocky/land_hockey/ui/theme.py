"""Dark Mofid-branded ttk theme for the control panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BG = "#0B1F2A"
CARD = "#11303F"
CARD2 = "#173B4C"
FIELD = "#0D2836"
FG = "#E6F2F5"
MUTED = "#8FB3C0"
ACCENT = "#00A796"
ACCENT_HI = "#19D3BC"
WARN = "#F3716D"
GOOD = "#39E46F"
ORANGE = "#F0A030"


def apply(root: tk.Tk) -> None:
    root.configure(bg=BG)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        try:
            tkfont.nametofont(name).configure(size=12)
        except tk.TclError:
            pass
    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=BG, foreground=FG, fieldbackground=FIELD, bordercolor=CARD2, lightcolor=CARD2,
                 darkcolor=CARD2, troughcolor=FIELD, focuscolor=ACCENT, insertcolor=FG, selectbackground=ACCENT,
                 selectforeground="#001A17")
    st.configure("TFrame", background=BG)
    st.configure("Card.TFrame", background=CARD)
    st.configure("TLabel", background=BG, foreground=FG)
    st.configure("Card.TLabel", background=CARD, foreground=FG)
    st.configure("Muted.TLabel", background=CARD, foreground=MUTED)
    st.configure("MutedBg.TLabel", background=BG, foreground=MUTED)
    st.configure("Title.TLabel", background=BG, foreground=FG, font=("TkDefaultFont", 17, "bold"))
    st.configure("Header.TLabel", background=BG, foreground=ACCENT_HI, font=("TkDefaultFont", 15, "bold"))
    st.configure("Status.TLabel", background=BG, foreground=MUTED)
    st.configure("TButton", background=CARD2, foreground=FG, borderwidth=0, padding=(10, 5), relief="flat")
    st.map("TButton", background=[("active", "#21526A"), ("pressed", ACCENT)], foreground=[("disabled", MUTED)])
    st.configure("Accent.TButton", background=ACCENT, foreground="#00110F", font=("TkDefaultFont", 12, "bold"))
    st.map("Accent.TButton", background=[("active", ACCENT_HI), ("pressed", ACCENT_HI)])
    st.configure("Danger.TButton", background="#4A2228", foreground=FG)
    st.map("Danger.TButton", background=[("active", "#6B2E36")])
    st.configure("Small.TButton", padding=(4, 1), background=CARD, foreground=MUTED)
    st.map("Small.TButton", background=[("active", CARD2)], foreground=[("active", FG)])
    st.configure("TCheckbutton", background=CARD, foreground=FG, indicatorcolor=FIELD, indicatorbackground=FIELD)
    st.map("TCheckbutton", indicatorcolor=[("selected", ACCENT)], background=[("active", CARD)])
    st.configure("Bg.TCheckbutton", background=BG)
    st.map("Bg.TCheckbutton", background=[("active", BG)], indicatorcolor=[("selected", ACCENT)])
    st.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=FG, padding=3)
    st.configure("Bad.TEntry", fieldbackground="#3A1A1E", foreground=FG)
    st.configure("TCombobox", fieldbackground=FIELD, background=CARD2, foreground=FG, arrowcolor=FG, padding=2)
    st.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)],
           selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", FG)])
    st.configure("Horizontal.TScale", background=ACCENT, troughcolor=FIELD, bordercolor=CARD, lightcolor=ACCENT,
                 darkcolor=ACCENT)
    st.configure("Card.TLabelframe", background=CARD, bordercolor=CARD2, relief="solid", borderwidth=1)
    st.configure("Card.TLabelframe.Label", background=CARD, foreground=ACCENT_HI, font=("TkDefaultFont", 13, "bold"))
    st.configure("Vertical.TScrollbar", background=CARD2, troughcolor=BG, arrowcolor=FG, bordercolor=BG)
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "#00110F")
