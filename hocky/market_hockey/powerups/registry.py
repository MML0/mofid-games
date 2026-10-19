"""Auto-discovers power-up types in `powerups/types/`."""

from __future__ import annotations

import importlib
import logging
import pkgutil

log = logging.getLogger(__name__)
_TYPES: dict = {}
_DISCOVERED = False


def register(cls):
    inst = cls()
    if not inst.id:
        raise ValueError(f"{cls.__name__} has no id")
    _TYPES[inst.id] = inst
    return cls


def discover() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return
    from . import types as pkg

    for mod in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        if mod.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{pkg.__name__}.{mod.name}")
        except Exception:  # a broken power-up file must never take the game down
            log.exception("failed to load power-up module %s", mod.name)
    _DISCOVERED = True


def all_types() -> dict:
    discover()
    return dict(sorted(_TYPES.items(), key=lambda kv: (kv[1].order, kv[0])))


def get(type_id: str):
    discover()
    return _TYPES.get(type_id)
