"""Content evidence first, camera-clock suggestions after user confirmation."""
from __future__ import annotations

import hashlib
import math
from collections import Counter
from statistics import median

CLOCK_TOLERANCE = 2.0


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
    if stamp is None or not record.get("metadata") or not math.isfinite(stamp):
        return None
    duration = record["metadata"]["duration"]
    if not math.isfinite(duration) or duration <= 0:
        return None
    return stamp - (duration if method == "modified" and modified_kind == "end" else 0)


def clock_model(session, method):
    records = {r["id"]: r for r in session["videos"]}
    values, anchors = [], []
    kind = session.get("modified_kind", "end")
    for pair in session["pairs"]:
        if not pair.get("confirmed") or pair.get("stale"):
            continue
        f, s = records.get(pair["fpv"]), records.get(pair["stick"])
        if not f or not s or not math.isfinite(pair["offset"]):
            continue
        fc, sc = clock_start(f, method, kind), clock_start(s, method, kind)
        if fc is None or sc is None:
            continue
        delta = sc - fc + pair["offset"]
        values.append(delta)
        anchors.append({"pair": pair["id"], "fpv": f["id"], "stick": s["id"], "delta": delta,
                        "alignment_method": pair.get("method", "manual"), "offset": pair["offset"],
                        "modified_difference": s["mtime"] - f["mtime"]})
    if not values:
        return None
    centre = median(values)
    consistent = all(abs(v - centre) <= CLOCK_TOLERANCE for v in values)
    return {"method": method, "delta": centre, "consistent": consistent, "anchors": anchors,
            "tolerance": CLOCK_TOLERANCE,
            "independent_flights": len({a["stick"] for a in anchors}),
            "tentative": len({a["stick"] for a in anchors}) < 2}


def _clock_models(session):
    return [m for method in ["modified", *(["filename"] if session.get("use_filenames", True) else [])]
            if (m := clock_model(session, method))]


def _clock_data(session):
    records = [r for r in session["videos"] if r.get("metadata") and not r.get("stale")]
    counts = {m: Counter((r["kind"], clock_start(r, m, session.get("modified_kind", "end"))) for r in records)
              for m in ("modified", "filename")}
    # Duplicates within a feed can indicate copied/reset dates. A date shared
    # by one FPV and one StickCam recording is not itself a duplicate clock.
    raw_counts = Counter((r["kind"], r["mtime"]) for r in records)
    return records, counts, raw_counts


def _repeated_dates(f, s, method, fc, sc, counts, raw_counts):
    return (max(raw_counts[(f["kind"], f["mtime"])], raw_counts[(s["kind"], s["mtime"])]) > 1
            if method == "modified" else max(counts[method][(f["kind"], fc)], counts[method][(s["kind"], sc)]) > 1)


def refresh_clock_evidence(session, models=None):
    """Refresh candidate evidence, including old sessions, without audio work.

    This annotates existing pairs only. Reads neither generate proposals nor
    move any saved alignment, and confirmed anchors never corroborate themselves.
    """
    models = _clock_models(session) if models is None else models
    session["clocks"] = models
    records, counts, raw_counts = _clock_data(session)
    by_id = {r["id"]: r for r in records}
    for pair in session["pairs"]:
        pair.pop("clock_support", None)
        if pair.get("confirmed") or pair.get("stale"):
            continue
        f, s = by_id.get(pair["fpv"]), by_id.get(pair["stick"])
        if not f or not s:
            continue
        support = []
        for model in models:
            method = model["method"]
            fc, sc = clock_start(f, method, session.get("modified_kind", "end")), clock_start(s, method, session.get("modified_kind", "end"))
            if fc is None or sc is None:
                continue
            details = {"method": method, "tolerance": CLOCK_TOLERANCE,
                       "independent_flights": model["independent_flights"], "tentative": model["tentative"],
                       "anchors": [a["pair"] for a in model["anchors"]], "clock_delta": model["delta"],
                       "modified_difference": s["mtime"] - f["mtime"],
                       "modified_kind": session.get("modified_kind", "end")}
            if not model["consistent"]:
                support.append(details | {"status": "conflicting", "agrees": False})
                continue
            if _repeated_dates(f, s, method, fc, sc, counts, raw_counts):
                support.append(details | {"status": "repeated_dates", "agrees": False})
                continue
            expected = model["delta"] + fc - sc
            difference = pair["offset"] - expected
            support.append(details | {"status": "available", "expected_offset": expected,
                                      "alignment_difference": difference, "agrees": abs(difference) <= CLOCK_TOLERANCE})
        if support:
            pair["clock_support"] = support
    return session


def suggest(session):
    """Allow many FPV parts per StickCam; never treat duration as identity proof."""
    refresh_pair_ranges(session)
    models = _clock_models(session)
    session["clock_warnings"] = []
    # Rebuild only clock proposals. Preserve audio evidence and user-confirmed pairs.
    retained = [p for p in session["pairs"] if p.get("confirmed") or p.get("method") != "timestamp"]
    known = {p["id"] for p in retained}
    records, counts, raw_counts = _clock_data(session)
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
                if _repeated_dates(f, s, method, fc, sc, counts, raw_counts):
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
    refresh_clock_evidence(session, models)
