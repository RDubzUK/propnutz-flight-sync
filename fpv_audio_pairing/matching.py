"""Content evidence first, camera-clock suggestions after user confirmation."""
from __future__ import annotations

import hashlib
import math
from collections import Counter
from statistics import median


def overlap(fpv_duration, stick_duration, offset):
    """Intersect the complete source timelines at the sync offset.

    Audio evidence establishes the offset; its sampled/matching span does not
    limit the footage that can be reviewed or exported at that offset.
    """
    if not all(math.isfinite(v) for v in (fpv_duration, stick_duration, offset)):
        raise ValueError("Alignment must use finite durations and offset")
    fstart, sstart = max(0., -offset), max(0., offset)
    return {"fpv_start": fstart, "radio_start": sstart,
            "overlap_duration": max(0., min(fpv_duration - fstart, stick_duration - sstart))}


def pair_id(fpv, stick):
    return hashlib.sha256(f"{fpv}:{stick}".encode()).hexdigest()[:32]


def make_pair(fpv, stick, offset, **details):
    return {"id": pair_id(fpv["id"], stick["id"]), "fpv": fpv["id"], "stick": stick["id"],
            "offset": float(offset), "confirmed": False, **details,
            **overlap(fpv["metadata"]["duration"], stick["metadata"]["duration"], offset)}


def refresh_pair_ranges(session):
    """Rebuild derived ranges, including older saved pairs, without moving sync."""
    records = {r["id"]: r for r in session["videos"]}
    for pair in session["pairs"]:
        fpv, stick = records.get(pair["fpv"]), records.get(pair["stick"])
        if pair.get("stale") or not fpv or not stick or not fpv.get("metadata") or not stick.get("metadata"):
            continue
        pair.update(overlap(fpv["metadata"]["duration"], stick["metadata"]["duration"], pair["offset"]))
    return session


def clock_start(record, method, modified_kind="end"):
    stamp = record.get("filename_time") if method == "filename" else record["mtime"]
    if stamp is None or not record.get("metadata"):
        return None
    return stamp - (record["metadata"]["duration"] if method == "modified" and modified_kind == "end" else 0)


def clock_model(session, method):
    records = {r["id"]: r for r in session["videos"]}
    values, anchors = [], []
    kind = session.get("modified_kind", "end")
    for pair in session["pairs"]:
        if not pair.get("confirmed") or pair.get("stale"):
            continue
        f, s = records[pair["fpv"]], records[pair["stick"]]
        fc, sc = clock_start(f, method, kind), clock_start(s, method, kind)
        if fc is None or sc is None:
            continue
        delta = sc - fc + pair["offset"]
        values.append(delta)
        anchors.append({"pair": pair["id"], "stick": s["id"], "delta": delta,
                        "modified_difference": s["mtime"] - f["mtime"]})
    if not values:
        return None
    centre = median(values)
    consistent = all(abs(v - centre) <= 2. for v in values)
    return {"method": method, "delta": centre, "consistent": consistent, "anchors": anchors,
            "independent_flights": len({a["stick"] for a in anchors}),
            "tentative": len({a["stick"] for a in anchors}) < 2}


def suggest(session):
    """Allow many FPV parts per StickCam; never treat duration as identity proof."""
    refresh_pair_ranges(session)
    models = [m for method in ["modified", *( ["filename"] if session.get("use_filenames", True) else [])]
              if (m := clock_model(session, method))]
    session["clocks"] = models
    session["clock_warnings"] = []
    # Rebuild only clock proposals. Preserve audio evidence and user-confirmed pairs.
    retained = [p for p in session["pairs"] if p.get("confirmed") or p.get("method") != "timestamp"]
    known = {p["id"] for p in retained}
    records = [r for r in session["videos"] if r.get("metadata") and not r.get("stale")]
    counts = {m: Counter(clock_start(r, m, session.get("modified_kind", "end")) for r in records)
              for m in ("modified", "filename")}
    # Raw identical modification dates commonly indicate a copy operation.
    raw_counts = Counter(r["mtime"] for r in records)
    for model in models:
        if not model["consistent"]:
            session["clock_warnings"].append(f"Confirmed {model['method']} clock offsets disagree; suggestions from this clock are disabled.")
            continue
        method = model["method"]
        repeated = False
        for f in [r for r in records if r["kind"] == "fpv"]:
            for s in [r for r in records if r["kind"] == "stick"]:
                pid = pair_id(f["id"], s["id"])
                if pid in known:
                    continue
                fc, sc = clock_start(f, method, session.get("modified_kind", "end")), clock_start(s, method, session.get("modified_kind", "end"))
                if fc is None or sc is None:
                    continue
                if (method == "modified" and max(raw_counts[f["mtime"]], raw_counts[s["mtime"]]) > 1
                    or method == "filename" and max(counts[method][fc], counts[method][sc]) > 1):
                    repeated = True
                    continue
                offset = model["delta"] + fc - sc
                pair = make_pair(f, s, offset, method="timestamp", clock_method=method,
                                 confidence="Timestamp suggestion", score=None, evidence=None)
                if pair["overlap_duration"] >= session.get("min_overlap", 2):
                    retained.append(pair)
                    known.add(pid)
        if repeated:
            session["clock_warnings"].append(f"Repeated {method} timestamps were excluded; these may be reset or copied dates.")
    session["pairs"] = retained
