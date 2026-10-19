from ..base import PowerUpType
from ..registry import register


@register
class BullMarket(PowerUpType):
    """Bull market: the collector's next goal (within the window) is worth more."""
    id = "bull_market"
    name = "Bull market (double points)"
    order = 10
    icon = "bull"
    default_class = "good"
    default_enabled = False
    duration = 12.0
    unlock_phase = 2
    toast_c = "بازار صعودی! گل بعدی دو امتیازی"

    def extra_schema(self, sb, p):
        sb.i(f"{p}.multiplier", 2, 2, 5, 1, "×", "Points multiplier")

    def collect(self, engine, ball, collector):
        engine.add_effect(self, self.effect(engine, "bull", ("player", collector),
                                            self.p(engine.cfg, "multiplier"), collector))
        return {"affects": ("player", collector)}
