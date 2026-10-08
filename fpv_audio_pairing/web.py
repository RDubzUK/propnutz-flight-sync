from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import threading
import time
import uuid
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import store, matching, preview, export_locations, review, projects, quality, diagnostics
from .cache import _key, get_or_extract
from .evidence import assess_audio_pair, audio_sections
from .exports import export_pair, stream_archive
from .fingerprint import ALGORITHM_VERSION, extract_audio, validate_audio
from .metadata import filename_timestamp, probe_video

app = FastAPI(title="PropNutz Flight Sync")
STATIC = Path(__file__).parent / "static"
WORKERS = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio-pairing")
PREVIEWS = threading.Semaphore(2)
THUMBNAIL_LOCK = threading.Lock()
FLAGS = {}
TASK_SAVE_ERRORS = {}
ACTIVE = threading.RLock()
EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".mts", ".m2ts", ".webm"}


@app.on_event("shutdown")
def stop_workers():
    # Let running subprocesses stop through their normal cancellation paths;
    # startup marks unfinished saved jobs interrupted so they can be resumed.
    with ACTIVE:
        for flag in FLAGS.values():
            flag.set()
    WORKERS.shutdown(wait=False, cancel_futures=True)


@app.exception_handler(store.SessionSaveError)
async def session_save_error(request: Request, exc: store.SessionSaveError):
    return JSONResponse({"detail": str(exc)}, status_code=503)


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items() if not str(k).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def task_save_status(doc):
    # A stopped worker must not appear to run forever if the disk also refused
    # its failure-status save. This overlay is explicitly marked as unsaved.
    with ACTIVE:
        failed = TASK_SAVE_ERRORS.get(doc["id"])
    if failed:
        doc["job"] = {**doc.get("job", {}), **failed}
    return doc


def session(sid):
    try:
        return review.enrich(task_save_status(matching.refresh_clock_evidence(matching.refresh_pair_ranges(store.read(sid)))))
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Session not found") from None


def video(sid, vid):
    s = session(sid)
    r = next((r for r in s["videos"] if r["id"] == vid), None)
    if r is None:
        raise HTTPException(404, "Recording not found")
    if r.get("missing"):
        raise HTTPException(409, "Relink the source folders before using this recording")
    try:
        stat = Path(r["path"]).stat()
        if [stat.st_size, stat.st_mtime_ns] != r["signature"]:
            raise HTTPException(409, "Source changed. Rescan this session before continuing.")
    except OSError:
        raise HTTPException(409, "Source recording unavailable. Reconnect its folder or network share.") from None
    return r


def idle(sid):
    with ACTIVE:
        doc = session(sid)
        if sid in FLAGS or (not doc.get("recovery_required") and doc.get("job", {}).get("status") in {"queued", "running"}):
            raise HTTPException(409, "A task is already running for this session")


def task(sid, title, work, *, target_fpv=None, descriptor=None):
    with ACTIVE:
        idle(sid)
        flag = threading.Event()
        start = time.time()
        job = {"status": "queued", "title": title, "message": "Waiting for the processing queue", "percent": 0,
               "started": start, "elapsed": 0, "eta": None}
        if descriptor:
            job["resume"] = descriptor
        if target_fpv is not None:
            job["target_fpv"] = target_fpv
        store.update(sid, lambda s: s.update(job=job))
        FLAGS[sid] = flag
        TASK_SAVE_ERRORS.pop(sid, None)

    def update(percent, message):
        if flag.is_set():
            raise RuntimeError("Cancelled")
        elapsed = time.time() - start
        def save_progress(s):
            current = max(float(s["job"].get("percent", 0)), percent)
            s["job"].update(status="running", percent=round(current, 1), message=message,
                            elapsed=round(elapsed, 1), eta=round(elapsed * (100 - current) / current) if current > 1 else None)
        store.update(sid, save_progress)

    def run():
        nonlocal start
        start = time.time()  # Queue waiting time is not processing time.
        try:
            update(0, title)
            work(update, flag)
            update(100, "Complete")
            store.update(sid, lambda s: s["job"].update(status="complete", eta=0))
        except Exception as exc:
            try:
                store.update(sid, lambda s: s["job"].update(status="cancelled" if flag.is_set() else "failed",
                              message=str(exc), eta=None, elapsed=round(time.time() - start, 1)))
            except FileNotFoundError:
                pass
            except store.SessionSaveError:
                with ACTIVE:
                    TASK_SAVE_ERRORS[sid] = {
                        "status": "failed", "eta": None, "elapsed": round(time.time() - start, 1),
                        "message": f"Task stopped; its failure status could not be saved. {exc}",
                        "persistence_failed": True,
                    }
        finally:
            with ACTIVE:
                FLAGS.pop(sid, None)
    WORKERS.submit(run)
    return job


def execute(flag, command, logfile, timeout=4 * 3600, on_progress=None):
    logfile = Path(logfile)
    logfile.parent.mkdir(parents=True, exist_ok=True)
    meter = logfile.with_suffix(".progress")
    if on_progress and Path(command[0]).stem == "ffmpeg":
        meter.unlink(missing_ok=True)
        command = command[:1] + ["-progress", str(meter), "-nostats"] + command[1:]
    with logfile.open("wb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        start = time.monotonic()
        last_percent = -1
        try:
            while process.poll() is None:
                if flag.is_set():
                    raise RuntimeError("Cancelled")
                if time.monotonic() - start > timeout:
                    raise RuntimeError("Encoding timed out")
                if on_progress and meter.exists():
                    try:
                        values = [int(line.split("=", 1)[1]) for line in meter.read_text().splitlines() if line.startswith("out_time_us=")]
                        duration = float(command[command.index("-t") + 1])
                        percent = min(100, max(0, int(100 * values[-1] / 1e6 / duration))) if values else 0
                        if percent > last_percent:
                            on_progress(percent / 100)
                            last_percent = percent
                    except (ValueError, OSError, IndexError):
                        pass
                flag.wait(.25)
            if process.returncode:
                raise RuntimeError(logfile.read_text(errors="replace")[-1200:] or "FFmpeg failed")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            meter.unlink(missing_ok=True)


def cache_path(sid, r, boundary):
    return store.directory(sid) / "audio" / f"audio.{_key(r['path'], ALGORITHM_VERSION, {'boundary_seconds': float(boundary)}, r.get('content_id'))}.npz"


def audio(sid, r, boundary, flag=None):
    r = video(sid, r["id"])
    requested = boundary
    previous = r.get("audio_boundary")
    if previous and r["metadata"]["duration"] <= 2 * min(previous, boundary):
        # Both configurations cover the complete recording. A retry cannot
        # reveal new samples; reuse the compatible full-recording fingerprint.
        boundary = previous
    started = time.monotonic()
    cached = cache_path(sid, r, boundary).exists()
    config = {"boundary_seconds": float(boundary)}
    legacy = [_key(r["path"], ALGORITHM_VERSION, config)]
    # Historic integer config keys remain readable after this upgrade.
    if float(boundary).is_integer():
        legacy.append(_key(r["path"], ALGORITHM_VERSION, {"boundary_seconds": int(boundary)}))
    if r.get("audio_cache_keys", {}).get(str(float(boundary))):
        legacy.append(r["audio_cache_keys"][str(float(boundary))])
    data = get_or_extract(r["path"], store.directory(sid) / "audio", "audio", ALGORITHM_VERSION,
                          config, lambda: extract_audio(r["path"], boundary, cancelled=flag), validate=validate_audio,
                          identity=r.get("content_id"), legacy_keys=legacy)
    status = "ready" if len(data["time"]) and float(data["quality"]) > .1 else "unusable"
    def save(s):
        record = next(v for v in s["videos"] if v["id"] == r["id"])
        record.update(audio_status=status, audio_boundary=boundary, audio_quality=float(data["quality"]),
                      audio_seconds=round(time.monotonic() - started, 2), audio_reused=cached, audio_requested_boundary=requested)
    store.update(sid, save)
    return data


def scan(sid, progress, flag):
    s = session(sid)
    old = {r["path"]: r for r in s["videos"]}
    export_folders = {Path(e["directory"]) for e in export_locations.records(include_pending=True)}
    found = []
    for kind, root in s["folders"].items():
        folder = Path(root)
        if not folder.is_dir():
            raise ValueError(f"The {kind} folder is unavailable: {folder}")
        files = folder.rglob("*") if s.get("recursive") else folder.iterdir()
        for path in files:
            if flag.is_set():
                raise RuntimeError("Cancelled")
            if path.is_file() and path.suffix.lower() in EXTENSIONS:
                resolved_path = path.resolve()
                if any(parent in export_folders for parent in resolved_path.parents):
                    continue
                resolved = str(resolved_path)
                stat = path.stat()
                record = {"id": hashlib.sha256(f"{kind}:{resolved}".encode()).hexdigest()[:32], "kind": kind,
                          "name": path.name, "path": resolved, "mtime": stat.st_mtime,
                          "signature": [stat.st_size, stat.st_mtime_ns], "filename_time": filename_timestamp(path.name)}
                previous = old.get(resolved)
                if previous and previous["signature"] == record["signature"] and previous["kind"] == kind:
                    record.update({k: v for k, v in previous.items() if k not in record and k != "stale"})
                    record["id"] = previous["id"]  # Relinked recordings retain pair identities.
                    if "relinked_mtime" in previous:
                        record["mtime"] = previous["mtime"]
                        record["relinked_mtime"] = stat.st_mtime
                record["relative_path"] = str(resolved_path.relative_to(folder.resolve()))
                record["content_id"] = record.get("content_id") or projects.content_id(path)
                record["missing"] = False
                found.append(record)
    found.sort(key=lambda r: (r["kind"], r["name"].casefold()))
    def save_scan(doc):
        doc["videos"] = found
        current = {r["id"]: r for r in found}
        for p in doc["pairs"]:
            p["stale"] = any(i not in current or current[i]["signature"] != old.get(current[i]["path"], {}).get("signature")
                             for i in (p["fpv"], p["stick"]))
    store.update(sid, save_scan)
    for index, r in enumerate(found):
        progress(100 * index / max(1, len(found)), f"Reading recording {index + 1}/{len(found)} · {r['name']}")
        try:
            if not r.get("metadata"):
                r["metadata"] = probe_video(r["path"])
            r.pop("error", None)
            r["audio_status"] = r.get("audio_status", "not_prepared") if r["metadata"]["has_audio"] else "no_audio"
        except Exception as exc:
            r["error"] = str(exc)
        store.update(sid, lambda doc, r=r: next(v for v in doc["videos"] if v["id"] == r["id"]).update(r))
    store.update(sid, matching.suggest)


class Sources(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    fpv: str
    stick: str
    recursive: bool = False


class MatchOptions(BaseModel):
    selected: list[str] = Field(default_factory=list)
    fraction: float = Field(default=1, gt=0, le=1)
    boundary: float = Field(default=30, ge=10, le=300)
    min_overlap: float = Field(default=2, ge=2, le=60)
    use_filenames: bool = True
    modified_kind: str = "end"
    adaptive: bool = True
    retry_limit: float = Field(default=120, ge=30, le=300)


def find(sid, options, progress, flag, *, counterpart_fpv=None):
    from .search import run_match
    return run_match(sid, options, progress, flag, lambda r, boundary: audio(sid, r, boundary, flag), clean, counterpart_fpv)


@app.get("/api/system")
def system():
    return {"name": "PropNutz Flight Sync", "version": version("fpv-audio-pairing"), "ffmpeg": bool(shutil.which("ffmpeg")),
            "ffprobe": bool(shutil.which("ffprobe")), "data": str(store.ROOT)}


@app.get("/api/browse")
def browse(path: str = "", hidden: bool = False):
    root = Path(path).expanduser() if path else Path.home()
    try:
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Choose a directory")
        entries = [{"name": p.name, "path": str(p), "folder": p.is_dir()} for p in root.iterdir()
                   if (hidden or not p.name.startswith(".")) and (p.is_dir() or p.suffix.lower() in EXTENSIONS)]
        entries.sort(key=lambda p: (not p["folder"], p["name"].casefold()))
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"Cannot browse folder: {exc}") from None
    shortcuts = [str(Path.home()), "/mnt", "/media", f"/run/user/{os.getuid()}/gvfs"] if os.name != "nt" else [f"{d}:\\" for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{d}:\\").exists()]
    return {"path": str(root), "parent": str(root.parent), "entries": entries,
            "shortcuts": [p for p in shortcuts if Path(p).is_dir()]}


@app.get("/api/sessions")
def list_sessions():
    result = []
    for s in map(task_save_status, store.sessions()):
        candidates = thumbnail_candidates(s)
        result.append({k: s.get(k) for k in ("id", "name", "created", "folders", "job")} | {
            "videos": len(s["videos"]), "confirmed": sum(p.get("confirmed", False) for p in s["pairs"]),
            "thumbnail_url": f"/api/sessions/{s['id']}/thumbnail?v={thumbnail_key(candidates[0])}" if candidates else None,
        })
    return result


def thumbnail_candidates(doc):
    dated = [r for r in doc["videos"] if isinstance(r.get("mtime"), (int, float)) and math.isfinite(r["mtime"])]
    mean = sum(r["mtime"] for r in dated) / len(dated) if dated else 0
    return sorted((r for r in doc["videos"] if r["kind"] == "fpv" and r.get("metadata") and not r.get("error")),
                  key=lambda r: (abs((r.get("mtime") or mean) - mean), r["name"]))


def thumbnail_key(record):
    return hashlib.sha256(json.dumps(["session-still-v1", record["id"], record["signature"],
                                     record["metadata"]["duration"]]).encode()).hexdigest()


@app.get("/api/sessions/{sid}/thumbnail")
def session_thumbnail(sid: str):
    try:
        doc = store.read(sid)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "Session not found") from None
    candidates = thumbnail_candidates(doc)
    if not candidates:
        raise HTTPException(404, "No scanned FPV recording available for a session preview")
    # Decode just one still, lazily. Cached images remain useful when a source
    # drive is disconnected, and repeat polling never decodes the video again.
    with THUMBNAIL_LOCK:
        for r in candidates[:3]:
            destination = store.directory(sid) / "thumbnails" / f"{thumbnail_key(r)}.jpg"
            try:
                if not destination.is_file():
                    path = Path(r["path"])
                    stat = path.stat()
                    if [stat.st_size, stat.st_mtime_ns] != r["signature"]:
                        continue
                    executable = shutil.which("ffmpeg")
                    if not executable:
                        raise HTTPException(503, "FFmpeg is required for session previews")
                    duration = r["metadata"]["duration"]
                    at = 90 if duration > 90.1 else 60 if duration > 60.1 else duration / 2
                    frame = subprocess.run([
                        executable, "-hide_banner", "-loglevel", "error", "-nostdin", "-threads", "1",
                        "-ss", str(at), "-i", str(path), "-map", "0:v:0", "-an", "-sn", "-dn",
                        "-frames:v", "1", "-vf", "scale=400:225:force_original_aspect_ratio=increase,crop=400:225",
                        "-threads", "1", "-q:v", "4", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
                    ], capture_output=True, timeout=30)
                    if frame.returncode or not frame.stdout.startswith(b"\xff\xd8"):
                        continue
                    current = path.stat()
                    if [current.st_size, current.st_mtime_ns] != r["signature"]:
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    temporary = destination.with_suffix(".tmp")
                    temporary.write_bytes(frame.stdout)
                    os.replace(temporary, destination)
                return FileResponse(destination, media_type="image/jpeg", headers={
                    "Cache-Control": "private, max-age=300", "X-Thumbnail-Source": quote(r["name"]),
                })
            except (OSError, subprocess.SubprocessError):
                continue
    raise HTTPException(422, "Could not decode a session preview; reconnect or rescan the source folder")


@app.post("/api/sessions")
def create(options: Sources):
    roots = {kind: str(Path(path).expanduser().resolve()) for kind, path in (("fpv", options.fpv), ("stick", options.stick))}
    if not all(Path(p).is_dir() for p in roots.values()):
        raise HTTPException(400, "Both source folders must exist on the machine running this app")
    if roots["fpv"] == roots["stick"]:
        raise HTTPException(400, "Choose separate FPV and StickCam folders")
    if options.recursive and any(Path(a) in Path(b).parents for a, b in ((roots["fpv"], roots["stick"]), (roots["stick"], roots["fpv"]))):
        raise HTTPException(400, "When including subfolders, choose folders that do not contain each other")
    sid = uuid.uuid4().hex
    doc = {"id": sid, "name": options.name.strip() or "Untitled session", "created": time.time(), "folders": roots,
           "recursive": options.recursive, "videos": [], "pairs": [], "exports": [], "clocks": [], "clock_warnings": []}
    store.write(doc)
    task(sid, "Scanning source folders", lambda update, flag: scan(sid, update, flag), descriptor={"kind": "scan"})
    return session(sid)


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    # Old confirmations acquire current date evidence on load. This is a cheap
    # derived annotation, not a new match search or a write to the session file.
    return matching.refresh_clock_evidence(session(sid))


class Rename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@app.patch("/api/sessions/{sid}")
def rename(sid: str, options: Rename):
    session(sid)
    return store.update(sid, lambda s: s.update(name=options.name.strip() or "Untitled session"))


class ClockOptions(BaseModel):
    use_filenames: bool = True
    modified_kind: str = "end"
    modified_tolerance: float = Field(default=5, ge=1, le=10)


@app.patch("/api/sessions/{sid}/clocks")
def clock_settings(sid: str, options: ClockOptions):
    idle(sid)
    if options.modified_kind not in {"start", "end"}:
        raise HTTPException(400, "Modified dates must represent recording start or end")
    def change(s):
        s.update(use_filenames=options.use_filenames, modified_kind=options.modified_kind, modified_tolerance=options.modified_tolerance)
        matching.suggest(s)
    store.update(sid, change)
    return session(sid)


@app.delete("/api/sessions/{sid}")
def delete(sid: str):
    with ACTIVE, store.LOCK:
        idle(sid)
        shutil.rmtree(store.directory(sid))
        TASK_SAVE_ERRORS.pop(sid, None)
    return {"deleted": True, "exports_preserved": True}


@app.post("/api/sessions/{sid}/cancel")
def cancel(sid: str):
    session(sid)
    with ACTIVE:
        if sid in FLAGS:
            FLAGS[sid].set()
    return {"message": "Cancellation requested. Saved fingerprints, comparisons and completed export pairs are kept for resume."}


@app.post("/api/sessions/{sid}/scan")
def rescan(sid: str):
    return task(sid, "Scanning source folders", lambda update, flag: scan(sid, update, flag), descriptor={"kind": "scan"})


@app.post("/api/sessions/{sid}/match")
def match(sid: str, options: MatchOptions):
    if options.modified_kind not in {"start", "end"}:
        raise HTTPException(400, "Modified dates must represent recording start or end")
    return task(sid, "Finding matching flights", lambda update, flag: find(sid, options, update, flag),
                descriptor={"kind": "match", "options": options.model_dump()})


class CounterpartOptions(BaseModel):
    fpv: str
    boundary: float = Field(default=30, ge=10, le=300)
    adaptive: bool = True
    retry_limit: float = Field(default=120, ge=30, le=300)


@app.post("/api/sessions/{sid}/counterpart")
def counterpart(sid: str, options: CounterpartOptions):
    idle(sid)
    source = video(sid, options.fpv)
    if source["kind"] != "fpv":
        raise HTTPException(400, "Choose an FPV recording to find its StickCam counterpart")
    if not source.get("metadata") or source.get("error"):
        raise HTTPException(400, "Rescan this recording before searching for its counterpart")
    if not source["metadata"].get("has_audio"):
        raise HTTPException(400, "This FPV recording has no audio track. Review any saved timestamp suggestions or align a pair manually.")
    current = session(sid)
    if not any(r["kind"] == "stick" and r.get("metadata", {}).get("has_audio") and not r.get("error")
               for r in current["videos"]):
        raise HTTPException(400, "This session has no StickCam recordings with readable audio. Check the folders and rescan.")
    match_options = MatchOptions(selected=[source["id"]], fraction=1, boundary=options.boundary,
                                 adaptive=options.adaptive, retry_limit=options.retry_limit,
                                 use_filenames=current.get("use_filenames", True),
                                 modified_kind=current.get("modified_kind", "end"),
                                 min_overlap=current.get("min_overlap", 2))
    return task(sid, "Finding StickCam counterpart",
                lambda update, flag: find(sid, match_options, update, flag, counterpart_fpv=source["id"]),
                target_fpv=source["id"], descriptor={"kind": "match", "options": match_options.model_dump(), "counterpart": source["id"]})


class PairOptions(BaseModel):
    fpv: str
    stick: str
    offset: float = Field(allow_inf_nan=False)
    confirmed: bool = False
    independent_check: bool = False


@app.post("/api/sessions/{sid}/pairs")
def save_pair(sid: str, options: PairOptions):
    idle(sid)
    f, r = video(sid, options.fpv), video(sid, options.stick)
    if f["kind"] != "fpv" or r["kind"] != "stick" or not f.get("metadata") or not r.get("metadata"):
        raise HTTPException(400, "Choose one readable recording of each type")
    p = matching.make_pair(f, r, options.offset)
    if p["overlap_duration"] < .1:
        raise HTTPException(400, "The recordings do not overlap at that offset")
    store.checkpoint(sid, force=True)
    def save(s):
        conflicts = review.overlap_conflicts(s, p) if options.confirmed else []
        if conflicts:
            raise HTTPException(409, f"This FPV part overlaps confirmed '{conflicts[0]['name']}' by {conflicts[0]['seconds']:.2f}s in StickCam. Correct the alignment or unconfirm the conflicting pair before confirming this split part.")
        existing = next((q for q in s["pairs"] if q["id"] == p["id"]), None)
        if existing:
            changed = abs(existing["offset"] - options.offset) > .00001
            existing.update(p, confirmed=options.confirmed, stale=False)
            if changed and existing.get("evidence"):
                existing["evidence"] = None
                existing["confidence"] = "Manually adjusted"
                existing["method"] = "manual"
            if changed:
                existing.pop("verification", None)
                existing["method"] = "manual"
        else:
            existing = p | {"method": "manual", "confidence": "Manual alignment", "score": None, "evidence": None,
                            "confirmed": options.confirmed}
            s["pairs"].append(existing)
        existing["source_signatures"] = {"fpv": f["signature"], "stick": r["signature"]}
        if options.confirmed:
            existing["confirmed_at"] = time.time()
            existing["modified_difference"] = r["mtime"] - f["mtime"]
            existing["verification"] = "independent" if options.independent_check or existing.get("method") != "timestamp" else "date_only"
            existing["review_state"] = "confirmed"
            s.setdefault("decisions", {}).pop(existing["id"], None)
            next(v for v in s["videos"] if v["id"] == options.fpv)["no_counterpart"] = False
        else:
            existing["review_state"] = "candidate"
            s.setdefault("decisions", {}).pop(existing["id"], None)
        review.event(s, "pair_confirmed" if options.confirmed else "alignment_saved", pair=existing["id"], offset=options.offset)
        matching.suggest(s)
    store.update(sid, save)
    return session(sid)


class DecisionOptions(BaseModel):
    state: Literal["candidate", "later", "rejected"]


@app.patch("/api/sessions/{sid}/pairs/{pid}/review")
def decide_pair(sid: str, pid: str, options: DecisionOptions):
    idle(sid)
    store.checkpoint(sid, force=True)
    def change(s):
        p = next((p for p in s["pairs"] if p["id"] == pid), None)
        if p is None:
            raise HTTPException(404, "Pair not found")
        p.update(confirmed=False, review_state=options.state)
        s.setdefault("decisions", {})[pid] = options.state
        review.event(s, "review_decision", pair=pid, state=options.state)
        matching.suggest(s)
    store.update(sid, change)
    return session(sid)


class NoCounterpart(BaseModel):
    value: bool = True


@app.patch("/api/sessions/{sid}/videos/{vid}/counterpart")
def no_counterpart(sid: str, vid: str, options: NoCounterpart):
    idle(sid)
    def change(s):
        r = next((r for r in s["videos"] if r["id"] == vid and r["kind"] == "fpv"), None)
        if r is None:
            raise HTTPException(404, "FPV recording not found")
        if options.value and any(p["fpv"] == vid and p.get("confirmed") for p in s["pairs"]):
            raise HTTPException(400, "Unconfirm this recording's pairs before marking it unmatched")
        r["no_counterpart"] = options.value
        for p in s["pairs"]:
            if options.value and p["fpv"] == vid:
                p.update(review_state="rejected", confirmed=False)
                s.setdefault("decisions", {})[p["id"]] = "rejected"
        review.event(s, "no_counterpart", video=vid, value=options.value)
        matching.suggest(s)
    store.update(sid, change)
    return session(sid)


class SyncPoint(BaseModel):
    fpv_time: float = Field(ge=0, allow_inf_nan=False)
    stick_time: float = Field(ge=0, allow_inf_nan=False)
    note: str = Field(default="", max_length=200)


@app.post("/api/sessions/{sid}/pairs/{pid}/checkpoints")
def sync_point(sid: str, pid: str, options: SyncPoint):
    idle(sid)
    def change(s):
        p = next((p for p in s["pairs"] if p["id"] == pid), None)
        if p is None:
            raise HTTPException(404, "Pair not found")
        by_id = {r["id"]: r for r in s["videos"]}
        if options.fpv_time >= by_id[p["fpv"]]["metadata"]["duration"] or options.stick_time >= by_id[p["stick"]]["metadata"]["duration"]:
            raise HTTPException(400, "Event times must be inside the source recordings")
        points = p.setdefault("sync_points", [])
        if len(points) >= 20:
            raise HTTPException(400, "Keep up to 20 checkpoints; remove an old point first")
        points.append(options.model_dump() | {"id": uuid.uuid4().hex})
        review.event(s, "sync_checkpoint", pair=pid)
    store.update(sid, change)
    return session(sid)


@app.delete("/api/sessions/{sid}/pairs/{pid}/checkpoints/{point}")
def remove_sync_point(sid: str, pid: str, point: str):
    idle(sid)
    def change(s):
        p = next((p for p in s["pairs"] if p["id"] == pid), None)
        if p is None:
            raise HTTPException(404, "Pair not found")
        p["sync_points"] = [item for item in p.get("sync_points", []) if item["id"] != point]
    store.update(sid, change)
    return session(sid)


class ReferenceOptions(BaseModel):
    match: bool
    expected_offset: float | None = Field(default=None, allow_inf_nan=False)
    tolerance: float = Field(default=.15, ge=.01, le=2)
    note: str = Field(default="", max_length=500)
    known_identity: bool = False


@app.post("/api/sessions/{sid}/pairs/{pid}/reference")
def reference(sid: str, pid: str, options: ReferenceOptions):
    idle(sid)
    def change(s):
        p = next((p for p in s["pairs"] if p["id"] == pid), None)
        if p is None or p.get("stale"):
            raise HTTPException(400, "Open a pair with available sources")
        if options.match and not review.independently_verified(p) and not options.known_identity:
            raise HTTPException(400, "Independently identify the flight before adding a matching reference")
        if not options.match and p.get("confirmed"):
            raise HTTPException(400, "Unconfirm or reject this pair before labelling it a non-match")
        sources = {r["id"]: r for r in s["videos"]}
        item = {"id": pid, "fpv": p["fpv"], "stick": p["stick"], **options.model_dump(),
                "content_ids": {k: sources[p[k]].get("content_id") for k in ("fpv", "stick")}, "created": time.time()}
        s["references"] = [r for r in s.get("references", []) if r["id"] != pid] + [item]
        review.event(s, "reference_label", pair=pid, match=options.match)
    store.update(sid, change)
    return session(sid)


@app.delete("/api/sessions/{sid}/references/{pid}")
def remove_reference(sid: str, pid: str):
    idle(sid)
    store.update(sid, lambda s: s.update(references=[r for r in s.get("references", []) if r["id"] != pid]))
    return session(sid)


class BenchmarkOptions(BaseModel):
    boundary: float = Field(default=120, ge=10, le=300)


@app.post("/api/sessions/{sid}/validate")
def validate_references(sid: str, options: BenchmarkOptions):
    if not session(sid).get("references"):
        raise HTTPException(400, "Add at least one known answer to the reference collection first")
    def run(progress, flag):
        result = quality.benchmark(session(sid), lambda r, b: audio(sid, r, b, flag), options.boundary, progress, flag)
        store.update(sid, lambda s: s.update(benchmark=clean(result)))
    return task(sid, "Validating reference pairs", run, descriptor={"kind": "validate", "options": options.model_dump()})


@app.get("/api/sessions/{sid}/project")
def save_project(sid: str, bundle: bool = False):
    idle(sid)
    s = session(sid)
    try:
        data = projects.bundle(s) if bundle else json.dumps(projects.document(s), indent=2, allow_nan=False).encode()
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"Cannot save project: {exc}") from None
    name = quote(export_locations.folder_name(s["name"]) + (".flightsync.zip" if bundle else ".flightsync.json"), safe="")
    return StreamingResponse(io.BytesIO(data), media_type="application/zip" if bundle else "application/json",
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"})


@app.post("/api/projects/open")
async def open_project(request: Request):
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > projects.MAX_BUNDLE:
            raise HTTPException(413, "Project exceeds 128 MiB")
        chunks.append(chunk)
    try:
        result = projects.open_project(b"".join(chunks))
    except (OSError, ValueError, KeyError, TypeError, OverflowError, zipfile.BadZipFile) as exc:
        raise HTTPException(400, f"Cannot open project: {exc}") from None
    return review.enrich(result)


class RelinkOptions(BaseModel):
    fpv: str = Field(max_length=4096)
    stick: str = Field(max_length=4096)


@app.post("/api/sessions/{sid}/relink")
def relink_sources(sid: str, options: RelinkOptions):
    idle(sid)
    roots = {"fpv": options.fpv, "stick": options.stick}
    if not all(Path(p).expanduser().is_dir() for p in roots.values()):
        raise HTTPException(400, "Both relink folders must exist on this machine")
    if Path(options.fpv).resolve() == Path(options.stick).resolve():
        raise HTTPException(400, "Choose separate source folders")
    store.checkpoint(sid, force=True)
    def run(progress, flag):
        doc = projects.relink(session(sid), roots, progress, flag)
        # Keep the current job descriptor/progress written by task().
        job = store.read(sid)["job"]
        doc["job"] = job
        store.write(doc)
    return task(sid, "Relinking source folders", run, descriptor={"kind": "relink", "options": options.model_dump()})


@app.get("/api/sessions/{sid}/backups")
def session_backups(sid: str):
    session(sid)
    return store.backups(sid)


class RestoreOptions(BaseModel):
    name: str


@app.post("/api/sessions/{sid}/restore")
def restore_backup(sid: str, options: RestoreOptions):
    idle(sid)
    try:
        return review.enrich(store.restore(sid, options.name))
    except (OSError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from None


@app.get("/api/diagnostics")
def system_diagnostics(sid: str = "", include_paths: bool = False):
    return diagnostics.report(session(sid) if sid else None, include_paths)


@app.get("/api/sessions/{sid}/videos/{vid}/original")
def original(sid: str, vid: str):
    r = video(sid, vid)
    return MediaFileResponse(r["path"], media_type="video/mp4" if Path(r["path"]).suffix.lower() in {".mp4", ".m4v"} else None)


class MediaFileResponse(FileResponse):
    # Retain HTTP range support with fewer disk/thread hops for large originals.
    chunk_size = 1024 ** 2


@app.get("/api/sessions/{sid}/videos/{vid}/preview")
def preview_info(sid: str, vid: str, acceleration: Literal["auto", "cpu"] = "auto"):
    r = video(sid, vid)
    if not r.get("metadata"):
        raise HTTPException(409, "Wait for source scanning to finish")
    return preview.manifest(r["path"], r["metadata"], acceleration)


@app.get("/api/sessions/{sid}/videos/{vid}/preview/{index}")
def preview_chunk(sid: str, vid: str, index: int, source: str, acceleration: Literal["auto", "cpu"] = "auto"):
    r = video(sid, vid)
    if preview.source_key(r["path"], acceleration) != source:
        raise HTTPException(409, "Source changed; reload the preview")
    with PREVIEWS:
        try:
            path, details = preview.fragment(r["path"], r["metadata"], index, store.directory(sid) / "previews",
                lambda key, cmd, log, timeout: execute(threading.Event(), cmd, log, timeout), vid, threading.Event(), acceleration)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from None
    return FileResponse(path, media_type="video/mp4", headers={"X-Preview-Start": str(details["start"]),
        "X-Preview-Duration": str(details["duration"]), "X-Preview-Video-Start": str(details["video_start"]),
        "X-Preview-Decoder": details.get("decoder", "cpu")})


@app.get("/api/sessions/{sid}/videos/{vid}/audio")
def audio_trace(sid: str, vid: str):
    r = video(sid, vid)
    target = cache_path(sid, r, r.get("audio_boundary", 30))
    if not target.exists():
        return {"time": [], "energy": [], "segments": []}
    with np.load(target, allow_pickle=False) as data:
        validate_audio(data)
        return {"time": data["time"].tolist(), "energy": data["features"][:, 0].tolist(), "segments": data["segments"].tolist()}


class ExportOptions(BaseModel):
    pairs: list[str] = Field(min_length=1)
    fps: int | None = None
    profile: str = "copy"
    trim_start: float = Field(default=0, ge=0, allow_inf_nan=False)
    trim_end: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    destination: str = Field(default="", max_length=4096)
    verify_frames: bool = False
    acknowledge_sync_warning: bool = False


@app.post("/api/sessions/{sid}/export")
def export(sid: str, options: ExportOptions):
    return start_export(sid, options)


def start_export(sid, options, resume=None):
    idle(sid)
    s = session(sid)
    selected = [p for p in s["pairs"] if p["id"] in set(options.pairs)]
    names = {r["id"]: r["name"] for r in s["videos"]}
    selected.sort(key=lambda p: (names.get(p["stick"], "").casefold(), p["radio_start"], names.get(p["fpv"], "").casefold()))
    if len(selected) != len(set(options.pairs)) or any(not p.get("confirmed") or p.get("stale") for p in selected):
        raise HTTPException(400, "Export requires confirmed pairs with unchanged source recordings")
    if any(review.overlap_conflicts(s, p, selected) for p in selected):
        raise HTTPException(409, "Confirmed FPV parts overlap on the same StickCam timeline. Review their alignments before exporting the flight together.")
    if options.fps not in {None, 24, 25, 30, 50, 60} or options.profile not in {"copy", "h264", "dnxhr"}:
        raise HTTPException(400, "Choose a supported frame rate and export format")
    if options.profile == "copy" and options.fps is not None:
        raise HTTPException(400, "Fast trim uses original frame rates. Select Accurate trim to convert frame rates.")
    for p in selected:
        sources = [video(sid, p[k]) for k in ("fpv", "stick")]
        rates = [options.fps] if options.fps is not None else [r["metadata"]["fps"] for r in sources]
        if any(not math.isfinite(rate) or rate <= 0 for rate in rates):
            raise HTTPException(400, "Rescan the source videos to determine their original frame rates")
        end = options.trim_end if options.trim_end is not None else p["overlap_duration"]
        if end > p["overlap_duration"] or end - options.trim_start < max(1 / rate for rate in rates):
            raise HTTPException(400, "Trim must fit inside every selected pair's overlap")
    try:
        root = export_locations.destination(options.destination.strip())
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"Cannot use export destination: {exc}") from None
    from .export_jobs import alignment_key, run_export
    key = alignment_key(selected)
    if resume and key != resume.get("alignment_key"):
        raise HTTPException(409, "Sources or alignments changed since this export. Start a new export instead.")
    warned = [p for p in selected if review.sync_check(p)["status"] in {"drift", "offset_mismatch"}]
    if warned and not options.acknowledge_sync_warning:
        raise HTTPException(409, "Sync checkpoints disagree with a constant offset. Review/trim the range, or explicitly acknowledge the warning before exporting.")
    spec = resume or {"kind": "export", "options": options.model_dump(), "eid": uuid.uuid4().hex, "alignment_key": key}
    return task(sid, "Exporting aligned clips",
                lambda progress, flag: run_export(sid, options, selected, spec, progress, flag, video, execute), descriptor=spec)


@app.post("/api/sessions/{sid}/resume")
def resume_task(sid: str):
    idle(sid)
    doc = session(sid)
    if doc.get("job", {}).get("status") not in {"interrupted", "failed", "cancelled"}:
        raise HTTPException(400, "Only interrupted, failed or cancelled tasks can be resumed")
    spec = doc.get("job", {}).get("resume", {})
    kind = spec.get("kind")
    if kind == "scan":
        return rescan(sid)
    if kind == "match":
        options = MatchOptions(**spec["options"])
        return task(sid, "Finding StickCam counterpart" if spec.get("counterpart") else "Finding matching flights",
                    lambda progress, flag: find(sid, options, progress, flag, counterpart_fpv=spec.get("counterpart")),
                    target_fpv=spec.get("counterpart"), descriptor=spec)
    if kind == "validate":
        return validate_references(sid, BenchmarkOptions(**spec["options"]))
    if kind == "relink":
        return relink_sources(sid, RelinkOptions(**spec["options"]))
    if kind == "export":
        return start_export(sid, ExportOptions(**spec["options"]), resume=spec)
    raise HTTPException(400, "This older task has no resume details. Start it again; saved audio is still reused.")


@app.get("/api/exports")
def exports():
    return export_locations.records()


@app.get("/api/exports/{sid}/{eid}/download")
def download(sid: str, eid: str):
    try:
        result, directory = export_locations.load(sid, eid)
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(404, "Export folder is unavailable or no longer contains this export. Reconnect its drive/share.") from None
    archive_name = quote(directory.name + ".zip", safe="")
    disposition = f"attachment; filename=\"aligned_pairs_{eid[:8]}.zip\"; filename*=UTF-8''{archive_name}"
    return StreamingResponse(stream_archive(directory, result.get("pair_directories")), media_type="application/zip",
                             headers={"Content-Disposition": disposition})


@app.middleware("http")
async def local_app(request: Request, call_next):
    # Prevent unrelated sites from controlling a trusted-LAN file browser.
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != f"{request.url.scheme}://{request.headers.get('host')}":
        return JSONResponse({"detail": "Use the app from its own address"}, 403)
    response = await call_next(request)
    if request.url.path.startswith("/api/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path.startswith("/static/"):
        # Windows registry file associations can override Python's MIME map.
        # Modules must be served as JavaScript, including imported modules and
        # cache-validation responses, regardless of the host's file associations.
        media_type = {".js": "text/javascript; charset=utf-8",
                      ".mjs": "text/javascript; charset=utf-8",
                      ".css": "text/css; charset=utf-8"}.get(Path(request.url.path).suffix.lower())
        if media_type and response.status_code in {200, 206, 304}:
            response.headers["Content-Type"] = media_type
            response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", media_type="text/html", headers={"Cache-Control": "no-store"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")


def main():
    parser = argparse.ArgumentParser(description="PropNutz Flight Sync · standalone audio pairing")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8768, type=int)
    parser.add_argument("--open", action="store_true", help="Open the local interface in your browser")
    parser.add_argument("--check", action="store_true", help="Print local diagnostics and exit")
    parser.add_argument("--data-dir", help="Use a dedicated writable data folder")
    args = parser.parse_args()
    if args.data_dir:
        store.ROOT = Path(args.data_dir).expanduser().resolve()
    if args.check:
        print(json.dumps(diagnostics.report(), indent=2))
        return
    try:
        store.acquire_instance()
    except RuntimeError as exc:
        parser.error(str(exc))
    for s in store.sessions():
        if s.get("job", {}).get("status") in {"queued", "running"}:
            if not s.get("recovery_required"):
                store.update(s["id"], lambda d: d["job"].update(status="interrupted", message="App restarted. Resume the task to reuse saved work."))
    import uvicorn
    if args.open:
        import webbrowser
        opener = threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}/"))
        opener.daemon = True
        opener.start()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
