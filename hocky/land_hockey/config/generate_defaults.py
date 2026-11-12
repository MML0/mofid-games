"""Generate config/defaults.json and docs/CONFIG_REFERENCE.md from the schema.

    python -m land_hockey.config.generate_defaults
"""

from __future__ import annotations

from ..paths import DEFAULTS_PATH, DOCS_DIR, SETTINGS_PATH, PRESETS_DIR
from .schema import TABS, get_schema
from .store import Config

PRESETS = {
    "default": {},
    "kids_easy": {
        "ball.serve_speed": 340, "ball.base_speed": 420, "ball.max_speed": 1000, "ball.rally_cap": 1.3,
        "paddles.p1.width": 170, "paddles.p2.width": 170, "paddles.p1.aim_blend": 0.6, "paddles.p2.aim_blend": 0.6,
        "match.score_limit": 5, "input.ai.difficulty": 0.35,
    },
    "pro": {
        "ball.serve_speed": 520, "ball.base_speed": 660, "ball.max_speed": 1900, "ball.rally_gain_per_hit": 1.045,
        "paddles.p1.width": 115, "paddles.p2.width": 115, "paddles.p1.aim_blend": 0.15, "paddles.p2.aim_blend": 0.15,
        "match.score_limit": 9, "input.ai.difficulty": 0.85,
    },
    "calibration": {
        "debug.calibration": True, "match.attract_demo": False, "powerups.enabled": False, "fx.ambient_chart": False,
    },
}


def write_reference(path) -> None:
    schema = get_schema()
    lines = ["# Land Hockey: configuration reference", "",
             "Generated from `land_hockey/config/schema.py`. Every key lives in `config/settings.json` "
             "and is editable in the control panel (`python settings_app.py`).", "",
             "Live = applies instantly while the game runs; restart = applies on the next launch.", ""]
    for tab in TABS:
        params = [p for p in schema.values() if p.tab == tab]
        if not params:
            continue
        lines += [f"## {tab}", "", "| Key | Default | Range / options | Live | Description |", "|---|---|---|---|---|"]
        for p in params:
            if p.kind in ("float", "int"):
                rng = f"{p.min} … {p.max} {p.unit}".strip()
            elif p.options:
                rng = ", ".join(p.options[:8]) + (" …" if len(p.options) > 8 else "")
            else:
                rng = p.kind
            desc = (p.label + (" — " + p.help if p.help else "")).replace("|", "/")
            default = str(p.default).replace("|", "/")
            lines.append(f"| `{p.path}` | {default} | {rng} | {'live' if p.live else 'restart'} | {desc} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    cfg = Config()
    cfg.save(DEFAULTS_PATH)
    if not SETTINGS_PATH.exists():
        cfg.save(SETTINGS_PATH)
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    for name, values in PRESETS.items():
        pc = Config(values)
        pc.save(PRESETS_DIR / f"{name}.json")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    write_reference(DOCS_DIR / "CONFIG_REFERENCE.md")
    print(f"wrote {DEFAULTS_PATH}, presets, and docs/CONFIG_REFERENCE.md ({len(get_schema())} settings)")


if __name__ == "__main__":
    main()
