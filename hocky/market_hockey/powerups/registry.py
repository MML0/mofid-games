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

    names = sorted(m.name for m in pkgutil.iter_modules(pkg.__path__) if not m.name.startswith("_"))
    if not names:  # some packaged builds cannot list modules; use the built-in list
        names = list(getattr(pkg, "BUILTIN", []))
    for name in names:
        try:
            importlib.import_module(f"{pkg.__name__}.{name}")
        except Exception:  # a broken power-up file must never take the game down
            log.exception("failed to load power-up module %s", name)
    _DISCOVERED = True


def all_types() -> dict:
    discover()
    return dict(sorted(_TYPES.items(), key=lambda kv: (kv[1].order, kv[0])))


def get(type_id: str):
    discover()
    return _TYPES.get(type_id)
