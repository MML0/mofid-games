"""The supervisor page faces a network: bad requests get proper errors, the game never sees them."""

import json
import urllib.error
import urllib.request

import pytest

from land_hockey.web import history
from land_hockey.web.server import MAX_BODY, SupervisorServer, local_addresses


@pytest.fixture
def server(tmp_path):
    srv = SupervisorServer("127.0.0.1", 0, history_path=tmp_path / "h.jsonl")
    assert srv.start()
    yield srv
    srv.stop()


def call(url, data=None, method=None, ctype="application/json", raw=None):
    body = raw if raw is not None else (None if data is None else json.dumps(data).encode())
    req = urllib.request.Request(url, data=body, method=method or ("POST" if body is not None else "GET"))
    if ctype and body is not None:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


@pytest.mark.parametrize("path", ["nope", "api/nope", "fonts/nope.ttf", "fonts/settings.json", "fonts/..%2F..%2Fmain.py",
                                  "config/settings.json", "../config/settings.json"])
def test_unknown_paths_are_404(server, path):
    assert call(server.url + path)[0] == 404


def test_post_to_an_unknown_route_is_404(server):
    assert call(server.url + "api/nope", {})[0] == 404


@pytest.mark.parametrize("raw", [b"not json", b"[1,2]", b"7", b"\xff\xfe"])
def test_bad_json_is_400_and_reaches_no_one(server, raw):
    assert call(server.url + "api/names", raw=raw)[0] == 400
    assert server.drain() == []


def test_huge_bodies_are_refused(server):
    assert call(server.url + "api/names", raw=b"x" * (MAX_BODY + 1))[0] == 413
    assert server.drain() == []


def test_names_are_trimmed_to_a_safe_length(server):
    call(server.url + "api/names", {"p1": "x" * 500, "p2": 5})
    cmd, body = server.drain()[0]
    assert cmd == "names" and len(body["p1"]) == 40 and body["p2"] == "5"


@pytest.mark.parametrize("player,idx", [(1, 1), (0, 0), ("1", 1), ("x", 0), (None, 0), (7, 0)])
def test_single_name_player_index_is_always_valid(server, player, idx):
    call(server.url + "api/name", {"player": player, "name": "A"})
    assert server.drain()[0][1]["player"] == idx


@pytest.mark.parametrize("route,cmd", [("start", "start"), ("pause", "pause"), ("reset", "reset"),
                                       ("clear_names", "clear_names")])
def test_buttons_become_commands_in_order(server, route, cmd):
    assert call(server.url + f"api/{route}", {})[0] == 200
    assert server.drain() == [(cmd, {})]


def test_head_requests_send_no_body(server):
    code, body, headers = call(server.url, method="HEAD")
    assert code == 200 and body == b"" and int(headers["Content-Length"]) > 0


def test_responses_are_not_cached_or_sniffed(server):
    _c, _b, headers = call(server.url + "api/state")
    assert headers["Cache-Control"] == "no-store" and headers["X-Content-Type-Options"] == "nosniff"


def test_csv_download_opens_correctly_in_excel(server, tmp_path):
    ev = {"scores": [3, 5], "winner": 1, "duration": 60, "golden": False, "stats": {}}
    history.append(history.make_record(ev, ["سارا", "علی"], ["a", "b"]), tmp_path / "h.jsonl")
    code, body, headers = call(server.url + "api/history.csv")
    assert code == 200 and body.startswith(b"\xef\xbb\xbf")  # the BOM keeps Persian readable in Excel
    assert "attachment" in headers["Content-Disposition"]
    assert "سارا" in body.decode("utf-8-sig") and "علی" in body.decode("utf-8-sig")


def test_history_api_shape(server, tmp_path):
    code, body, _h = call(server.url + "api/history")
    assert code == 200 and json.loads(body) == {"matches": [], "leaderboard": [], "count": 0}


def test_port_in_use_is_reported_not_raised(server):
    other = SupervisorServer("127.0.0.1", server.port)
    assert other.start() is False
    other.stop()


def test_addresses_for_phones():
    srv = SupervisorServer("0.0.0.0", 8765)
    assert srv.url == "http://127.0.0.1:8765/"
    assert srv.urls()[0] == "http://127.0.0.1:8765/"
    assert SupervisorServer("127.0.0.1", 1).urls() == ["http://127.0.0.1:1/"]
    assert all("." in ip and not ip.startswith("127.") for ip in local_addresses())


def test_snapshot_is_a_copy(server):
    server.publish({"a": 1})
    snap = server.snapshot()
    snap["a"] = 2
    assert server.snapshot() == {"a": 1}


# ---------------------------------------------------------------- history file
def test_draws_and_missing_stats_are_recorded(tmp_path):
    rec = history.make_record({"scores": [2, 2], "winner": None}, ["", ""], ["P1", "P2"])
    assert rec["winner"] is None and rec["players"][0] == {"name": "P1", "score": 2, "powerups": 0, "smart": 0}
    assert "draw" in history.to_csv([rec])


def test_damaged_history_lines_are_skipped(tmp_path):
    path = tmp_path / "h.jsonl"
    path.write_text('\n{"players": []}\nbroken\n[1]\n{"no_players": 1}\n', encoding="utf-8")
    assert len(history.read_all(path)) == 1


def test_history_limit_and_order(tmp_path):
    path = tmp_path / "h.jsonl"
    for k in range(5):
        history.append({"players": [], "n": k}, path)
    assert [r["n"] for r in history.read_all(path, limit=2)] == [4, 3]


def test_unwritable_history_only_warns(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    history.append({"players": []}, blocker / "h.jsonl")


def test_unreadable_history_reads_as_empty(tmp_path):
    assert history.read_all(tmp_path) == []
    assert history.read_all(tmp_path / "none.jsonl") == []


def test_leaderboard_ranks_by_wins_then_goals():
    rec = lambda a, sa, b, sb, w: {"time": "t", "players": [{"name": a, "score": sa}, {"name": b, "score": sb}], "winner": w}
    lb = history.leaderboard([rec("A", 3, "B", 5, 1), rec("C", 9, "A", 0, 0), rec("B", 1, "C", 2, 1)])
    assert [r["name"] for r in lb] == ["C", "B", "A"]
    assert lb[0]["wins"] == 2 and lb[0]["best"] == 9
