"""Project-local session documents. Exports deliberately live outside sessions."""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path

ROOT = Path(os.environ.get("FPV_AUDIO_DATA_DIR", Path(__file__).resolve().parent.parent / "data")).resolve()
LOCK = threading.RLock()


def identifier(value):
    if not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Invalid identifier")
    return value


def directory(sid):
    return ROOT / "sessions" / identifier(sid)


def read(sid):
    with LOCK:
        return json.loads((directory(sid) / "session.json").read_text(encoding="utf-8"))


def write(session):
    with LOCK:
        folder = directory(session["id"])
        folder.mkdir(parents=True, exist_ok=True)
        temp = folder / f".{uuid.uuid4().hex}.tmp"
        try:
            temp.write_text(json.dumps(session, indent=2, allow_nan=False), encoding="utf-8")
            os.replace(temp, folder / "session.json")
        finally:
            temp.unlink(missing_ok=True)


def update(sid, change):
    with LOCK:
        session = read(sid)
        change(session)
        write(session)
        return session


def sessions():
    result = []
    for path in (ROOT / "sessions").glob("*/session.json"):
        try:
            result.append(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return sorted(result, key=lambda s: s["created"], reverse=True)
