import json
import time
import urllib.error
import urllib.request

import pytest

from market_hockey.web import history
from market_hockey.web.server import SupervisorServer


def _req(url, data=None, ctype="application/json"):
    req = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(), method="POST" if data is not None else "GET")
    if data is not None and ctype:
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=3) as r:
        return r.status, r.read()


@pytest.fixture
def server(tmp_path):
    srv = SupervisorServer("127.0.0.1", 0, history_path=tmp_path / "h.jsonl")
    assert srv.start()
    yield srv
    srv.stop()


def test_page_state_and_fonts(server):
    code, body = _req(server.url)
    assert code == 200 and "هاکی بازار".encode() in body
    server.publish({"state": "ATTRACT", "scores": [1, 2]})
    code, body = _req(server.url + "api/state")
    assert json.loads(body)["scores"] == [1, 2]
    code, body = _req(server.url + "fonts/IRANSansX-Bold.ttf")
    assert code == 200 and len(body) > 10000
    with pytest.raises(urllib.error.HTTPError):
        _req(server.url + "fonts/..%2F..%2Fconfig%2Fsettings.json")


def test_commands_need_json(server):
    _req(server.url + "api/names", {"p1": "سارا", "p2": "Ali"})
    _req(server.url + "api/start", {})
    cmds = server.drain()
    assert cmds[0] == ("names", {"p1": "سارا", "p2": "Ali"}) and cmds[1][0] == "start"
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(server.url + "api/start", {}, ctype="text/plain")
    assert e.value.code == 415  # cross-site form posts are refused


def test_history_and_leaderboard(tmp_path, server):
    path = tmp_path / "h.jsonl"
    ev = {"scores": [3, 5], "winner": 1, "duration": 60, "golden": False, "stats": {"powerups": [1, 2], "smart": [0, 1]}}
    history.append(history.make_record(ev, ["سارا", ""], ["بازیکن 1", "بازیکن 2"]), path)
    ev2 = {"scores": [4, 1], "winner": 0, "duration": 60, "golden": False, "stats": {}}
    history.append(history.make_record(ev2, ["سارا", "Ali"], ["بازیکن 1", "بازیکن 2"]), path)
    path.open("a").write("not json\n")
    recs = history.read_all(path)
    assert len(recs) == 2 and recs[0]["players"][1]["name"] == "Ali"  # newest first, bad line skipped
    lb = history.leaderboard(recs)
    assert lb[0]["name"] == "سارا" and lb[0]["games"] == 2 and lb[0]["wins"] == 1 and lb[0]["goals"] == 7
    code, body = _req(server.url + "api/history")
    data = json.loads(body)
    assert data["count"] == 2 and data["leaderboard"]
    code, body = _req(server.url + "api/history.csv")
    assert "سارا" in body.decode("utf-8-sig")


def test_game_applies_web_commands(tmp_path):
    from market_hockey.app import GameApp

    app = GameApp(headless=True, seed=1)
    app.web = SupervisorServer("127.0.0.1", 0, history_path=tmp_path / "h.jsonl")
    assert app.web.start()
    try:
        _req(app.web.url + "api/names", {"p1": "نگار", "p2": "Reza"})
        _req(app.web.url + "api/start", {})
        app._poll_web(time.perf_counter())
        assert app.engine.names == ["نگار", "Reza"] and app.engine.state == "INTRO"
        snap = json.loads(_req(app.web.url + "api/state")[1])
        assert snap["names"] == ["نگار", "Reza"] and snap["state"] == "INTRO" and len(snap["colors"]) == 2
    finally:
        app.web.stop()
        app.shutdown()


def test_single_name_and_addresses(server):
    from market_hockey.web.server import local_addresses

    _req(server.url + "api/name", {"player": 1, "name": "آرش"})
    assert server.drain() == [("name", {"player": 1, "name": "آرش"})]
    ips = local_addresses()
    assert all(not ip.startswith(("127.", "169.254.", "240.")) for ip in ips)
    assert server.urls()[0].startswith("http://127.0.0.1:")


def test_waiting_screen_text_never_overlaps(tmp_path):
    from market_hockey.app import GameApp

    app = GameApp(headless=True, seed=4)
    app.cfg.set("input.p1.source", "ai")
    app.cfg.set("input.p2.source", "ai")
    app.cfg.set("match.attract_toasts", True)  # worst case: demo pop-ups on
    app.engine.set_names("سارا احمدی", "Reza Karimi")
    t = 0.0
    try:
        for _ in range(600):
            t += 1 / 60
            app.tick(1 / 60, t)
            rs = app.renderer._reserved
            for i in range(len(rs)):
                for j in range(i + 1, len(rs)):
                    assert not rs[i].colliderect(rs[j]), (rs[i], rs[j])
    finally:
        app.shutdown()


def test_demo_message_waits_when_the_waiting_screen_is_full():
    from market_hockey.app import GameApp

    app = GameApp(headless=True, seed=4)
    app.engine.set_names("سارا احمدی", "Reza Karimi")
    r = app.renderer
    t = 0.0
    try:
        for _ in range(3):
            t += 1 / 60
            app.tick(1 / 60, t)
        for _ in range(2):  # the most one side can hold, and more than fit beside a name
            r.toast("حجم معاملات افزایش یافت!", (255, 255, 255), 1)
        for _ in range(5):
            t += 1 / 60
            app.tick(1 / 60, t)
            rs = r._reserved
            assert all(not a.colliderect(b) for i, a in enumerate(rs) for b in rs[i + 1:])
        assert len(r.toasts) == 2 and "pos" not in r.toasts[1]  # no room yet: it is kept until a spot frees up
    finally:
        app.shutdown()
