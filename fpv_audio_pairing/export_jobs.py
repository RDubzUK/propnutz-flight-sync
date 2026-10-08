"""Resumable pair exports with checked completed-part reuse."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from . import store, export_locations
from .exports import export_pair, _output_info
from .cut_checks import compare_cut


def alignment_key(selected):
    return hashlib.sha256(json.dumps([{k: p.get(k) for k in ("id", "offset", "source_signatures", "overlap_duration")}
                                     for p in sorted(selected, key=lambda p: p["id"])], sort_keys=True).encode()).hexdigest()


def run_export(sid, options, selected, spec, progress, flag, video, execute):
    doc = store.read(sid)
    if spec.get("directory"):
        directory = Path(spec["directory"])
        if not directory.is_dir():
            raise RuntimeError("Reconnect the original export folder before resuming, or start a new export.")
    else:
        root = export_locations.destination(options.destination.strip())
        directory = export_locations.create_directory(root, doc["name"])
        spec["directory"] = str(directory)
        store.update(sid, lambda s: s["job"].update(resume=spec))
    store.update(sid, lambda s: s.update(export_destination=options.destination.strip()))
    base = {"id": spec["eid"], "session": sid, "session_name": doc["name"], "created": time.time(),
            "pairs": len(selected), "profile": options.profile, "fps": options.fps or "original", "directory": str(directory)}
    export_locations.register_pending(base)
    manifests, pair_directories = [], []
    for i, p in enumerate(selected):
        f, r = video(sid, p["fpv"]), video(sid, p["stick"])
        end = options.trim_end if options.trim_end is not None else p["overlap_duration"]
        info = p | {"radio_start": p["radio_start"] + options.trim_start, "fpv_start": p["fpv_start"] + options.trim_start,
                    "overlap_duration": end - options.trim_start, "fpv_source": f["name"], "stick_source": r["name"],
                    "source_metadata": {"radio": r["metadata"], "fpv": f["metadata"]},
                    "resume_key": spec["alignment_key"], "requested_trim": [options.trim_start, options.trim_end]}
        relative = "." if len(selected) == 1 else f"{i + 1:03d}_{export_locations.folder_name(Path(f['name']).stem, 50)}"
        part = directory / relative
        pair_directories.append(relative)
        manifest = None
        try:
            saved = json.loads((part / "alignment.json").read_text())
            if (saved.get("resume_key") == spec["alignment_key"] and saved.get("requested_trim") == info["requested_trim"]
                and saved["export_profile"] == options.profile and saved["export_fps"] == (options.fps or "original")):
                for kind, key, source in (("StickCam", "radio_export", r), ("FPV", "fpv_export", f)):
                    output = part / saved[key]
                    if output.parent.resolve() != part.resolve():
                        raise ValueError("Invalid export filename")
                    _output_info(output, saved["export_duration"], source["metadata"]["fps"],
                                 frame_count=saved.get("export_frame_count"), copy=options.profile == "copy",
                                 run=lambda cmd, log: execute(flag, cmd, log))
                manifest = saved
                progress(100 * (i + 1) / len(selected), f"Reused checked pair {i + 1}/{len(selected)}")
        except (OSError, ValueError, KeyError, RuntimeError):
            if flag.is_set():
                raise RuntimeError("Cancelled")
        if manifest is None:
            def run(cmd, log):
                source_index = 0 if Path(log).stem == "StickCam" else 1
                return execute(flag, cmd, log, on_progress=lambda fraction:
                               progress(100 * (i + (source_index + fraction) / 2) / len(selected),
                                        f"Pair {i + 1}/{len(selected)} · {Path(log).stem} {fraction:.0%}"))
            manifest = export_pair(info, Path(r["path"]), Path(f["path"]), part, options.fps, options.profile, run=run,
                                   progress=lambda message: progress(100 * i / len(selected), f"Pair {i + 1}/{len(selected)} · {message}"))
        if options.verify_frames and not manifest.get("decoded_cut_checks"):
            progress(100 * (i + .95) / len(selected), f"Checking decoded frames · pair {i + 1}/{len(selected)}")
            manifest["decoded_cut_checks"] = {
                kind: compare_cut(source["path"], part / manifest[key], info[start], manifest["export_duration"], source["metadata"]["fps"], flag)
                for kind, key, source, start in (("StickCam", "radio_export", r, "radio_start"), ("FPV", "fpv_export", f, "fpv_start"))}
            export_locations._write_json(part / "alignment.json", manifest)
        video(sid, p["fpv"])
        video(sid, p["stick"])
        manifests.append(manifest)
        store.update(sid, lambda s: s["job"].update(completed_pairs=i + 1, total_pairs=len(selected)))
    if flag.is_set():
        raise RuntimeError("Cancelled")
    result = base | {"pair_directories": pair_directories, "decoded_checks": options.verify_frames,
                     "flight_groups": sorted({p["stick"] for p in selected})}
    # Flight manifest preserves the StickCam timeline for split parts, without
    # concatenating originals or imposing a common frame rate.
    export_locations._write_json(directory / "flights.json", {"session": doc["name"], "parts": [
        {"pair": p["id"], "stick": p["stick"], "fpv": p["fpv"], "directory": d,
         "stick_start": m["radio_start"], "fpv_start": m["fpv_start"], "duration": m["export_duration"]}
        for p, d, m in zip(selected, pair_directories, manifests)]})
    export_locations.save(result)
    def save(s):
        s["exports"] = [e for e in s["exports"] if e["id"] != result["id"]] + [result]
    store.update(sid, save)
