"""Project-local session documents. Exports deliberately live outside sessions."""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(os.environ.get("FPV_AUDIO_DATA_DIR", Path(__file__).resolve().parent.parent / "data")).resolve()
LOCK = threading.RLock()
REPLACE_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.5, 0.75)


class SessionSaveError(RuntimeError):
    """A session could not be saved; existing saved data was not removed."""


def _replace_session(temp: Path, target: Path):
    # Windows can temporarily deny a rename while a reader, virus scanner or
    # indexer has the file open. Keep atomic replacement and bound the wait to
    # two seconds; genuine/persistent access problems must remain visible.
    for attempt in range(len(REPLACE_DELAYS) + 1):
        try:
            os.replace(temp, target)
            return
        except OSError as error:
            if getattr(error, "winerror", None) in {5, 32, 33} and attempt < len(REPLACE_DELAYS):
                time.sleep(REPLACE_DELAYS[attempt])
                continue
            raise SessionSaveError(
                f"Could not save session JSON at '{target}'. Existing saved data has not been removed. "
                f"The new JSON is retained at '{temp}' for recovery. Close other app instances or "
                f"programs using this file, and check that the data folder and session.json are writable. "
                f"You can select a writable data folder with FPV_AUDIO_DATA_DIR. Details: {error}"
            ) from error


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
        payload = json.dumps(session, indent=2, allow_nan=False)
        folder = directory(session["id"])
        temp = folder / f".{uuid.uuid4().hex}.tmp"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            # write_text closes its handle before the atomic replacement.
            temp.write_text(payload, encoding="utf-8")
        except OSError as error:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass  # Cleanup must not obscure the original write failure.
            raise SessionSaveError(
                f"Could not write session data in '{folder}'. Check that the folder is writable, "
                f"or choose a writable folder with FPV_AUDIO_DATA_DIR. Details: {error}"
            ) from error
        _replace_session(temp, folder / "session.json")


def update(sid, change):
    with LOCK:
        session = read(sid)
        change(session)
        write(session)
        return session


def sessions():
    # The frontend polls this list while workers save progress. Protect these
    # readers too: an open file can prevent its replacement on Windows.
    with LOCK:
        result = []
        for path in (ROOT / "sessions").glob("*/session.json"):
            try:
                result.append(json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
        return sorted(result, key=lambda s: s["created"], reverse=True)
