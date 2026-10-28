from ..base import PowerUpType
from ..registry import register


@register
class DoubleBall(PowerUpType):
    """Trading volume («حجم معاملات»): a second ball appears where the orb was collected.

    It spawns half a second late, is smaller, and starts slow, so it trails far behind the first ball and the
    opponent can deal with both (an instant twin was almost a guaranteed point).
    """
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
        sb.e(f"{p}.mode", "delayed", ("delayed", "instant"), "Mode", "instant = the old immediate split.")
        sb.i(f"{p}.extra_balls", 1, 1, 3, 1, "", "Extra balls")
        sb.f(f"{p}.spawn_delay_s", 0.5, 0, 3, 0.05, "s", "Spawn delay")
        sb.f(f"{p}.radius_scale", 0.72, 0.3, 1.2, 0.01, "×", "Second ball size")
        sb.f(f"{p}.slow_mult", 0.45, 0.1, 1.0, 0.01, "×", "Second ball starting speed")
        sb.f(f"{p}.slow_s", 0.6, 0, 3, 0.05, "s", "Slow start duration")
        sb.f(f"{p}.split_angle_deg", 24, 2, 60, 1, "°", "Split angle")
        sb.f(f"{p}.extra_lifetime_s", 10, 1, 60, 0.5, "s", "Extra ball lifetime")

    def collect(self, engine, ball, collector):
        cfg = engine.cfg
        if self.p(cfg, "mode") == "instant":
            engine.split_ball(ball, self.p(cfg, "extra_balls"), self.p(cfg, "split_angle_deg"),
                              self.p(cfg, "extra_lifetime_s"))
        else:
            keys = ("extra_balls", "spawn_delay_s", "radius_scale", "slow_mult", "slow_s", "split_angle_deg",
                    "extra_lifetime_s")
            engine.schedule_extra_ball(ball, collector, {k: self.p(cfg, k) for k in keys})
        return {"affects": ("ball", ball.id)}
