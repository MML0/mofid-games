"""Base class for power-up types.

To add a power-up: create one file in `market_hockey/powerups/types/`, subclass `PowerUpType`, decorate it
with `@register`, and implement `collect()`. Its settings appear in config/settings.json and in the control
panel automatically. To remove one, switch it off in the panel (or delete the file).
"""

from __future__ import annotations

from .effects import Effect


class PowerUpType:
    id = ""
    name = ""
    order = 100
    icon = ""  # procedural icon name (render/icons.py); assets/icons/<id>.png overrides it
    default_class = "good"  # good = helps the collector (green); bad = helps the opponent (red)
    default_enabled = True
    duration = 6.0
    has_duration = True
    weight = 1.0
    unlock_phase = 1  # 1 = early, 2 = mid, 3 = peak
    stacking = "refresh"
    group: str | None = None
    toast_c = ""  # message on the collector's side
    toast_o = ""  # message on the opponent's side
    banner = False  # also show the collector message as a central banner

    # ---- schema ---------------------------------------------------------------
    def add_schema(self, sb) -> None:
        p = f"powerups.types.{self.id}"
        sb.section("Power-ups", f"{self.order:02d} · {self.name}")
        sb.b(f"{p}.enabled", self.default_enabled, "Enabled")
        sb.e(f"{p}.class", self.default_class, ("good", "bad", "neutral"), "Color class",
             "good = green (helps whoever collects it), bad = red (helps the opponent).")
        sb.f(f"{p}.weight", self.weight, 0, 10, 0.1, "", "Spawn weight")
        if self.has_duration:
            sb.f(f"{p}.duration_s", self.duration, 0.5, 30, 0.5, "s", "Duration")
        sb.i(f"{p}.unlock_phase", self.unlock_phase, 1, 3, 1, "", "Unlocks in phase", "1 = early, 2 = mid, 3 = peak.")
        sb.e(f"{p}.stacking", self.stacking, ("refresh", "extend", "stack", "ignore"), "If collected again")
        sb.i(f"{p}.max_stack", 3, 1, 5, 1, "", "Max stack")
        sb.f(f"{p}.cooldown_s", 3.0, 0, 60, 0.5, "s", "Re-spawn cooldown")
        sb.s(f"{p}.toast_collector", self.toast_c, "Message (collector side)", rtl=True)
        sb.s(f"{p}.toast_opponent", self.toast_o, "Message (opponent side)", rtl=True)
        self.extra_schema(sb, p)

    def extra_schema(self, sb, p: str) -> None:
        pass

    def p(self, cfg, key: str):
        return cfg[f"powerups.types.{self.id}.{key}"]

    def effect(self, engine, kind: str, target: tuple, value: float = 1.0, collector=None, group=None, **data) -> Effect:
        dur = self.p(engine.cfg, "duration_s") if self.has_duration else 0.0
        return Effect(type_id=self.id, kind=kind, target=target, duration=dur, remaining=dur, value=value,
                      group=group if group is not None else self.group, collector=collector, data=data)

    # ---- behavior ---------------------------------------------------------------
    def collect(self, engine, ball, collector: int) -> dict:
        """Apply the power-up. Return {"affects": ("player", idx) | ("ball", id)} for the visuals."""
        raise NotImplementedError
