from ..base import PowerUpType
from ..registry import register


@register
class TrajectoryReveal(PowerUpType):
    """RED: it shows the collector's OPPONENT where the ball will meet their paddle and how it will bounce."""
    id = "trajectory_reveal"
    name = "Trajectory reveal (for opponent)"
    order = 6
    icon = "trajectory"
    default_class = "bad"
    duration = 7.0
    unlock_phase = 2
    toast_c = "مسیرت لو رفت!"
    toast_o = "مسیر حرکت را تحلیل کن!"

    def collect(self, engine, ball, collector):
        opp = 1 - collector
        engine.add_effect(self, self.effect(engine, "reveal", ("player", opp), 1.0, collector))
        engine.request_prediction()
        return {"affects": ("player", opp)}
