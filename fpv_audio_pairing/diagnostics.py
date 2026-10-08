"""Local installation checks. Reports omit source paths unless requested."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from importlib.metadata import version
from pathlib import Path

from . import store, preview


def check_folder(path, write=False):
    p = Path(path).expanduser().resolve()
    try:
        if write:
            parent = p
            while not parent.exists():
                parent = parent.parent
            with tempfile.TemporaryFile(dir=parent):
                pass
            space = shutil.disk_usage(parent)
            return {"available": True, "free_bytes": space.free, "exists": p.is_dir()}
        if not p.is_dir():
            raise OSError("Folder is unavailable")
        next(p.iterdir(), None)
        return {"available": True}
    except OSError as exc:
        return {"available": False, "error": str(exc)}


def report(doc=None, include_paths=False):
    result = {"app_version": version("fpv-audio-pairing"), "python": platform.python_version(),
              "platform": platform.system(), "platform_release": platform.release(), "tools": {},
              "data_folder": check_folder(store.ROOT, True), "preview_decoders": preview.hardware_decoders(),
              "instance_lock": store._INSTANCE is not None}
    for name in ("ffmpeg", "ffprobe"):
        exe = shutil.which(name)
        item = {"available": bool(exe)}
        if exe:
            try:
                output = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=10)
                item.update(version=output.stdout.splitlines()[0], working=output.returncode == 0)
            except (OSError, subprocess.TimeoutExpired, IndexError) as exc:
                item.update(working=False, error=type(exc).__name__)
        if include_paths:
            item["path"] = exe
        result["tools"][name] = item
    if doc:
        result["source_folders"] = {kind: check_folder(path) for kind, path in doc["folders"].items()}
        result["output_folder"] = check_folder(doc.get("export_destination") or store.ROOT / "exports", True)
        result["recordings"] = len(doc["videos"])
        result["job"] = {k: doc.get("job", {}).get(k) for k in ("status", "title", "percent", "persistence_failed")}
        if include_paths:
            result["paths"] = {"sources": doc["folders"], "data": str(store.ROOT), "output": doc.get("export_destination")}
    # Error strings from permission checks can contain private paths.
    if not include_paths:
        for item in [result["data_folder"], *result.get("source_folders", {}).values(), result.get("output_folder", {})]:
            if item.get("error"):
                item["error"] = "Folder unavailable or permission denied; check locally."
    result["note"] = "Local report; not uploaded. GPU decoder availability is not a codec compatibility guarantee."
    return result
