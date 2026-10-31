"""Sounds are generated, not recorded: the files must be valid and playback must never affect the game."""

import wave

import pygame
import pytest

from market_hockey.audio import audio as audio_mod
from market_hockey.audio.audio import CATEGORY, Audio
from market_hockey.audio.synth import SOUNDS, generate_all, seq, tone
from market_hockey.paths import SOUNDS_DIR


@pytest.fixture
def audio(cfg):
    pygame.init()
    a = Audio(cfg)
    if not a.ok:
        pytest.skip("no audio mixer on this machine")
    return a


class Spy:
    def __init__(self, a):
        self.played = []
        self.real = a.play
        a.play = lambda name, vol=1.0: self.played.append((name, vol))


def test_every_sound_generates_a_valid_wav(tmp_path):
    made = generate_all(tmp_path)
    assert {p.stem for p in made} == set(SOUNDS)
    for p in made:
        with wave.open(str(p)) as w:
            assert w.getnframes() > 100 and w.getsampwidth() == 2 and w.getnchannels() == 1


def test_generation_keeps_existing_files_unless_forced(tmp_path):
    generate_all(tmp_path)
    keep = tmp_path / "wall.wav"
    keep.write_bytes(b"custom")
    assert generate_all(tmp_path) == []
    assert keep.read_bytes() == b"custom"
    assert len(generate_all(tmp_path, overwrite=True)) == len(SOUNDS)
    assert keep.read_bytes() != b"custom"


@pytest.mark.parametrize("wave_", ["sine", "tri", "square"])
def test_tones_stay_in_range(wave_):
    samples = tone([440, 880], 0.05, 1.0, wave_, noise=0.5, sweep=0.3)
    assert len(samples) > 0 and max(abs(v) for v in samples) <= 1.0001


def test_sequences_play_one_after_the_other():
    a, b = tone([440], 0.02), tone([880], 0.03)
    assert len(seq([a, b])) >= len(a) + len(b) - 2


def test_all_sounds_ship_with_the_game():
    for name in SOUNDS:
        assert (SOUNDS_DIR / f"{name}.wav").exists(), name


def test_every_sound_has_a_volume_category():
    assert set(CATEGORY) == set(SOUNDS)


def test_loads_every_sound(audio):
    assert set(audio.sounds) == set(SOUNDS)


def test_missing_sounds_are_generated(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(audio_mod, "SOUNDS_DIR", tmp_path)
    pygame.init()
    a = Audio(cfg)
    if a.ok:
        assert (tmp_path / "goal.wav").exists() and set(a.sounds) == set(SOUNDS)


def test_a_broken_sound_file_only_silences_that_sound(cfg, tmp_path, monkeypatch):
    generate_all(tmp_path)
    (tmp_path / "goal.wav").write_bytes(b"not audio")
    monkeypatch.setattr(audio_mod, "SOUNDS_DIR", tmp_path)
    pygame.init()
    a = Audio(cfg)
    if a.ok:
        assert "goal" not in a.sounds and "wall" in a.sounds
        a.play("goal")


def test_no_mixer_means_silence_not_a_crash(cfg, monkeypatch):
    def boom(*a, **k):
        raise pygame.error("no audio device")

    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
    monkeypatch.setattr(pygame.mixer, "init", boom)
    a = Audio(cfg)
    assert not a.ok
    a.play("goal")
    a.handle_events([{"type": "goal"}])


def test_settings_silence_playback(audio, cfg, monkeypatch):
    calls = []

    class S:
        def play(self):
            calls.append(1)

    audio.sounds["goal"] = S()
    cfg.set("audio.enabled", False)
    audio.play("goal")
    cfg.set("audio.enabled", True)
    cfg.set("audio.master", 0)
    audio.play("goal")
    assert calls == []
    audio.last.clear()
    cfg.set("audio.master", 1)
    audio.play("goal")
    audio.play("goal")  # immediately again: rate limited
    assert len(calls) == 1


def test_unknown_sound_is_ignored(audio):
    audio.play("no_such_sound")


@pytest.mark.parametrize("event,sound", [
    ({"type": "paddle_hit", "speed": 1000}, "hit_high"),
    ({"type": "paddle_hit", "speed": 700}, "hit_mid"),
    ({"type": "paddle_hit", "speed": 300}, "hit_low"),
    ({"type": "wall_bounce"}, "wall"),
    ({"type": "goal"}, "goal"),
    ({"type": "powerup_collected", "cls": "bad"}, "bad"),
    ({"type": "powerup_collected", "cls": "good"}, "good"),
    ({"type": "orb_spawned"}, "spawn"),
    ({"type": "effect_ended"}, "effect_end"),
    ({"type": "countdown_beat", "label": "go"}, "go"),
    ({"type": "countdown_beat", "label": "3"}, "beep"),
    ({"type": "timer_tick"}, "tick"),
    ({"type": "match_end"}, "end"),
    ({"type": "shield_block"}, "shield"),
    ({"type": "ball_split"}, "split"),
])
def test_game_events_play_the_right_sound(audio, event, sound):
    spy = Spy(audio)
    audio.handle_events([event])
    assert spy.played[0][0] == sound


def test_smart_hits_add_a_sound_and_demo_goals_are_quieter(audio):
    spy = Spy(audio)
    audio.handle_events([{"type": "paddle_hit", "speed": 300, "smart": True}])
    assert [n for n, _v in spy.played] == ["hit_low", "smart"]
    spy.played.clear()
    audio.handle_events([{"type": "goal", "demo": True}])
    assert spy.played == [("goal", 0.5)]


def test_replaced_effects_stay_silent(audio):
    spy = Spy(audio)
    audio.handle_events([{"type": "effect_ended", "replaced": True}, {"type": "unknown_event"}])
    assert spy.played == []
