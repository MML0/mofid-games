import math
import random

from market_hockey.config import Config
from market_hockey.core.engine import Engine
from market_hockey.inputs.ai import AIAdapter


def test_ai_soak_three_minutes():
    cfg = Config()
    cfg.set("match.start_mode", "auto_loop")
    cfg.set("match.auto_loop_delay_s", 1.0)
    cfg.set("match.duration_s", 30)
    for t in ("slow_down", "dim_ball", "shield", "bull_market"):
        cfg.set(f"powerups.types.{t}.enabled", True)
    eng = Engine(cfg, random.Random(5))
    ai = AIAdapter(cfg, random.Random(6))
    dt = 1 / 240
    matches = 0
    goals = 0
    collected = 0
    for k in range(int(180 / dt)):
        s = {i: ai.sample(i, k * dt, dt, eng) for i in (0, 1)}
        eng.step(dt, s, [True, True])
        for e in eng.drain_events():
            matches += e["type"] == "match_end"
            goals += e["type"] == "goal" and not e.get("demo")
            collected += e["type"] == "powerup_collected"
        for b in eng.live_balls():
            assert math.isfinite(b.x) and math.isfinite(b.y) and math.isfinite(b.vx)
            assert math.hypot(b.x, b.y) < eng.geom.R + 60
            assert b.since_touch < cfg["physics.stall_timeout_s"] + 20
        assert len(eng.balls) <= cfg["physics.max_balls"] + 2
        assert len(eng.orbs) <= 10
        assert len(eng.effects.effects) <= 30
    assert matches >= 3 and goals > 0 and collected > 0
