"""Match history (logs/history.jsonl): one JSON object per finished match. Append-only, human readable."""

from __future__ import annotations

import csv
import io
import json
import logging
import time

from ..paths import LOGS_DIR

log = logging.getLogger(__name__)
HISTORY_PATH = LOGS_DIR / "history.jsonl"


def append(record: dict, path=None) -> None:
    path = path or HISTORY_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("could not write %s: %s", path, exc)


def make_record(event: dict, names: list[str], fallback: list[str]) -> dict:
    st = event.get("stats") or {}
    w = event.get("winner")
    return {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(float(event.get("duration", 0.0)), 1),
        "players": [
            {"name": names[i] or fallback[i], "score": int(event["scores"][i]),
             "powerups": int((st.get("powerups") or [0, 0])[i]), "smart": int((st.get("smart") or [0, 0])[i])}
            for i in (0, 1)],
        "winner": w,
        "golden_goal": bool(event.get("golden")),
    }


def read_all(path=None, limit: int | None = None) -> list[dict]:
    """Newest first. Damaged lines are skipped."""
    path = path or HISTORY_PATH
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict) and "players" in rec:
                        out.append(rec)
                except ValueError:
                    continue
    except FileNotFoundError:
        return []
    except OSError as exc:
        log.warning("could not read %s: %s", path, exc)
        return []
    out.reverse()
    return out[:limit] if limit else out


def leaderboard(records: list[dict]) -> list[dict]:
    table: dict[str, dict] = {}
    for rec in records:
        for i, pl in enumerate(rec.get("players", [])[:2]):
            name = str(pl.get("name", "")).strip() or "?"
            row = table.setdefault(name, {"name": name, "games": 0, "wins": 0, "goals": 0, "best": 0, "last": ""})
            row["games"] += 1
            row["goals"] += int(pl.get("score", 0))
            row["best"] = max(row["best"], int(pl.get("score", 0)))
            row["wins"] += 1 if rec.get("winner") == i else 0
            row["last"] = max(row["last"], rec.get("time", ""))
    return sorted(table.values(), key=lambda r: (-r["wins"], -r["goals"], -r["best"], r["name"]))


def to_csv(records: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time", "player_1", "score_1", "player_2", "score_2", "winner", "golden_goal", "duration_s"])
    for r in records:
        p = r.get("players", [{}, {}])
        win = r.get("winner")
        w.writerow([r.get("time"), p[0].get("name"), p[0].get("score"), p[1].get("name"), p[1].get("score"),
                    "draw" if win is None else p[win].get("name"), r.get("golden_goal"), r.get("duration_s")])
    return buf.getvalue()
