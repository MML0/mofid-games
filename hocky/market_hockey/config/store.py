"""Config store: validated flat values, nested JSON on disk, atomic saves, change tracking."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from collections import deque
from pathlib import Path
from typing import Any

from .schema import SCHEMA_VERSION, Param, get_schema

log = logging.getLogger(__name__)

_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")
META_KEY = "_meta"


def coerce(p: Param, value: Any) -> tuple[Any, str | None]:
    """Return (valid value, warning or None). Never raises."""
    if value is None:
        return p.default, f"{p.path}: missing value"
    try:
        if p.kind == "float":
            v = float(value)
            if v != v:  # NaN
                raise ValueError("NaN")
            nv = min(max(v, p.min), p.max) if p.min is not None else v
            return nv, (f"{p.path}: {v} clamped to {nv}" if nv != v else None)
        if p.kind == "int":
            v = int(round(float(value)))
            nv = min(max(v, int(p.min)), int(p.max)) if p.min is not None else v
            return nv, (f"{p.path}: {v} clamped to {nv}" if nv != v else None)
        if p.kind == "bool":
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on"), None
            return bool(value), None
        if p.kind == "color":
            s = str(value).strip()
            if not _HEX.match(s):
                return p.default, f"{p.path}: invalid color {value!r}"
            return ("#" + s.lstrip("#")).upper(), None
        if p.kind in ("enum", "font"):
            s = str(value)
            if p.kind == "enum" and s not in p.options:
                return p.default, f"{p.path}: {value!r} not one of {p.options}"
            return s, None
        if p.kind in ("str", "key"):
            return str(value), None
    except (TypeError, ValueError, OverflowError) as exc:
        return p.default, f"{p.path}: invalid value {value!r} ({exc})"
    return p.default, f"{p.path}: unknown kind {p.kind}"


def flatten(d: dict, prefix: str = "") -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        if k == META_KEY and not prefix:
            continue
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, path))
        else:
            out[path] = v
    return out


def nest(flat: dict[str, Any]) -> dict:
    root: dict = {}
    for path, v in flat.items():
        cur = root
        parts = path.split(".")
        for part in parts[:-1]:
            nxt = cur.setdefault(part, {})
            if not isinstance(nxt, dict):  # a leaf collides with a branch; keep the leaf under "_value"
                nxt = cur[part] = {"_value": nxt}
            cur = nxt
        cur[parts[-1]] = v
    return root


V2_DEFAULT_CHANGES = {
    "powerups.magnet.strength": (900.0, 2200.0),
    "powerups.magnet.radius": (200, 260),
    "powerups.magnet.max_offset": (80, 120),
    "powerups.spawn_interval_min_s": (4.0, 2.5),
    "powerups.spawn_interval_max_s": (7.0, 5.0),
    "powerups.max_active_orbs": (2, 3),
    "powerups.types.trajectory_reveal.class": ("bad", "good"),
    "powerups.types.trajectory_reveal.toast_collector": ("مسیرت لو رفت!", "مسیر حرکت را تحلیل کن!"),
    "powerups.types.trajectory_reveal.toast_opponent": ("مسیر حرکت را تحلیل کن!", ""),
    "colors.wall": ("#CFE8EE", "#A8F0FF"),
    "trails.duration_s": (0.35, 0.45),
    "trails.glow": (0.6, 0.8),
    "input.ai.noise": (0.06, 0.04),
}


def _v1_to_v2(flat: dict) -> dict:
    """New defaults replace old defaults, but values the operator changed are kept."""
    for key, (old, new) in V2_DEFAULT_CHANGES.items():
        if key not in flat or flat[key] == old:
            flat[key] = new
    return flat


V3_DEFAULT_CHANGES = {
    "powerups.types.chaos.mode": ("instant", "sequence"),
    "powerups.types.chaos.toast_collector": ("بازار غیرقابل پیش\u200cبینی شد!", ""),
    "powerups.types.trajectory_reveal.duration_s": (7.0, 12.0),
    "powerups.types.double_ball.split_angle_deg": (18.0, 24.0),
    "prediction.assist_alpha": (0.22, 0.13),
    "prediction.assist_arrow": (False, True),
    "powerups.types.expand.toast_collector": ("بالکرت بزرگ شد!", "پدلت بزرگ شد!"),
    "powerups.types.shrink.toast_collector": ("بالکر حریف کوچک شد!", "پدل حریف کوچک شد!"),
    "powerups.types.shrink.toast_opponent": ("بالکرت کوچک شد!", "پدلت کوچک شد!"),
}


def _changes(table: dict):
    def mig(flat: dict) -> dict:
        for key, (old, new) in table.items():
            if key not in flat or flat[key] == old:
                flat[key] = new
        return flat
    return mig


V4_DEFAULT_CHANGES = {f"paddles.{pid}.{k}": v for pid in ("p1", "p2") for k, v in {
    "velocity_transfer": (0.35, 0.1),
    "paddle_speed_to_ball": (0.25, 0.1),
    "max_outgoing_angle_deg": (72.0, 55.0),
}.items()}

V5_DEFAULT_CHANGES = {
    "web.bind": ("127.0.0.1", "0.0.0.0"),
    "text.toast_size": (40, 34),
    "text.banner_size": (64, 56),
}

V6_DEFAULT_CHANGES = {
    "powerups.types.chaos.intro_s": (1.1, 0.55),
    "powerups.types.chaos.select_s": (1.0, 0.5),
    "powerups.types.chaos.reroll_select_s": (0.6, 0.3),
    "powerups.types.chaos.fire_mult": (1.1, 1.0),
}

# Migrations: {from_version: function(flat_dict) -> flat_dict}
MIGRATIONS: dict[int, Any] = {1: _v1_to_v2, 2: _changes(V3_DEFAULT_CHANGES), 3: _changes(V4_DEFAULT_CHANGES),
                              4: _changes(V5_DEFAULT_CHANGES), 5: _changes(V6_DEFAULT_CHANGES)}


class Config:
    """Flat dict of validated values. Unknown keys are preserved but ignored by the game."""

    def __init__(self, values: dict[str, Any] | None = None, extra: dict[str, Any] | None = None):
        self.schema = get_schema()
        self.values: dict[str, Any] = {k: p.default for k, p in self.schema.items()}
        self.extra: dict[str, Any] = dict(extra or {})
        self.warnings: list[str] = []
        self.version = 0
        self._log: deque = deque(maxlen=4000)
        if values:
            for k, v in values.items():
                self.set(k, v, record=False)
        self.version = 1

    # ---- access ---------------------------------------------------------------
    def __getitem__(self, path: str) -> Any:
        return self.values[path]

    def get(self, path: str, default: Any = None) -> Any:
        return self.values.get(path, default)

    def __contains__(self, path: str) -> bool:
        return path in self.values

    # ---- mutation -------------------------------------------------------------
    def set(self, path: str, value: Any, record: bool = True) -> tuple[bool, Any, str | None]:
        p = self.schema.get(path)
        if p is None:
            self.extra[path] = value
            return False, value, f"unknown setting {path} (kept, ignored)"
        v, warn = coerce(p, value)
        if warn:
            self.warnings.append(warn)
            log.warning(warn)
        if self.values.get(path) != v:
            self.values[path] = v
            self.version += 1
            self._log.append((self.version, path))
        return True, v, warn

    def update(self, values: dict[str, Any]) -> list[str]:
        warns = []
        for k, v in values.items():
            _, _, w = self.set(k, v)
            if w:
                warns.append(w)
        return warns

    def reset_defaults(self) -> None:
        self.update({k: p.default for k, p in self.schema.items()})

    def changes_since(self, version: int) -> set[str]:
        """Paths changed after `version`. Returns {'*'} if the log no longer reaches that far."""
        if version >= self.version:
            return set()
        if not self._log or self._log[0][0] > version + 1:
            return {"*"}
        return {path for v, path in self._log if v > version}

    def snapshot(self) -> dict[str, Any]:
        return dict(self.values)

    # ---- persistence ----------------------------------------------------------
    def to_json_obj(self) -> dict:
        data = nest({**self.extra, **self.values})
        data[META_KEY] = {"schema_version": SCHEMA_VERSION, "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                          "app": "Market Hockey"}
        return data

    def save(self, path: Path, backup: Path | None = None) -> None:
        """Atomic save: write temp file, fsync, replace. Keeps the previous file as a backup."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        text = json.dumps(self.to_json_obj(), ensure_ascii=False, indent=2, sort_keys=False)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if backup is not None and path.exists():
            try:
                shutil.copy2(path, backup)
            except OSError as exc:
                log.warning("could not write backup %s: %s", backup, exc)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path | None) -> "Config":
        if path is None or not Path(path).exists():
            cfg = cls()
            if path is not None:
                cfg.warnings.append(f"{path} not found, using defaults")
            return cfg
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
            if not isinstance(raw, dict):
                raise ValueError("top level is not an object")
        except (OSError, ValueError) as exc:
            cfg = cls()
            cfg.warnings.append(f"could not read {path} ({exc}); using defaults")
            log.error(cfg.warnings[-1])
            return cfg
        try:
            version = int(raw.get(META_KEY, {}).get("schema_version", SCHEMA_VERSION))
        except (AttributeError, TypeError, ValueError, OverflowError):  # damaged _meta: treat the values as current
            version = SCHEMA_VERSION
        flat = flatten(raw)
        while version < SCHEMA_VERSION:
            mig = MIGRATIONS.get(version)
            if mig:
                flat = mig(flat)
            version += 1
        schema = get_schema()
        known = {k: v for k, v in flat.items() if k in schema}
        extra = {k: v for k, v in flat.items() if k not in schema}
        cfg = cls(known, extra)
        for k in extra:
            cfg.warnings.append(f"unknown setting {k} preserved")
        return cfg

    @staticmethod
    def read_flat(path: Path) -> dict[str, Any]:
        with open(path, encoding="utf-8") as fh:
            return flatten(json.load(fh))
