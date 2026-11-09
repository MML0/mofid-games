from ..base import PowerUpType
from ..registry import register


@register
class SpeedUp(PowerUpType):
    """High volatility: the ball speeds up on its way to the opponent."""
    id = "speed_up"
    name = "Speed up (High volatility)"
    order = 3
    icon = "speed_up"
    default_class = "good"
    duration = 6.0
    unlock_phase = 1
    group = "ball_speed"
    toast_c = "نوسان بازار افزایش یافت!"
    float_text = "زیاد شدن سرعت"
    glow = "#D4B96F"  # the gold of its صندوق عیار icon
    banner = True

    def extra_schema(self, sb, p):
        sb.f(f"{p}.multiplier", 1.4, 1.05, 3.0, 0.05, "×", "Speed multiplier")
        sb.e(f"{p}.scope", "this_ball", ("this_ball", "all_balls"), "Affects")

    def collect(self, engine, ball, collector):
        target = ("ball", ball.id) if self.p(engine.cfg, "scope") == "this_ball" else ("all",)
        engine.add_effect(self, self.effect(engine, "ball_speed", target, self.p(engine.cfg, "multiplier"), collector))
        return {"affects": ("ball", ball.id)}
