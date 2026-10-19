from ..base import PowerUpType
from ..registry import register


@register
class Expand(PowerUpType):
    id = "expand"
    name = "Expand my paddle"
    order = 1
    icon = "expand"
    default_class = "good"
    duration = 8.0
    unlock_phase = 1
    toast_c = "بالکرت بزرگ شد!"

    def extra_schema(self, sb, p):
        sb.f(f"{p}.multiplier", 1.5, 1.05, 3.0, 0.05, "×", "Size multiplier")

    def collect(self, engine, ball, collector):
        engine.add_effect(self, self.effect(engine, "paddle_size", ("player", collector),
                                            self.p(engine.cfg, "multiplier"), collector))
        return {"affects": ("player", collector)}
