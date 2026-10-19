from ..base import PowerUpType
from ..registry import register


@register
class SlowDown(PowerUpType):
    """Market stability. Red by default: slowing your own shot makes it easier for the receiver."""
    id = "slow_down"
    name = "Slow down (Market stability)"
    order = 7
    icon = "slow_down"
    default_class = "bad"
    default_enabled = False
    duration = 6.0
    unlock_phase = 1
    group = "ball_speed"
    toast_c = "بازار وارد دوره‌ی آرام شد."
    banner = True

    def extra_schema(self, sb, p):
        sb.f(f"{p}.multiplier", 0.7, 0.2, 0.95, 0.05, "×", "Speed multiplier")
        sb.e(f"{p}.scope", "this_ball", ("this_ball", "all_balls"), "Affects")

    def collect(self, engine, ball, collector):
        target = ("ball", ball.id) if self.p(engine.cfg, "scope") == "this_ball" else ("all",)
        engine.add_effect(self, self.effect(engine, "ball_speed", target, self.p(engine.cfg, "multiplier"), collector))
        return {"affects": ("ball", ball.id)}
