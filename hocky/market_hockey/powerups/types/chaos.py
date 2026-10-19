from ..base import PowerUpType
from ..registry import register


@register
class Chaos(PowerUpType):
    """Random path: the ball's direction jumps (instant) or curves (wobble), always toward the opponent."""
    id = "chaos"
    name = "Random path"
    order = 4
    icon = "chaos"
    default_class = "good"
    duration = 2.5
    unlock_phase = 2
    toast_c = "بازار غیرقابل پیش‌بینی شد!"
    banner = True

    def extra_schema(self, sb, p):
        sb.e(f"{p}.mode", "instant", ("instant", "wobble"), "Mode", "wobble uses Duration as its length.")
        sb.f(f"{p}.min_angle_deg", 20, 0, 90, 1, "°", "Min turn")
        sb.f(f"{p}.max_angle_deg", 55, 0, 90, 1, "°", "Max turn")
        sb.f(f"{p}.wobble_deg_s", 140, 10, 600, 5, "°/s", "Wobble strength")
        sb.f(f"{p}.wobble_hz", 1.6, 0.2, 6, 0.1, "Hz", "Wobble frequency")

    def collect(self, engine, ball, collector):
        cfg = engine.cfg
        if self.p(cfg, "mode") == "wobble":
            engine.add_effect(self, self.effect(engine, "wobble", ("ball", ball.id), 1.0, collector,
                                                amp=self.p(cfg, "wobble_deg_s"), hz=self.p(cfg, "wobble_hz"),
                                                phase=engine.rng.random() * 6.283))
        else:
            engine.chaos_deflect(ball, collector, self.p(cfg, "min_angle_deg"), self.p(cfg, "max_angle_deg"))
        return {"affects": ("ball", ball.id)}
