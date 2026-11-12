from ..base import PowerUpType
from ..registry import register


@register
class Shield(PowerUpType):
    """Circuit breaker: a barrier over the collector's goal blocks one ball."""
    id = "shield"
    name = "Shield (Circuit breaker)"
    order = 9
    icon = "shield"
    default_class = "good"
    default_enabled = False
    duration = 8.0
    unlock_phase = 2
    toast_c = "حد نوسان فعال شد!"

    def extra_schema(self, sb, p):
        sb.f(f"{p}.coverage_percent", 100, 20, 100, 1, "%", "Goal coverage")
        sb.i(f"{p}.charges", 1, 1, 5, 1, "", "Blocks")

    def collect(self, engine, ball, collector):
        cfg = engine.cfg
        engine.add_effect(self, self.effect(engine, "shield", ("player", collector), 1.0, collector,
                                            charges=self.p(cfg, "charges"),
                                            coverage=self.p(cfg, "coverage_percent")))
        return {"affects": ("player", collector)}
