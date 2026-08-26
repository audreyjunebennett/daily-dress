"""A small, readable Minecraft-inspired Tk theme for Daily Dress."""

from __future__ import annotations

import tkinter as tk
from tkinter import font, ttk


COLORS = {
    "void": "#17130F",
    "shadow": "#211B15",
    "panel": "#342B22",
    "panel_alt": "#46392B",
    "slot": "#1E2529",
    "stone": "#7D7D78",
    "stone_dark": "#4E4E4A",
    "cream": "#FFF4D1",
    "muted": "#C8BFA7",
    "grass": "#66A83F",
    "grass_dark": "#3F7629",
    "gold": "#F4C95D",
    "rose": "#D97AAE",
    "water": "#62B5CE",
    "danger": "#B84D52",
}


def _available_font(root: tk.Misc) -> str:
    installed = {name.casefold(): name for name in font.families(root)}
    for candidate in ("Minecraft Seven v2", "Minecraft", "Monocraft", "Bahnschrift SemiBold", "Segoe UI"):
        if candidate.casefold() in installed:
            return installed[candidate.casefold()]
    return "TkDefaultFont"


def apply_minecraft_theme(root: tk.Misc) -> None:
    """Apply the shared blocky palette without requiring a bundled font."""

    family = _available_font(root)
    style = ttk.Style(root)
    style.theme_use("clam")
    root.option_add("*Font", (family, 10))
    root.option_add("*TkFDialog*Font", (family, 10))

    style.configure(".", background=COLORS["panel"], foreground=COLORS["cream"], fieldbackground=COLORS["slot"])
    style.configure("TFrame", background=COLORS["panel"])
    style.configure("Root.TFrame", background=COLORS["void"])
    style.configure("Card.TFrame", background=COLORS["panel_alt"], relief="raised", borderwidth=2)
    style.configure("TLabel", background=COLORS["panel"], foreground=COLORS["cream"])
    style.configure("Title.TLabel", font=(family, 21, "bold"), foreground=COLORS["gold"])
    style.configure("Step.TLabel", font=(family, 12, "bold"), foreground=COLORS["water"])
    style.configure("Muted.TLabel", foreground=COLORS["muted"])
    style.configure("Count.TLabel", foreground=COLORS["gold"], font=(family, 10, "bold"))
    style.configure(
        "TButton",
        background=COLORS["stone"],
        foreground="#151515",
        bordercolor="#B9B9B3",
        darkcolor=COLORS["stone_dark"],
        lightcolor="#A9A9A3",
        padding=(9, 6),
        relief="raised",
        borderwidth=2,
        font=(family, 9, "bold"),
    )
    style.map("TButton", background=[("active", "#9A9A94"), ("pressed", COLORS["stone_dark"]), ("disabled", "#555550")])
    style.configure("Accent.TButton", background=COLORS["grass"], lightcolor="#88C966", darkcolor=COLORS["grass_dark"])
    style.map("Accent.TButton", background=[("active", "#7CBE55"), ("pressed", COLORS["grass_dark"])])
    style.configure("Rose.TButton", background=COLORS["rose"], lightcolor="#F0A5CA", darkcolor="#8C4269")
    style.map("Rose.TButton", background=[("active", "#E88CBD"), ("pressed", "#8C4269")])
    style.configure("Danger.TButton", background=COLORS["danger"], lightcolor="#D87578", darkcolor="#772E33", foreground="white")
    style.configure("TEntry", fieldbackground=COLORS["slot"], foreground=COLORS["cream"], insertcolor=COLORS["cream"], borderwidth=2, padding=5)
    style.configure("TCombobox", fieldbackground=COLORS["slot"], foreground=COLORS["cream"], arrowcolor=COLORS["gold"], padding=4)
    style.map("TCombobox", fieldbackground=[("readonly", COLORS["slot"])], foreground=[("readonly", COLORS["cream"])])
    style.configure("TLabelframe", background=COLORS["panel"], foreground=COLORS["gold"], bordercolor=COLORS["stone_dark"], borderwidth=2, relief="groove")
    style.configure("TLabelframe.Label", background=COLORS["panel"], foreground=COLORS["gold"], font=(family, 10, "bold"))
    style.configure("TCheckbutton", background=COLORS["panel"], foreground=COLORS["cream"], indicatorcolor=COLORS["slot"], padding=2)
    style.map("TCheckbutton", indicatorcolor=[("selected", COLORS["grass"]), ("active", COLORS["water"])])
    style.configure("TRadiobutton", background=COLORS["panel"], foreground=COLORS["cream"], indicatorcolor=COLORS["slot"], padding=2)
    style.map("TRadiobutton", indicatorcolor=[("selected", COLORS["gold"]), ("active", COLORS["water"])])
    style.configure("TScale", background=COLORS["panel"], troughcolor=COLORS["slot"], bordercolor=COLORS["stone_dark"], lightcolor=COLORS["grass"], darkcolor=COLORS["grass_dark"])
    style.configure("TProgressbar", background=COLORS["grass"], troughcolor=COLORS["slot"], bordercolor=COLORS["stone_dark"], thickness=16)
    style.configure("TPanedwindow", background=COLORS["void"])
    style.configure("Vertical.TScrollbar", background=COLORS["stone"], troughcolor=COLORS["slot"], arrowcolor=COLORS["cream"])
    style.configure("Horizontal.TScrollbar", background=COLORS["stone"], troughcolor=COLORS["slot"], arrowcolor=COLORS["cream"])
    try:
        root.configure(background=COLORS["void"])
    except tk.TclError:
        pass
