"""Project-local session documents. Exports deliberately live outside sessions."""
from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import uuid
import shutil
from pathlib import Path

ROOT = Path(os.environ.get("FPV_AUDIO_DATA_DIR", Path(__file__).resolve().parent.parent / "data")).resolve()
LOCK = threading.RLock()
REPLACE_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.5, 0.75)
SCHEMA_VERSION = 2
_INSTANCE = None


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


def _decode(path, sid):
    result = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(result, dict) or result.get("id") != sid or not isinstance(result.get("name"), str)
        or not isinstance(result.get("created"), (int, float)) or not math.isfinite(result["created"])
        or not all(isinstance(result.get(k), list) for k in ("videos", "pairs", "exports"))
        or not isinstance(result.get("folders"), dict)):
        raise ValueError("Unreadable session document structure")
    return result


def read(sid):
    with LOCK:
        try:
            result = _decode(directory(sid) / "session.json", sid)
        except (ValueError, OSError):
            for backup in backups(sid):
                try:
                    result = _decode(directory(sid) / "backups" / backup["name"], sid)
                    result["recovery_required"] = backup["name"]
                    return result
                except (ValueError, OSError):
                    continue
            raise
        return result


def backups(sid):
    return [{"name": p.name, "created": p.stat().st_mtime} for p in
            sorted((directory(sid) / "backups").glob("*.json"), reverse=True)]


def checkpoint(sid, force=False):
    with LOCK:
        folder = directory(sid)
        source = folder / "session.json"
        if not source.exists():
            return
        existing = backups(sid)
        if not force and existing and time.time() - existing[0]["created"] < 60:
            return
        # Back up only readable documents, never replace a good backup with a
        # corrupt current file. Snapshots contain metadata, not originals.
        _decode(source, sid)
        target = folder / "backups" / f"{time.time_ns()}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        for old in backups(sid)[10:]:
            (target.parent / old["name"]).unlink(missing_ok=True)


def restore(sid, name):
    if name not in {b["name"] for b in backups(sid)}:
        raise ValueError("Choose an available session backup")
    with LOCK:
        result = _decode(directory(sid) / "backups" / name, sid)
        result["id"] = sid
        result.pop("recovery_required", None)
        # Preserve current metadata, even if corrupt, for manual recovery.
        current = directory(sid) / "session.json"
        if current.exists():
            shutil.copyfile(current, directory(sid) / f"before-restore-{time.time_ns()}.json")
        if result.get("job"):
            result["job"].update(status="interrupted", message="Backup restored. Resume or restart the task.")
        write(result, backup=False)
        return result


def write(session, backup=True):
    with LOCK:
        if session.get("recovery_required"):
            raise SessionSaveError("The session JSON is unreadable. Restore the offered backup before editing this session.")
        session["schema_version"] = SCHEMA_VERSION
        session["saved_at"] = time.time()
        payload = json.dumps(session, indent=2, allow_nan=False)
        folder = directory(session["id"])
        temp = folder / f".{uuid.uuid4().hex}.tmp"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if backup:
                checkpoint(session["id"])
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
                result.append(read(path.parent.name))
            except (ValueError, OSError):
                continue
        return sorted(result, key=lambda s: s["created"], reverse=True)


def acquire_instance():
    """Prevent two local processes from concurrently writing the same data."""
    global _INSTANCE
    ROOT.mkdir(parents=True, exist_ok=True)
    handle = (ROOT / ".app.lock").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            if not handle.read(1):
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError(f"Another Flight Sync instance is using {ROOT}. Close it or choose a separate FPV_AUDIO_DATA_DIR.") from None
    _INSTANCE = handle
