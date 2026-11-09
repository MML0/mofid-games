import json
import os

import pytest

from market_hockey.config import SCHEMA_VERSION, Config, get_schema
from market_hockey.config.schema import KINDS
from market_hockey.config.store import coerce
from market_hockey.ui.widgets import widget_kind


def test_schema_is_complete():
    schema = get_schema()
    assert len(schema) > 300
    for p in schema.values():
        assert p.kind in KINDS
        assert p.label and p.tab
        if p.kind in ("float", "int"):
            assert p.min is not None and p.max is not None and p.min <= p.default <= p.max, p.path
        if p.kind == "enum":
            assert p.default in p.options, p.path
        assert widget_kind(p)  # every setting has a control-panel widget


def test_roundtrip(tmp_path):
    c = Config()
    c.set("ball.base_speed", 777)
    c.set("text.goal", "گل!")
    c.set("colors.p1", "#123456")
    path = tmp_path / "s.json"
    c.save(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["ball"]["base_speed"] == 777 and raw["_meta"]["schema_version"] == SCHEMA_VERSION
    assert "گل!" in path.read_text(encoding="utf-8")  # Persian kept readable
    c2 = Config.load(path)
    assert c2["ball.base_speed"] == 777 and c2["colors.p1"] == "#123456"


def test_invalid_values_are_recovered():
    c = Config()
    ok, v, w = c.set("ball.max_speed", 999999)
    assert v == get_schema()["ball.max_speed"].max and w
    ok, v, w = c.set("colors.p2", "not a color")
    assert v == get_schema()["colors.p2"].default and w
    ok, v, w = c.set("ball.radius", "abc")
    assert v == get_schema()["ball.radius"].default
    ok, v, w = c.set("serve.first", "nobody")
    assert v == "random"
    assert coerce(get_schema()["match.timer_enabled"], "false")[0] is False


def test_missing_and_unknown_keys(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"ball": {"radius": 20}, "mystery": {"x": 1}}), encoding="utf-8")
    c = Config.load(path)
    assert c["ball.radius"] == 20
    assert c["ball.base_speed"] == get_schema()["ball.base_speed"].default  # missing -> default
    assert c.extra == {"mystery.x": 1}
    c.save(path)
    assert json.loads(path.read_text(encoding="utf-8"))["mystery"]["x"] == 1  # preserved


def test_corrupt_file_falls_back(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{ this is not json", encoding="utf-8")
    c = Config.load(path)
    assert c["ball.radius"] == get_schema()["ball.radius"].default and c.warnings


def test_atomic_save_keeps_old_file_on_failure(tmp_path, monkeypatch):
    path = tmp_path / "s.json"
    Config({"ball.radius": 22}).save(path)
    before = path.read_text(encoding="utf-8")

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        Config({"ball.radius": 33}).save(path)
    assert path.read_text(encoding="utf-8") == before


def test_backup_written(tmp_path):
    path, bak = tmp_path / "s.json", tmp_path / "s.prev.json"
    Config({"ball.radius": 22}).save(path, bak)
    Config({"ball.radius": 33}).save(path, bak)
    assert json.loads(bak.read_text(encoding="utf-8"))["ball"]["radius"] == 22


def test_change_tracking():
    c = Config()
    v = c.version
    c.set("walls.top_percent", 20)
    assert c.changes_since(v) == {"walls.top_percent"}
    assert c.changes_since(c.version) == set()


def test_live_link_roundtrip():
    from market_hockey.config.live_link import LiveLinkClient, LiveLinkServer
    import time

    srv = LiveLinkServer(0)
    assert srv.ok
    cl = LiveLinkClient(srv.port)
    cl.set("ball.radius", 25)
    cl.command("start_match")
    msgs = []
    for _ in range(50):
        msgs += srv.poll()
        if len(msgs) >= 2:
            break
        time.sleep(0.01)
    assert msgs[0][0]["path"] == "ball.radius" and msgs[1][0]["name"] == "start_match"
    srv.send({"type": "state", "fps": 60}, msgs[0][1])
    got = []
    for _ in range(50):
        got += cl.poll()
        if got:
            break
        time.sleep(0.01)
    assert got and got[0]["fps"] == 60 and cl.connected
    srv.close()
    cl.close()


def test_v1_settings_migrate_but_keep_custom_values(tmp_path):
    from market_hockey.config.store import V2_DEFAULT_CHANGES

    path = tmp_path / "old.json"
    old = {"_meta": {"schema_version": 1}, "ball": {"radius": 15},
           "powerups": {"magnet": {"strength": 900.0, "radius": 333}, "max_active_orbs": 2,
                        "types": {"trajectory_reveal": {"class": "bad"}}}}
    path.write_text(json.dumps(old), encoding="utf-8")
    c = Config.load(path)
    assert c["ball.radius"] == 15  # untouched custom value
    assert c["powerups.magnet.strength"] == V2_DEFAULT_CHANGES["powerups.magnet.strength"][1]  # old default -> new
    assert c["powerups.magnet.radius"] == 333  # customized: kept
    assert c["powerups.max_active_orbs"] == 5  # old default at every step: 2 -> 3 (v2) -> 5 (v14)
    assert c["powerups.types.trajectory_reveal.class"] == "good"
