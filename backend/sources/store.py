"""Record/replay for every outside call, so the app runs the same offline from data/samples/.

live mode     -> call the internet; if recording is on, also save the answer to the snapshot.
snapshot mode -> never touch the internet; answer from the saved snapshot or fail loudly.
"""
from pathlib import Path
from typing import Any, Callable
import hashlib
import json
import os

from backend import config


class NotInSnapshot(LookupError):
    pass


def snapshot_dir(name: str | None = None) -> Path:
    return config.DATA / "samples" / (name or config.SNAPSHOT)


def _path(kind: str, key: dict) -> Path:
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]
    return snapshot_dir() / "cache" / kind / f"{digest}.json"


def recording() -> bool:
    return os.getenv("VILLA_RECORD") == "1"


def cached_call(kind: str, key: dict, live: Callable[[], Any], recordable: bool = True) -> Any:
    """Return `live()` in live mode, the saved copy in snapshot mode.

    recordable=False keeps a result out of the snapshot (e.g. full news articles, which are
    copyrighted and must not be committed to a public repo).
    """
    path = _path(kind, key)
    if config.SOURCE_MODE == "snapshot":
        if not path.exists():
            raise NotInSnapshot(f"{kind} {key} is not in snapshot '{config.SNAPSHOT}'")
        return json.loads(path.read_text())["value"]
    value = live()
    if recording() and recordable:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"kind": kind, "key": key, "value": value}, indent=1, ensure_ascii=False))
    return value
