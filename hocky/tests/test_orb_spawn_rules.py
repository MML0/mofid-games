"""Orbs on the field are unique, there are always 2 to 4 of them, and the red shrink orb comes at most twice a game."""

import json
import random

import pygame
import pytest

from conftest import playing
from market_hockey.config import Config
from market_hockey.core.engine import Engine
from market_hockey.paths import ORBS_DIR

ROOT = ORBS_DIR.parent.parent


def _engine(seed=3, **values):
    engine = Engine(Config(values), random.Random(seed))
    playing(engine)
    return engine


def _types_on_field(engine):
    return [o.type_id for o in engine._active_orbs()]


def test_defaults_keep_two_to_four_unique_orbs():
    cfg = Config()
    assert (cfg["powerups.min_active_orbs"], cfg["powerups.max_active_orbs"]) == (2, 4)
    assert cfg["powerups.unique_orbs"] is True
    assert cfg["powerups.types.shrink.max_per_match"] == 2
    assert all(cfg[f"powerups.types.{tid}.max_per_match"] == 0 for tid in ("expand", "speed_up", "double_ball"))


def test_shipped_settings_use_the_new_rules():
    shipped = Config.load(ROOT / "config" / "settings.json")
    assert (shipped["powerups.min_active_orbs"], shipped["powerups.max_active_orbs"]) == (2, 4)
    assert shipped["powerups.unique_orbs"] and shipped["powerups.types.shrink.max_per_match"] == 2
    assert shipped["powerups.types.expand.glow_color"] == "#3CAA5C"


def test_a_new_orb_is_never_a_type_already_on_the_field():
    engine = _engine(**{"powerups.max_active_orbs": 8, "powerups.no_repeat": False,
                        "powerups.avoid_conflicting_spawns": False})
    for _ in range(200):
        engine.orbs.clear()
        engine.type_cd.clear()
        engine.spawn_counts.clear()
        for _ in range(8):
            engine._spawn_orb(phase=3)
        types = _types_on_field(engine)
        assert types and len(types) == len(set(types))


def test_unique_orbs_can_be_switched_off():
    engine = _engine(**{"powerups.max_active_orbs": 8, "powerups.no_repeat": False, "powerups.unique_orbs": False,
                        "powerups.avoid_conflicting_spawns": False})
    for tid in engine.types:
        engine.cfg.set(f"powerups.types.{tid}.enabled", tid == "expand")
    for _ in range(3):
        engine._spawn_orb(phase=3)
    assert _types_on_field(engine) == ["expand"] * 3


def test_the_minimum_is_filled_at_once_without_waiting_for_the_timer():
    engine = _engine()
    engine.next_spawn = 99.0
    for _ in range(3):
        engine._update_spawner(1 / 60, demo=False)
    assert len(engine._active_orbs()) == 2
    for _ in range(600):  # 10 s and the timer never fires: nothing above the minimum
        engine._update_spawner(1 / 60, demo=False)
    assert len(engine._active_orbs()) == 2


def test_the_minimum_bends_cooldowns_but_never_uniqueness():
    engine = _engine()
    engine.play_elapsed = 15.0  # early phase: only expand, shrink and speed_up are unlocked
    assert engine.phase_index() == 1
    engine.cfg.set("powerups.types.shrink.enabled", False)
    for tid in engine.types:
        engine.type_cd[tid] = engine.time + 60  # everything was just collected
    engine.next_spawn = 99.0
    for _ in range(10):
        engine._update_spawner(1 / 60, demo=False)
    assert sorted(_types_on_field(engine)) == ["expand", "speed_up"]


def test_the_timer_tops_up_to_the_maximum_and_no_further():
    engine = _engine(**{"phases.enabled": False})  # mid phase: five power-ups are unlocked
    for _ in range(60 * 20):
        engine._update_spawner(1 / 60, demo=False)
        assert len(engine._active_orbs()) <= 4
    assert len(engine._active_orbs()) == 4


def test_shrink_spawns_at_most_twice_per_game():
    engine = _engine(**{"powerups.no_repeat": False})
    for tid in engine.types:
        engine.cfg.set(f"powerups.types.{tid}.enabled", tid in ("shrink", "expand"))
    shrinks = 0
    for _ in range(50):
        engine.orbs.clear()
        engine.type_cd.clear()
        orb = engine._spawn_orb(phase=3)
        shrinks += orb is not None and orb.type_id == "shrink"
    assert shrinks == 2
    engine.start_match()  # a new game starts the count again
    assert engine.spawn_counts == {}


def test_the_floor_keeps_two_orbs_through_a_whole_game_and_rules_hold():
    engine = Engine(Config({"match.duration_s": 60}), random.Random(11))
    engine.start_match()
    low = total = 0
    shrinks = set()
    for _ in range(60 * 90):
        engine.step(1 / 60)
        types = _types_on_field(engine)
        assert len(types) <= 4 and len(types) == len(set(types))
        if engine.state in ("ATTRACT",):
            break  # the game is over; the attract demo starts its own count
        for o in engine.orbs:
            if o.type_id == "shrink":
                shrinks.add(o.id)
        if engine.state == "PLAYING" and engine.phase_index() in (1, 2, 3):
            total += 1
            low += len(types) < 2
    assert total > 60 * 15
    assert low / total < 0.02  # only the odd frame where no clear spot was free
    assert len(shrinks) <= 2


def test_old_settings_move_to_four_orbs_and_the_green_glow(tmp_path):
    path = tmp_path / "v14.json"
    path.write_text(json.dumps({"_meta": {"schema_version": 14},
                                "powerups": {"max_active_orbs": 5,
                                             "types": {"expand": {"glow_color": "#3D97C9"}}}}), encoding="utf-8")
    cfg = Config.load(path)
    assert cfg["powerups.max_active_orbs"] == 4 and cfg["powerups.types.expand.glow_color"] == "#3CAA5C"
    path.write_text(json.dumps({"_meta": {"schema_version": 14}, "powerups": {"max_active_orbs": 6}}),
                    encoding="utf-8")
    assert Config.load(path)["powerups.max_active_orbs"] == 6  # the operator chose this one


@pytest.fixture
def _pg():
    pygame.init()
    yield


def test_the_hami_face_is_green(_pg):
    face = pygame.image.load(str(ORBS_DIR / "expand.png"))
    r, g, b, _ = face.get_at((256, 60))  # background above the name
    assert g > r + 60 and g > b + 40
