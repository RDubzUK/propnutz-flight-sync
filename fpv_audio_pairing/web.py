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
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import store, matching, preview
from .cache import _key, get_or_extract
from .evidence import assess_audio_pair, audio_sections
from .exports import export_pair, stream_archive
from .fingerprint import ALGORITHM_VERSION, extract_audio, validate_audio
from .metadata import filename_timestamp, probe_video

app = FastAPI(title="PropNutz Flight Sync")
STATIC = Path(__file__).parent / "static"
WORKERS = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio-pairing")
PREVIEWS = threading.Semaphore(2)
FLAGS = {}
TASK_SAVE_ERRORS = {}
ACTIVE = threading.RLock()
EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".mts", ".m2ts", ".webm"}


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
        return task_save_status(matching.refresh_pair_ranges(store.read(sid)))
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Session not found") from None


def video(sid, vid):
    s = session(sid)
    r = next((r for r in s["videos"] if r["id"] == vid), None)
    if r is None:
        raise HTTPException(404, "Recording not found")
    try:
        stat = Path(r["path"]).stat()
        if [stat.st_size, stat.st_mtime_ns] != r["signature"]:
            raise HTTPException(409, "Source changed. Rescan this session before continuing.")
    except OSError:
        raise HTTPException(409, "Source recording unavailable. Reconnect its folder or network share.") from None
    return r


def idle(sid):
    with ACTIVE:
        if sid in FLAGS or session(sid).get("job", {}).get("status") in {"queued", "running"}:
            raise HTTPException(409, "A task is already running for this session")


def task(sid, title, work, *, target_fpv=None):
    with ACTIVE:
        idle(sid)
        flag = threading.Event()
        start = time.time()
        job = {"status": "queued", "title": title, "message": "Waiting for the processing queue", "percent": 0,
               "started": start, "elapsed": 0, "eta": None}
        if target_fpv is not None:
            job["target_fpv"] = target_fpv
        store.update(sid, lambda s: s.update(job=job))
        FLAGS[sid] = flag
        TASK_SAVE_ERRORS.pop(sid, None)

    def update(percent, message):
        if flag.is_set():
            raise RuntimeError("Cancelled")
        elapsed = time.time() - start
        store.update(sid, lambda s: s["job"].update(status="running", percent=round(percent, 1), message=message,
                     elapsed=round(elapsed, 1), eta=round(elapsed * (100 - percent) / percent) if percent > 1 else None))

    def run():
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


def execute(flag, command, logfile, timeout=4 * 3600):
    logfile = Path(logfile)
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with logfile.open("wb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        start = time.monotonic()
        try:
            while process.poll() is None:
                if flag.is_set():
                    raise RuntimeError("Cancelled")
                if time.monotonic() - start > timeout:
                    raise RuntimeError("Encoding timed out")
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


def cache_path(sid, r, boundary):
    return store.directory(sid) / "audio" / f"audio.{_key(r['path'], ALGORITHM_VERSION, {'boundary_seconds': boundary})}.npz"


def audio(sid, r, boundary):
    video(sid, r["id"])
    started = time.monotonic()
    cached = cache_path(sid, r, boundary).exists()
    data = get_or_extract(r["path"], store.directory(sid) / "audio", "audio", ALGORITHM_VERSION,
                          {"boundary_seconds": boundary}, lambda: extract_audio(r["path"], boundary), validate=validate_audio)
    status = "ready" if len(data["time"]) and float(data["quality"]) > .1 else "unusable"
    def save(s):
        record = next(v for v in s["videos"] if v["id"] == r["id"])
        record.update(audio_status=status, audio_boundary=boundary, audio_quality=float(data["quality"]),
                      audio_seconds=round(time.monotonic() - started, 2), audio_reused=cached)
    store.update(sid, save)
    return data


def scan(sid, progress, flag):
    s = session(sid)
    old = {r["path"]: r for r in s["videos"]}
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
                resolved = str(path.resolve())
                stat = path.stat()
                record = {"id": hashlib.sha256(f"{kind}:{resolved}".encode()).hexdigest()[:32], "kind": kind,
                          "name": path.name, "path": resolved, "mtime": stat.st_mtime,
                          "signature": [stat.st_size, stat.st_mtime_ns], "filename_time": filename_timestamp(path.name)}
                previous = old.get(resolved)
                if previous and previous["signature"] == record["signature"] and previous["kind"] == kind:
                    record.update({k: v for k, v in previous.items() if k not in record and k != "stale"})
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


def find(sid, options, progress, flag, *, counterpart_fpv=None):
    s = session(sid)
    records = [r for r in s["videos"] if r.get("metadata", {}).get("has_audio") and not r.get("error")]
    fpvs, sticks = [[r for r in records if r["kind"] == k] for k in ("fpv", "stick")]
    selected = set(options.selected)
    scope_kind = {r["kind"] for r in records if r["id"] in selected}
    if selected and not scope_kind:
        raise ValueError("Selected recordings have no readable audio")
    # Selection filters one or both sides; the opposite side remains searchable.
    if "fpv" in scope_kind:
        fpvs = [r for r in fpvs if r["id"] in selected]
    if "stick" in scope_kind:
        sticks = [r for r in sticks if r["id"] in selected]
    # Evenly sample one seed side while preserving all candidates on the other.
    seed = sticks if scope_kind == {"stick"} else fpvs
    if options.fraction < 1 and seed:
        indices = np.unique(np.linspace(0, len(seed) - 1, max(1, math.ceil(len(seed) * options.fraction))).astype(int))
        seed = [seed[i] for i in indices]
        if scope_kind == {"stick"}:
            sticks = seed
        else:
            fpvs = seed
    if not fpvs or not sticks:
        raise ValueError("Audio matching requires at least one FPV and one StickCam recording with an audio track")
    total = len(fpvs) + len(sticks)
    fingerprints = {}
    failures = []
    for index, r in enumerate(fpvs + sticks):
        progress(55 * index / total, f"Reading audio {index + 1}/{total} · {r['name']}")
        try:
            fingerprints[r["id"]] = audio(sid, r, options.boundary)
        except Exception as exc:
            failures.append(f"{r['name']}: {exc}")
    candidates = []
    count = len(fpvs) * len(sticks)
    done = 0
    for f in fpvs:
        owners = []
        for r in sticks:
            done += 1
            progress(55 + 40 * done / count, f"Comparing audio {done}/{count} · {f['name']}")
            if f["id"] not in fingerprints or r["id"] not in fingerprints:
                continue
            a, b = fingerprints[r["id"]], fingerprints[f["id"]]
            evidence = assess_audio_pair(a, b, options.min_overlap)
            lag = evidence["offset"] if evidence["eligible"] else evidence["best_offset"]
            score = evidence["score"] if evidence["eligible"] else evidence["best_score"]
            if score < .40:
                continue
            evidence["sections"] = audio_sections(a, b, lag)
            pair = matching.make_pair(f, r, lag, method="audio", score=float(score), evidence=clean(evidence),
                                      confidence="Possible", source_signatures={"fpv": f["signature"], "stick": r["signature"]})
            if pair["overlap_duration"] >= options.min_overlap:
                owners.append(pair)
        owners.sort(key=lambda p: p["score"], reverse=True)
        for index, p in enumerate(owners[:3]):
            owner_gap = p["score"] - max((q["score"] for q in owners if q["id"] != p["id"]), default=0)
            p["owner_margin"] = owner_gap
            if p["evidence"]["eligible"] and owner_gap >= .08 and index == 0:
                p["confidence"] = "Strong"
            elif p["score"] < .65:
                p["confidence"] = "Weak"
            candidates.append(p)
    def save(doc):
        confirmed = [p for p in doc["pairs"] if p.get("confirmed") or p.get("method") == "manual"]
        keep_ids = {p["id"] for p in confirmed}
        scanned = {f["id"] for f in fpvs}
        other = [p for p in doc["pairs"] if not p.get("confirmed") and p.get("method") == "audio" and p["fpv"] not in scanned]
        doc.update(pairs=confirmed + other + [p for p in candidates if p["id"] not in keep_ids],
                   use_filenames=options.use_filenames, modified_kind=options.modified_kind,
                   min_overlap=options.min_overlap, match_errors=failures,
                   match_summary={"comparisons": done, "candidates": len(candidates), "fpv": len(fpvs), "stick": len(sticks)})
        if counterpart_fpv is not None:
            doc["counterpart_search"] = {
                "fpv": counterpart_fpv, "completed": time.time(), "boundary": options.boundary,
                "comparisons": done, "candidates": len(candidates), "stick": len(sticks), "errors": failures,
            }
        matching.suggest(doc)
    store.update(sid, save)


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
    return [{k: s.get(k) for k in ("id", "name", "created", "folders", "job")} | {"videos": len(s["videos"]),
            "confirmed": sum(p.get("confirmed", False) for p in s["pairs"])} for s in map(task_save_status, store.sessions())]


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
    task(sid, "Scanning source folders", lambda update, flag: scan(sid, update, flag))
    return session(sid)


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    return session(sid)


class Rename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@app.patch("/api/sessions/{sid}")
def rename(sid: str, options: Rename):
    session(sid)
    return store.update(sid, lambda s: s.update(name=options.name.strip() or "Untitled session"))


class ClockOptions(BaseModel):
    use_filenames: bool = True
    modified_kind: str = "end"


@app.patch("/api/sessions/{sid}/clocks")
def clock_settings(sid: str, options: ClockOptions):
    idle(sid)
    if options.modified_kind not in {"start", "end"}:
        raise HTTPException(400, "Modified dates must represent recording start or end")
    def change(s):
        s.update(use_filenames=options.use_filenames, modified_kind=options.modified_kind)
        matching.suggest(s)
    return store.update(sid, change)


@app.delete("/api/sessions/{sid}")
def delete(sid: str):
    with ACTIVE, store.LOCK:
        idle(sid)
        shutil.rmtree(store.directory(sid))
        TASK_SAVE_ERRORS.pop(sid, None)
    return {"deleted": True, "exports_preserved": str(store.ROOT / "exports" / sid)}


@app.post("/api/sessions/{sid}/cancel")
def cancel(sid: str):
    session(sid)
    with ACTIVE:
        if sid in FLAGS:
            FLAGS[sid].set()
    return {"message": "Cancellation requested; audio decoding may finish its current section first"}


@app.post("/api/sessions/{sid}/scan")
def rescan(sid: str):
    return task(sid, "Scanning source folders", lambda update, flag: scan(sid, update, flag))


@app.post("/api/sessions/{sid}/match")
def match(sid: str, options: MatchOptions):
    if options.modified_kind not in {"start", "end"}:
        raise HTTPException(400, "Modified dates must represent recording start or end")
    return task(sid, "Finding matching flights", lambda update, flag: find(sid, options, update, flag))


class CounterpartOptions(BaseModel):
    fpv: str
    boundary: float = Field(default=30, ge=10, le=300)


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
                                 use_filenames=current.get("use_filenames", True),
                                 modified_kind=current.get("modified_kind", "end"),
                                 min_overlap=current.get("min_overlap", 2))
    return task(sid, "Finding StickCam counterpart",
                lambda update, flag: find(sid, match_options, update, flag, counterpart_fpv=source["id"]),
                target_fpv=source["id"])


class PairOptions(BaseModel):
    fpv: str
    stick: str
    offset: float = Field(allow_inf_nan=False)
    confirmed: bool = False


@app.post("/api/sessions/{sid}/pairs")
def save_pair(sid: str, options: PairOptions):
    idle(sid)
    f, r = video(sid, options.fpv), video(sid, options.stick)
    if f["kind"] != "fpv" or r["kind"] != "stick" or not f.get("metadata") or not r.get("metadata"):
        raise HTTPException(400, "Choose one readable recording of each type")
    p = matching.make_pair(f, r, options.offset)
    if p["overlap_duration"] < .1:
        raise HTTPException(400, "The recordings do not overlap at that offset")
    def save(s):
        existing = next((q for q in s["pairs"] if q["id"] == p["id"]), None)
        if existing:
            changed = abs(existing["offset"] - options.offset) > .00001
            existing.update(p, confirmed=options.confirmed, stale=False)
            if changed and existing.get("evidence"):
                existing["evidence"] = None
                existing["confidence"] = "Manually adjusted"
        else:
            existing = p | {"method": "manual", "confidence": "Manual alignment", "score": None, "evidence": None,
                            "confirmed": options.confirmed}
            s["pairs"].append(existing)
        existing["source_signatures"] = {"fpv": f["signature"], "stick": r["signature"]}
        if options.confirmed:
            existing["confirmed_at"] = time.time()
            existing["modified_difference"] = r["mtime"] - f["mtime"]
        matching.suggest(s)
    return store.update(sid, save)


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


@app.post("/api/sessions/{sid}/export")
def export(sid: str, options: ExportOptions):
    s = session(sid)
    selected = [p for p in s["pairs"] if p["id"] in set(options.pairs)]
    if len(selected) != len(set(options.pairs)) or any(not p.get("confirmed") or p.get("stale") for p in selected):
        raise HTTPException(400, "Export requires confirmed pairs with unchanged source recordings")
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
    eid = uuid.uuid4().hex
    directory = store.ROOT / "exports" / store.identifier(sid) / eid
    def run(progress, flag):
        directory.mkdir(parents=True, exist_ok=True)
        manifests = []
        for index, p in enumerate(selected):
            f, r = video(sid, p["fpv"]), video(sid, p["stick"])
            end = options.trim_end if options.trim_end is not None else p["overlap_duration"]
            info = p | {"radio_start": p["radio_start"] + options.trim_start, "fpv_start": p["fpv_start"] + options.trim_start,
                        "overlap_duration": end - options.trim_start, "fpv_source": f["name"], "stick_source": r["name"],
                        "source_metadata": {"radio": r["metadata"], "fpv": f["metadata"]}}
            manifest = export_pair(info, Path(r["path"]), Path(f["path"]), directory / f"pair_{p['id']}", options.fps,
                options.profile, run=lambda cmd, log: execute(flag, cmd, log),
                progress=lambda message: progress(100 * index / len(selected), f"Pair {index + 1}/{len(selected)} · {message}"))
            video(sid, p["fpv"])
            video(sid, p["stick"])
            manifests.append(manifest)
        if flag.is_set():
            raise RuntimeError("Cancelled")
        result = {"id": eid, "session": sid, "session_name": s["name"], "created": time.time(), "pairs": len(manifests),
                  "profile": options.profile, "fps": options.fps if options.fps is not None else "original", "directory": str(directory)}
        (directory / "export.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        store.update(sid, lambda doc: doc["exports"].append(result))
    return task(sid, "Exporting aligned clips", run)


@app.get("/api/exports")
def exports():
    records = []
    for path in (store.ROOT / "exports").glob("*/*/export.json"):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(records, key=lambda r: r["created"], reverse=True)


@app.get("/api/exports/{sid}/{eid}/download")
def download(sid: str, eid: str):
    try:
        directory = store.ROOT / "exports" / store.identifier(sid) / store.identifier(eid)
    except ValueError:
        raise HTTPException(404, "Export not found") from None
    if not (directory / "export.json").is_file():
        raise HTTPException(404, "Export not complete or not found")
    return StreamingResponse(stream_archive(directory), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="aligned_pairs_{eid[:8]}.zip"'})


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
    args = parser.parse_args()
    for s in store.sessions():
        if s.get("job", {}).get("status") in {"queued", "running"}:
            store.update(s["id"], lambda d: d["job"].update(status="interrupted", message="App restarted; run the task again. Saved fingerprints will be reused."))
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
