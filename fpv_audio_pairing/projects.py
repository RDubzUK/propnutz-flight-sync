"""Portable project documents, bounded fingerprint bundles and safe relinking."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import time
import uuid
import zipfile
from pathlib import Path

from . import store, matching, review

MAX_PROJECT = 16 * 1024 ** 2
MAX_BUNDLE = 128 * 1024 ** 2
FORMAT = "propnutz-flight-sync"


def content_id(path):
    """Bounded head/tail fingerprint, not a claim of whole-file integrity."""
    p = Path(path)
    before = p.stat()
    digest = hashlib.sha256(str(before.st_size).encode())
    with p.open("rb") as stream:
        digest.update(stream.read(128 * 1024))
        stream.seek(max(0, before.st_size - 128 * 1024))
        digest.update(stream.read(128 * 1024))
    after = p.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"{p.name} changed while checking its identity")
    return "head-tail-v1:" + digest.hexdigest()


def document(doc):
    from .cache import _key
    from .fingerprint import ALGORITHM_VERSION
    result = copy.deepcopy(doc)
    for r in result["videos"]:
        if not r.get("content_id") and Path(r["path"]).is_file():
            r["content_id"] = content_id(r["path"])
        if Path(r["path"]).is_file():
            keys = r.setdefault("audio_cache_keys", {})
            for b in {30., 60., 120., 300., float(r.get("audio_boundary", 30))}:
                keys.setdefault(str(float(b)), _key(r["path"], ALGORITHM_VERSION, {"boundary_seconds": float(b)}))
        try:
            r["relative_path"] = str(Path(r["path"]).relative_to(Path(doc["folders"][r["kind"]])))
        except ValueError:
            r["relative_path"] = r["name"]
    # Export history stays at its original installation; no imported job can
    # overwrite paths or resume commands from somebody else's document.
    for key in ("job", "exports", "flights", "review_summary", "recovery_required"):
        result.pop(key, None)
    return {"format": FORMAT, "format_version": 1, "saved": time.time(), "session": result}


def bundle(doc):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("project.json", json.dumps(document(doc), allow_nan=False))
        total = 0
        for path in sorted((store.directory(doc["id"]) / "audio").glob("audio.*.npz")):
            total += path.stat().st_size
            if total > MAX_BUNDLE - MAX_PROJECT:
                raise ValueError("Fingerprint bundle exceeds 112 MiB. Save JSON instead; audio can be prepared again.")
            archive.write(path, f"audio/{path.name}")
    return buffer.getvalue()


def _validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("The project must be a JSON object")
    if payload.get("format") != FORMAT or payload.get("format_version") != 1:
        raise ValueError("Choose a Flight Sync project JSON or project bundle")
    doc = payload["session"]
    if not isinstance(doc, dict) or not isinstance(doc.get("videos"), list) or not isinstance(doc.get("pairs"), list):
        raise ValueError("Invalid session recordings/pairs")
    if doc.get("schema_version", 1) > store.SCHEMA_VERSION:
        raise ValueError("This project needs a newer Flight Sync version")
    if not isinstance(doc.get("name"), str) or not 1 <= len(doc["name"]) <= 120:
        raise ValueError("Invalid session name")
    if set(doc["folders"]) != {"fpv", "stick"} or not all(isinstance(p, str) and len(p) <= 4096 for p in doc["folders"].values()):
        raise ValueError("Invalid source folders")
    ids = set()
    for r in doc["videos"]:
        store.identifier(r["id"])
        if r["id"] in ids or r["kind"] not in {"fpv", "stick"}:
            raise ValueError("Invalid or duplicate recording")
        ids.add(r["id"])
        if not isinstance(r["path"], str) or not isinstance(r["name"], str) or not math.isfinite(r["mtime"]):
            raise ValueError("Invalid recording metadata")
        if "/" in r["name"] or "\\" in r["name"] or r["name"] in {"", ".", ".."}:
            raise ValueError("Invalid recording filename")
        info = r.get("metadata")
        if info and (not all(math.isfinite(info[k]) and info[k] > 0 for k in ("duration", "fps", "width", "height")) or
                     not isinstance(info.get("has_audio"), bool)):
            raise ValueError("Invalid recording duration/frame rate")
        if len(r["signature"]) != 2 or not all(isinstance(v, int) and v >= 0 for v in r["signature"]):
            raise ValueError("Invalid source signature")
    for p in doc["pairs"]:
        store.identifier(p["id"])
        if p["fpv"] not in ids or p["stick"] not in ids or not math.isfinite(p["offset"]):
            raise ValueError("Invalid pair or offset")
        if next(r for r in doc["videos"] if r["id"] == p["fpv"])["kind"] != "fpv" or next(r for r in doc["videos"] if r["id"] == p["stick"])["kind"] != "stick":
            raise ValueError("Pair recordings must have opposite types")
        p.setdefault("confidence", "Imported alignment")
        p.setdefault("confirmed", False)
        p.setdefault("method", "manual")
        if p.get("review_state", "candidate") not in {"candidate", "confirmed", "later", "rejected"}:
            raise ValueError("Invalid review decision")
        for point in p.get("sync_points", []):
            store.identifier(point["id"])
            if not all(math.isfinite(point[k]) and point[k] >= 0 for k in ("fpv_time", "stick_time")):
                raise ValueError("Invalid sync checkpoint")
    for ref in doc.get("references", []):
        if ref["fpv"] not in ids or ref["stick"] not in ids or not isinstance(ref["match"], bool):
            raise ValueError("Invalid reference pair")
        if ref["match"] and ref.get("expected_offset") is not None and not math.isfinite(ref["expected_offset"]):
            raise ValueError("Invalid reference offset")
        if not math.isfinite(ref.get("tolerance", .15)) or not .01 <= ref.get("tolerance", .15) <= 2:
            raise ValueError("Invalid reference tolerance")
    if not 1 <= doc.get("modified_tolerance", 5) <= 10 or doc.get("modified_kind", "end") not in {"start", "end"}:
        raise ValueError("Invalid modified-date settings")
    return doc


def open_project(raw):
    caches = []
    if raw.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(i.file_size for i in archive.infolist()) > MAX_BUNDLE or len(archive.infolist()) > 10000:
                raise ValueError("Project bundle is too large")
            info = archive.getinfo("project.json")
            if info.file_size > MAX_PROJECT:
                raise ValueError("Project JSON is too large")
            payload = json.loads(archive.read(info))
            for info in archive.infolist():
                if info.filename.startswith("audio/audio.") and info.filename.endswith(".npz"):
                    name = Path(info.filename).name
                    if len(name) == len("audio." + "0" * 64 + ".npz") and all(c in "0123456789abcdef" for c in name[6:-4]):
                        caches.append((name, archive.read(info)))
    else:
        if len(raw) > MAX_PROJECT:
            raise ValueError("Project JSON exceeds 16 MiB")
        payload = json.loads(raw)
    doc = _validate(payload)
    doc.update(id=uuid.uuid4().hex, created=time.time(), exports=[], imported_at=time.time(), history=doc.get("history", [])[-500:])
    doc.pop("job", None)
    doc.pop("recovery_required", None)
    doc.pop("export_destination", None)
    # Do not trust imported cache filenames blindly: cache.py validates NPZ
    # arrays and the internal cache key when they are used.
    for r in doc["videos"]:
        r["missing"] = True  # Validate/relink on this installation before use.
    for p in doc["pairs"]:
        p["stale"] = True
    review.event(doc, "project_opened")
    store.write(doc)
    cache = store.directory(doc["id"]) / "audio"
    cache.mkdir(exist_ok=True)
    for name, contents in caches:
        (cache / name).write_bytes(contents)
    return doc


def relink(doc, roots, progress, flag):
    from .metadata import probe_video
    old = copy.deepcopy(doc)
    results = []
    for i, r in enumerate(doc["videos"]):
        progress(100 * i / max(1, len(doc["videos"])), f"Relinking {i + 1}/{len(doc['videos'])} · {r['name']}")
        root = Path(roots[r["kind"]]).expanduser().resolve()
        relative = r.get("relative_path")
        if not relative:
            try:
                relative = str(Path(r["path"]).relative_to(Path(old["folders"][r["kind"]])))
            except ValueError:
                relative = r["name"]
        # JSON saved on Windows may have backslash relative paths.
        candidate = (root / relative.replace("\\", "/")).resolve()
        candidates = [candidate] if root in candidate.parents and candidate.is_file() else [p for p in root.rglob("*") if p.name.casefold() == r["name"].casefold()]
        candidates = [p for p in candidates if p.is_file() and p.stat().st_size == r["signature"][0]]
        if r.get("content_id"):
            candidates = [p for p in candidates if content_id(p) == r["content_id"]]
        if len(candidates) != 1:
            r.update(missing=True)
            results.append({"name": r["name"], "status": "missing" if not candidates else "ambiguous"})
            continue
        path = candidates[0]
        stat = path.stat()
        unchanged = r.get("content_id") is not None or [stat.st_size, stat.st_mtime_ns] == r["signature"]
        r.update(path=str(path), signature=[stat.st_size, stat.st_mtime_ns], missing=False,
                 content_id=content_id(path), relative_path=str(path.relative_to(root)), relinked_mtime=stat.st_mtime)
        r["metadata"] = probe_video(path)
        r.pop("error", None)
        for p in doc["pairs"]:
            if r["id"] in (p["fpv"], p["stick"]):
                if not unchanged:
                    p.update(confirmed=False, review_state="candidate", needs_recheck=True)
                p.setdefault("source_signatures", {})["fpv" if r["kind"] == "fpv" else "stick"] = r["signature"]
        results.append({"name": r["name"], "status": "verified" if unchanged else "recheck"})
    current = {r["id"]: r for r in doc["videos"]}
    for p in doc["pairs"]:
        p["stale"] = any(current[k].get("missing") for k in (p["fpv"], p["stick"]))
    doc.update(folders={k: str(Path(v).expanduser().resolve()) for k, v in roots.items()}, relink_report=results)
    review.event(doc, "sources_relinked")
    matching.suggest(doc)
    return doc
