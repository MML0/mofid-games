"""Timed effects. Game state is never mutated permanently: multipliers are recomputed from the active
effects every step, so when an effect expires the previous state is restored automatically."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Effect:
    type_id: str
    kind: str  # paddle_size | ball_speed | dim | reveal | shield | bull | wobble
    target: tuple  # ("player", idx) | ("ball", ball_id) | ("all",)
    duration: float = 5.0
    remaining: float = 5.0
    value: float = 1.0
    group: str | None = None
    collector: int | None = None
    data: dict = field(default_factory=dict)
    id: int = 0
    age: float = 0.0

    @property
    def frac(self) -> float:
        return max(0.0, min(1.0, self.remaining / self.duration)) if self.duration > 0 else 0.0


def _overlap(a: tuple, b: tuple) -> bool:
    if a == b:
        return True
    return (a[0] == "all" and b[0] == "ball") or (b[0] == "all" and a[0] == "ball")


class EffectManager:
    def __init__(self):
        self.effects: list[Effect] = []
        self._next = 1

    def clear(self) -> None:
        self.effects.clear()

    def add(self, eff: Effect, stacking: str = "refresh", max_stack: int = 3, policy: str = "replace"):
        """Returns (added_or_refreshed_effect | None, removed_effects)."""
        eff.remaining = eff.duration
        same = [e for e in self.effects if e.type_id == eff.type_id and e.target == eff.target]
        if same:
            if stacking == "ignore":
                return None, []
            if stacking == "refresh":
                same[0].duration = eff.duration
                same[0].remaining = eff.duration
                same[0].value = eff.value
                same[0].collector = eff.collector
                same[0].data.update(eff.data)
                return same[0], []
            if stacking == "extend":
                same[0].remaining = min(same[0].remaining + eff.duration, eff.duration * 3)
                same[0].duration = max(same[0].duration, same[0].remaining)
                return same[0], []
            if stacking == "stack" and len(same) >= max_stack:
                oldest = min(same, key=lambda e: e.remaining)
                oldest.remaining = oldest.duration = eff.duration
                return oldest, []
        removed: list[Effect] = []
        if eff.group:
            conflicts = [e for e in self.effects
                         if e.group == eff.group and e.type_id != eff.type_id and _overlap(e.target, eff.target)]
            if conflicts:
                if policy == "block":
                    return None, []
                for c in conflicts:
                    self.effects.remove(c)
                    removed.append(c)
        eff.id = self._next
        self._next += 1
        self.effects.append(eff)
        return eff, removed

    def remove(self, eff: Effect) -> None:
        if eff in self.effects:
            self.effects.remove(eff)

    def update(self, dt: float) -> list[Effect]:
        ended = []
        for e in self.effects:
            e.remaining -= dt
            e.age += dt
            if e.remaining <= 0:
                ended.append(e)
        for e in ended:
            self.effects.remove(e)
        return ended

    def remove_for_ball(self, ball_id: int) -> list[Effect]:
        gone = [e for e in self.effects if e.target == ("ball", ball_id)]
        for e in gone:
            self.effects.remove(e)
        return gone

    def remove_ball_effects(self) -> list[Effect]:
        gone = [e for e in self.effects if e.target[0] in ("ball", "all")]
        for e in gone:
            self.effects.remove(e)
        return gone

    # ---- queries -----------------------------------------------------------------
    def of_kind(self, kind: str) -> list[Effect]:
        return [e for e in self.effects if e.kind == kind]

    def paddle_mult(self, idx: int, stacking: str = "multiply") -> float:
        effs = [e for e in self.effects if e.kind == "paddle_size" and e.target == ("player", idx)]
        if not effs:
            return 1.0
        if stacking == "replace":
            return max(effs, key=lambda e: e.id).value
        m = 1.0
        for e in effs:
            m *= e.value
        return m

    def ball_speed_mult(self, ball_id: int) -> float:
        m = 1.0
        for e in self.effects:
            if e.kind == "ball_speed" and (e.target == ("ball", ball_id) or e.target[0] == "all"):
                m *= e.value
        return m

    def ball_alpha(self, ball_id: int) -> float:
        a = 1.0
        for e in self.effects:
            if e.kind == "dim" and (e.target == ("ball", ball_id) or e.target[0] == "all"):
                a = min(a, e.value)
        return a

    def ball_has(self, ball_id: int, kind: str) -> Effect | None:
        for e in self.effects:
            if e.kind == kind and (e.target == ("ball", ball_id) or e.target[0] == "all"):
                return e
        return None

    def reveal_beneficiaries(self) -> set[int]:
        return {e.target[1] for e in self.effects if e.kind == "reveal"}

    def for_player(self, idx: int, kind: str) -> Effect | None:
        for e in self.effects:
            if e.kind == kind and e.target == ("player", idx):
                return e
        return None

    def player_effects(self, idx: int) -> list[Effect]:
        return [e for e in self.effects if e.target == ("player", idx)]

    def group_active(self, group: str) -> bool:
        return any(e.group == group for e in self.effects)
