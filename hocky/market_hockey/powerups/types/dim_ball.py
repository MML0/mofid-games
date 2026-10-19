from ..base import PowerUpType
from ..registry import register


@register
class DimBall(PowerUpType):
    """Market correction: the ball dims (never invisible; its owner ring stays)."""
    id = "dim_ball"
    name = "Dim ball (Market correction)"
    order = 8
    icon = "dim_ball"
    default_class = "good"
    default_enabled = False
    duration = 5.0
    unlock_phase = 2
    toast_c = "بازار در مسیر اصلاح قرار گرفت."
    banner = True

    def extra_schema(self, sb, p):
        sb.f(f"{p}.alpha", 0.35, 0.05, 1, 0.01, "", "Ball opacity")
        sb.f(f"{p}.min_visibility", 0.25, 0.05, 1, 0.01, "", "Never below")

    def collect(self, engine, ball, collector):
        cfg = engine.cfg
        a = max(self.p(cfg, "alpha"), self.p(cfg, "min_visibility"))
        engine.add_effect(self, self.effect(engine, "dim", ("ball", ball.id), a, collector))
        return {"affects": ("ball", ball.id)}
