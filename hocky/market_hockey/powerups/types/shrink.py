from ..base import PowerUpType
from ..registry import register


@register
class Shrink(PowerUpType):
    """Green: it shrinks the OPPONENT's paddle, so it is good for whoever collects it."""
    id = "shrink"
    name = "Shrink opponent's paddle"
    order = 2
    icon = "shrink"
    default_class = "good"
    duration = 8.0
    unlock_phase = 1
    toast_c = "بالکر حریف کوچک شد!"
    toast_o = "بالکرت کوچک شد!"

    def extra_schema(self, sb, p):
        sb.f(f"{p}.multiplier", 0.6, 0.2, 0.95, 0.05, "×", "Size multiplier")

    def collect(self, engine, ball, collector):
        opp = 1 - collector
        engine.add_effect(self, self.effect(engine, "paddle_size", ("player", opp),
                                            self.p(engine.cfg, "multiplier"), collector))
        return {"affects": ("player", opp)}
