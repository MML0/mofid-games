from ..base import PowerUpType
from ..registry import register


@register
class DoubleBall(PowerUpType):
    """Trading volume: the ball splits; every ball keeps its own owner and trail."""
    id = "double_ball"
    name = "Double ball (Trading volume)"
    order = 5
    icon = "double_ball"
    default_class = "good"
    has_duration = False
    unlock_phase = 2
    toast_c = "حجم معاملات افزایش یافت!"
    banner = True

    def extra_schema(self, sb, p):
        sb.i(f"{p}.extra_balls", 1, 1, 3, 1, "", "Extra balls")
        sb.f(f"{p}.split_angle_deg", 18, 2, 60, 1, "°", "Split angle")
        sb.f(f"{p}.extra_lifetime_s", 10, 1, 60, 0.5, "s", "Extra ball lifetime")

    def collect(self, engine, ball, collector):
        cfg = engine.cfg
        engine.split_ball(ball, self.p(cfg, "extra_balls"), self.p(cfg, "split_angle_deg"),
                          self.p(cfg, "extra_lifetime_s"))
        return {"affects": ("ball", ball.id)}
