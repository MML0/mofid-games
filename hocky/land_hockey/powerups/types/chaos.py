from ..base import PowerUpType
from ..registry import register

ZWNJ = "‌"


@register
class Chaos(PowerUpType):
    """Random path («نوسان ناگهانی بازار»).

    sequence (default): the ball pauses, the event is announced, a roulette of candidate paths spins and locks,
    the ball fires; after a short flight it pauses and re-rolls once more, unless it is already near the receiver.
    instant / wobble: the older one-shot deflection or curving path.
    """
    id = "chaos"
    name = "Random path"
    order = 4
    icon = "chaos"
    default_class = "good"
    duration = 2.5
    unlock_phase = 2
    toast_c = ""
    banner = False

    def extra_schema(self, sb, p):
        sb.e(f"{p}.mode", "sequence", ("sequence", "instant", "wobble"), "Mode",
             "sequence = pause, announce, spin and fire (twice); wobble uses Duration as its length.")
        sb.s(f"{p}.title", "نوسان ناگهانی بازار!", "Announcement title", rtl=True)
        sb.s(f"{p}.subtitle", f"مسیر توپ به{ZWNJ}صورت تصادفی تغییر می{ZWNJ}کند", "Announcement subtitle", rtl=True)
        sb.s(f"{p}.reroll_text", "یک نوسان دیگر!", "Second change text", rtl=True)
        sb.f(f"{p}.intro_s", 0.55, 0.0, 4, 0.05, "s", "Announcement time")
        sb.f(f"{p}.select_s", 0.5, 0.1, 4, 0.05, "s", "Path selection spin")
        sb.i(f"{p}.rerolls", 1, 0, 3, 1, "", "Extra path changes")
        sb.f(f"{p}.reroll_delay_s", 0.3, 0.05, 2, 0.05, "s", "Flight before the next change")
        sb.f(f"{p}.reroll_select_s", 0.3, 0.1, 3, 0.05, "s", "Next change spin")
        sb.i(f"{p}.min_reroll_distance", 300, 0, 900, 10, "px", "No change if this close to the player")
        sb.i(f"{p}.candidates", 7, 3, 15, 1, "", "Candidate paths shown")
        sb.f(f"{p}.fire_mult", 1.0, 0.5, 2.0, 0.05, "×", "Speed when fired")
        sb.i(f"{p}.ray_length", 70, 20, 300, 5, "px", "Candidate path length")
        sb.b(f"{p}.block_speedup", True, "No speed-up after the random path",
             "Until a player hits it, the ball ignores speed-ups (they would make the random shot unplayable).")
        sb.b(f"{p}.pause_timer", True, "Pause the match timer meanwhile")
        sb.f(f"{p}.min_angle_deg", 20, 0, 90, 1, "°", "Min turn (instant mode)")
        sb.f(f"{p}.max_angle_deg", 55, 0, 90, 1, "°", "Max turn (instant mode)")
        sb.f(f"{p}.wobble_deg_s", 140, 10, 600, 5, "°/s", "Wobble strength")
        sb.f(f"{p}.wobble_hz", 1.6, 0.2, 6, 0.1, "Hz", "Wobble frequency")

    def collect(self, engine, ball, collector):
        cfg = engine.cfg
        mode = self.p(cfg, "mode")
        if mode == "wobble":
            engine.add_effect(self, self.effect(engine, "wobble", ("ball", ball.id), 1.0, collector,
                                                amp=self.p(cfg, "wobble_deg_s"), hz=self.p(cfg, "wobble_hz"),
                                                phase=engine.rng.random() * 6.283))
        elif mode == "instant":
            engine.chaos_deflect(ball, collector, self.p(cfg, "min_angle_deg"), self.p(cfg, "max_angle_deg"))
        else:
            keys = ("title", "subtitle", "reroll_text", "intro_s", "select_s", "rerolls", "reroll_delay_s",
                    "reroll_select_s", "min_reroll_distance", "candidates", "fire_mult", "ray_length", "block_speedup")
            engine.start_chaos(ball, collector, {k: self.p(cfg, k) for k in keys})
        return {"affects": ("ball", ball.id)}
