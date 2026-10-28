from ..base import PowerUpType
from ..registry import register


@register
class TrajectoryReveal(PowerUpType):
    """Market analysis: shows where the ball will meet a paddle and how it will bounce off.

    By default it helps the COLLECTOR (green): when the ball comes back, they see where it lands on their paddle.
    Set "Who sees the path" to opponent (and the class to bad/red) for the reverse rule.
    """
    id = "trajectory_reveal"
    name = "Trajectory reveal (aim assist)"
    order = 6
    icon = "trajectory"
    default_class = "good"
    duration = 12.0
    unlock_phase = 2
    toast_c = "مسیر حرکت را تحلیل کن!"
    toast_o = ""

    def extra_schema(self, sb, p):
        sb.e(f"{p}.beneficiary", "collector", ("collector", "opponent"), "Who sees the path")

    def collect(self, engine, ball, collector):
        ben = collector if self.p(engine.cfg, "beneficiary") == "collector" else 1 - collector
        engine.add_effect(self, self.effect(engine, "reveal", ("player", ben), 1.0, collector))
        engine.request_prediction()
        return {"affects": ("player", ben)}
