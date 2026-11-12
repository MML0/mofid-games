"""A damaged or outdated settings file must never stop the game from starting, in front of a queue of visitors."""

import json
import math
import random

import pytest

from land_hockey.config import SCHEMA_VERSION, Config, get_schema
from land_hockey.config.live_link import LiveLinkClient, LiveLinkServer, MAX_DATAGRAM, _decode
from land_hockey.config.store import MIGRATIONS, coerce, flatten, nest


@pytest.mark.parametrize("text", [
    "", "null", "[]", "42", '"text"', "{", '{"_meta": 5}', '{"_meta": []}', '{"_meta": {"schema_version": "abc"}}',
    '{"_meta": {"schema_version": null}}', '{"_meta": {"schema_version": 1e999}}', '{"ball": 5}', '{"ball": []}',
    '{"ball": {"radius": 1e999}}', '{"ball": {"radius": -1e999}}', '{"ball": {"radius": NaN}}', '{"ball": {"radius": Infinity}}',
    '{"match": {"score_limit": 1e999}}', '{"match": {"score_limit": NaN}}', '{"match": {"score_limit": "many"}}',
    '{"match": {"score_limit": [1]}}', '{"match": {"score_limit": {"a": 1}}}', '{"colors": {"p1": 12}}',
    '{"text": {"goal": null}}', '{"input": {"p1": {"source": "telepathy"}}}',
])
def test_any_broken_settings_file_still_loads(tmp_path, text):
    path = tmp_path / "s.json"
    path.write_text(text, encoding="utf-8")
    c = Config.load(path)
    for key, p in get_schema().items():
        v = c[key]
        if p.kind in ("float", "int"):
            assert math.isfinite(v) and p.min <= v <= p.max, key
    assert c["input.p1.source"] != "telepathy"


def test_binary_settings_file_still_loads(tmp_path):
    path = tmp_path / "s.json"
    path.write_bytes(b"\xff\xfe\x00\x01binary")
    assert Config.load(path)["ball.radius"] == get_schema()["ball.radius"].default


def test_missing_file_gives_defaults_with_a_warning(tmp_path):
    c = Config.load(tmp_path / "none.json")
    assert c.warnings and c["ball.radius"] == get_schema()["ball.radius"].default
    assert not Config.load(None).warnings


def test_numbers_are_coerced_and_rounded_for_each_kind():
    schema = get_schema()
    assert coerce(schema["match.score_limit"], "5")[0] == 5
    assert coerce(schema["match.score_limit"], 5.6)[0] == 6
    assert isinstance(coerce(schema["trails.duration_s"], 1)[0], float)
    assert coerce(schema["text.goal"], None)[0] == schema["text.goal"].default  # never the word "None" on the arena
    assert coerce(schema["colors.p1"], "abcdef")[0] == "#ABCDEF"
    for on in ("1", "true", "YES", " on "):
        assert coerce(schema["match.timer_enabled"], on)[0] is True
    assert coerce(schema["match.timer_enabled"], 0)[0] is False


def test_every_setting_accepts_its_own_default_without_a_warning():
    for p in get_schema().values():
        assert coerce(p, p.default)[1] is None, p.path


@pytest.mark.parametrize("seed", range(5))
def test_random_garbage_for_every_setting_never_raises(seed):
    rng = random.Random(seed)
    junk = [None, "", "x", -1, 0, 1, 1e308, -1e308, float("inf"), float("nan"), [], {}, True, "#GGGGGG", "ف"]
    c = Config()
    for path in c.schema:
        c.set(path, rng.choice(junk))
    for key, p in c.schema.items():
        if p.kind in ("float", "int"):
            assert math.isfinite(c[key]) and p.min <= c[key] <= p.max, key


def test_save_and_reload_is_lossless_for_every_setting(tmp_path):
    c = Config()
    path = tmp_path / "s.json"
    c.save(path)
    assert Config.load(path).values == c.values


def test_nest_and_flatten_are_inverse():
    flat = {"a.b.c": 1, "a.d": 2, "e": 3}
    assert flatten(nest(flat)) == flat


def test_nest_keeps_a_value_that_collides_with_a_group():
    assert nest({"a": 1, "a.b": 2}) == {"a": {"_value": 1, "b": 2}}


def test_migrations_chain_reaches_the_current_version():
    assert set(MIGRATIONS) == set(range(1, SCHEMA_VERSION))


def test_oldest_file_migrates_all_the_way(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"_meta": {"schema_version": 1}, "ball": {"radius": 17}}), encoding="utf-8")
    c = Config.load(path)
    assert c["ball.radius"] == 17
    assert c["powerups.types.chaos.mode"] == "sequence"  # from a later migration


def test_a_file_from_a_newer_version_still_loads(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"_meta": {"schema_version": SCHEMA_VERSION + 5}, "ball": {"radius": 17},
                                "future": {"setting": 1}}), encoding="utf-8")
    c = Config.load(path)
    assert c["ball.radius"] == 17 and c.extra == {"future.setting": 1}


def test_reset_defaults_restores_everything():
    c = Config({"ball.radius": 30, "colors.p1": "#000000"})
    c.reset_defaults()
    assert c.values == Config().values


def test_change_log_overflow_asks_for_a_full_refresh():
    c = Config()
    v = c.version
    for k in range(5000):
        c.set("ball.radius", 10 + k % 5)
    assert c.changes_since(v) == {"*"}


def test_update_returns_warnings_and_applies_the_rest():
    c = Config()
    warns = c.update({"ball.radius": 20, "ball.max_speed": 1e12, "no.such.key": 1})
    assert c["ball.radius"] == 20 and len(warns) == 2 and c.extra["no.such.key"] == 1


def test_snapshot_is_a_copy():
    c = Config()
    snap = c.snapshot()
    snap["ball.radius"] = -1
    assert c["ball.radius"] != -1


def test_read_flat(tmp_path):
    path = tmp_path / "s.json"
    Config({"ball.radius": 21}).save(path)
    flat = Config.read_flat(path)
    assert flat["ball.radius"] == 21 and not any(k.startswith("_meta") for k in flat)


def test_a_failed_backup_does_not_block_saving(tmp_path, monkeypatch):
    import shutil

    path = tmp_path / "s.json"
    Config({"ball.radius": 20}).save(path)

    def boom(*a, **k):
        raise OSError("no permission")

    monkeypatch.setattr(shutil, "copy2", boom)
    Config({"ball.radius": 21}).save(path, tmp_path / "bak.json")
    assert Config.load(path)["ball.radius"] == 21


# ---------------------------------------------------------------- live link
@pytest.fixture
def link():
    srv = LiveLinkServer(0)
    cl = LiveLinkClient(srv.port)
    yield srv, cl
    srv.close()
    cl.close()


def drain(fn, want=1, tries=500):
    import time

    out = []
    for _ in range(tries):
        out += fn()
        if len(out) >= want:
            break
        time.sleep(0.002)
    return out


@pytest.mark.parametrize("data", [b"", b"nope", b"\xff\xff", b"[1]", b"7", b"null"])
def test_decode_rejects_everything_but_objects(data):
    assert _decode(data) is None


def test_server_ignores_garbage_and_keeps_listening(link):
    srv, cl = link
    cl.sock.sendto(b"garbage", cl.game_addr)
    cl.hello()
    msgs = drain(srv.poll)
    assert [m for m, _ in msgs] == [{"type": "hello"}]


def test_all_current_settings_fit_through_the_link(link):
    """Connecting pushes every setting at once. That must survive the UDP size limit."""
    srv, cl = link
    c = Config()
    cl.set_many(c.snapshot())
    got = {}
    for m, _a in drain(srv.poll, want=4):
        got.update(m["values"])
    assert got == json.loads(json.dumps(c.snapshot()))


def test_oversized_batches_are_split(link):
    srv, cl = link
    big = {f"k{i}": "x" * 2000 for i in range(60)}
    assert len(json.dumps(big)) > MAX_DATAGRAM
    cl.set_many(big)
    got = {}
    for m, _a in drain(srv.poll, want=len(big) // 3):
        assert len(json.dumps(m)) <= MAX_DATAGRAM
        got.update(m["values"])
    assert got == big


def test_a_single_huge_value_does_not_hang_the_panel(link):
    _srv, cl = link
    cl.set_many({"text.goal": "x" * (MAX_DATAGRAM + 10)})
    cl.set("text.banner", "x" * (MAX_DATAGRAM + 10))
    warnings = cl.take_warnings()
    assert "text.goal" in warnings[0] and "text.banner" in warnings[1] and cl.take_warnings() == []


def test_persian_survives_the_link(link):
    srv, cl = link
    cl.set("text.goal", "گل!")
    assert drain(srv.poll)[0][0]["value"] == "گل!"


def test_state_marks_the_client_connected_then_it_expires(link, monkeypatch):
    import land_hockey.config.live_link as ll

    srv, cl = link
    assert not cl.connected
    cl.hello()
    addr = drain(srv.poll)[0][1]
    srv.send({"type": "ack"}, addr)
    drain(cl.poll)
    assert not cl.connected  # only telemetry counts
    srv.send({"type": "state"}, addr)
    drain(cl.poll)
    assert cl.connected
    t = ll.time.monotonic()
    monkeypatch.setattr(ll.time, "monotonic", lambda: t + 10)
    assert not cl.connected


def test_broadcast_reaches_clients_and_forgets_silent_ones(link, monkeypatch):
    import land_hockey.config.live_link as ll

    srv, cl = link
    cl.hello()
    drain(srv.poll)
    srv.broadcast({"type": "state", "n": 1})
    assert drain(cl.poll)[0]["n"] == 1
    t = ll.time.monotonic()
    monkeypatch.setattr(ll.time, "monotonic", lambda: t + 60)
    srv.broadcast({"type": "state", "n": 2})
    assert srv.clients == {}


def test_port_in_use_disables_the_link_but_nothing_else(link):
    srv, _cl = link
    other = LiveLinkServer(srv.port)
    assert not other.ok
    assert other.poll() == []
    other.send({"a": 1}, ("127.0.0.1", 1))
    other.broadcast({"a": 1})
    other.close()


def test_closed_server_is_harmless():
    srv = LiveLinkServer(0)
    srv.close()
    srv.close()
    assert srv.poll() == [] and not srv.ok
