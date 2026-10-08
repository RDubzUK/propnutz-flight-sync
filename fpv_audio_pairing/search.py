"""Bounded adaptive audio search with durable per-recording checkpoints."""
from __future__ import annotations

import hashlib
import json
import math
import time

import numpy as np

from . import matching, review, store
from .evidence import assess_audio_pair, audio_sections, POLICY_VERSION
from .fingerprint import ALGORITHM_VERSION


def run_match(sid, options, progress, flag, load_audio, clean, counterpart_fpv=None):
    doc = store.read(sid)
    records = [r for r in doc["videos"] if r.get("metadata", {}).get("has_audio") and not r.get("error") and not r.get("missing")]
    selected = set(options.selected)
    scope = {r["kind"] for r in records if r["id"] in selected}
    if selected and not scope:
        raise ValueError("Selected recordings have no readable audio")
    fpvs, sticks = [[r for r in records if r["kind"] == k and (k not in scope or r["id"] in selected)] for k in ("fpv", "stick")]
    if not selected:
        fpvs = [r for r in fpvs if not r.get("no_counterpart")]
    seed = sticks if scope == {"stick"} else fpvs
    if options.fraction < 1 and seed:
        indices = np.unique(np.linspace(0, len(seed) - 1, max(1, math.ceil(len(seed) * options.fraction))).astype(int))
        if scope == {"stick"}:
            sticks = [seed[i] for i in indices]
        else:
            fpvs = [seed[i] for i in indices]
    if not fpvs or not sticks:
        raise ValueError("Audio matching requires at least one FPV and one StickCam recording with audio. Restore any 'No counterpart' clips to search them again.")
    levels = [options.boundary]
    if options.adaptive:
        levels += [v for v in (60, 120, 300) if options.boundary < v <= options.retry_limit]
    key = hashlib.sha256(json.dumps({"options": options.model_dump(), "sources": [(r["id"], r["signature"]) for r in fpvs + sticks],
                                    "policy": POLICY_VERSION, "algorithm": ALGORITHM_VERSION}, sort_keys=True).encode()).hexdigest()
    path = store.directory(sid) / "work" / f"match-{key}.json"
    try:
        checkpoint = json.loads(path.read_text())
    except (OSError, ValueError):
        checkpoint = {"rounds": {}}
    pending, best, outcomes = list(fpvs), {}, {}
    failures, comparisons, reused = [], 0, 0
    total_units = len(levels) * (len(fpvs) + len(sticks) + len(fpvs) * len(sticks))
    units = 0

    def report(message):
        progress(min(95, 95 * units / max(1, total_units)), message)

    def save_round():
        def change(s):
            protected = [p for p in s["pairs"] if p.get("confirmed") or p.get("method") == "manual" or review.state(p) in {"rejected", "later"}]
            protected_ids = {p["id"] for p in protected}
            scanned = set(best)
            other = [p for p in s["pairs"] if p["id"] not in protected_ids and p.get("method") == "audio" and p["fpv"] not in scanned]
            candidates = [p for owners in best.values() for p in owners[:3] if p["id"] not in protected_ids]
            for p in candidates:
                p["review_state"] = s.get("decisions", {}).get(p["id"], "candidate")
            s.update(pairs=protected + other + candidates, use_filenames=options.use_filenames, modified_kind=options.modified_kind,
                     min_overlap=options.min_overlap, match_errors=list(dict.fromkeys(failures)),
                     match_summary={"comparisons": comparisons, "reused_comparisons": reused, "candidates": len(candidates),
                                    "fpv": len(fpvs), "stick": len(sticks), "rounds": len(checkpoint["rounds"]), "adaptive": options.adaptive})
            for r in s["videos"]:
                if r["id"] in outcomes:
                    r.update(match_checked=time.time(), match_outcome=outcomes[r["id"]])
            if counterpart_fpv:
                s["counterpart_search"] = {"fpv": counterpart_fpv, "completed": time.time(), "boundary": options.boundary,
                                          "comparisons": comparisons, "candidates": len(candidates), "stick": len(sticks), "errors": failures}
            matching.suggest(s)
        store.update(sid, change)

    for boundary in levels:
        if not pending:
            break
        round_results = checkpoint["rounds"].setdefault(str(boundary), {})
        todo = [f for f in pending if f["id"] not in round_results]
        data = {}
        for r in (todo + sticks if todo else []):
            units += 1
            report(f"Audio retry {boundary:g}s per end · {r['name']}")
            try:
                data[r["id"]] = load_audio(r, boundary)
            except Exception as exc:
                if flag.is_set():
                    raise
                failures.append(f"{r['name']}: {exc}")
        next_pending = []
        for f in pending:
            if flag.is_set():
                raise RuntimeError("Cancelled")
            if f["id"] in round_results:
                saved = round_results[f["id"]]
                owners, reason = saved["owners"], saved["reason"]
                reused += len(sticks)
                units += len(sticks)
                report(f"Reusing saved comparisons · {f['name']}")
            else:
                owners, strongest = [], None
                for r in sticks:
                    units += 1
                    comparisons += 1
                    report(f"Comparing {boundary:g}s audio · {f['name']} / {r['name']}")
                    if f["id"] not in data or r["id"] not in data:
                        continue
                    a, b = data[r["id"]], data[f["id"]]
                    e = assess_audio_pair(a, b, options.min_overlap)
                    score = e["score"] if e["eligible"] else e["best_score"]
                    if strongest is None or score > strongest[0]:
                        strongest = (score, e)
                    if score < .40:
                        continue
                    offset = e["offset"] if e["eligible"] else e["best_offset"]
                    e["sections"] = audio_sections(a, b, offset)
                    p = matching.make_pair(f, r, offset, method="audio", score=float(score), evidence=clean(e), confidence="Possible",
                                          audio_boundary=boundary, source_signatures={"fpv": f["signature"], "stick": r["signature"]})
                    if p["overlap_duration"] >= options.min_overlap:
                        owners.append(p)
                owners.sort(key=lambda p: p["score"], reverse=True)
                for i, p in enumerate(owners):
                    gap = p["score"] - max((q["score"] for q in owners if q["id"] != p["id"]), default=0)
                    p["owner_margin"] = gap
                    if p["evidence"]["eligible"] and gap >= .08 and i == 0:
                        p["confidence"] = "Strong"
                    elif p["score"] < .65:
                        p["confidence"] = "Weak"
                reason = ("Strong audio candidate found; review to confirm." if owners and owners[0]["confidence"] == "Strong" else
                          "Sampled audio has too little usable variation. Extend the sample or align manually." if strongest and strongest[1]["quality"] < .1 else
                          "; ".join(strongest[1]["reasons"]) if strongest else "Audio could not be prepared. Check source access and decoding errors.")
                round_results[f["id"]] = {"owners": owners, "reason": reason}
                path.parent.mkdir(parents=True, exist_ok=True)
                temp = path.with_suffix(".tmp")
                temp.write_text(json.dumps(checkpoint, allow_nan=False))
                store._replace_session(temp, path)
            # Wider samples can contain motor noise that weakens useful launch
            # or landing audio. Retain each pair's best sampled evidence.
            merged = {p["id"]: p for p in best.get(f["id"], [])}
            for p in owners:
                previous = merged.get(p["id"])
                rank = lambda item: (item["confidence"] == "Strong", item["score"])
                if previous is None or rank(p) > rank(previous):
                    merged[p["id"]] = p
            best[f["id"]] = sorted(merged.values(), key=lambda p: (p["confidence"] == "Strong", p["score"]), reverse=True)
            outcomes[f["id"]] = {"boundary": boundary, "reason": reason, "strong": bool(owners and owners[0]["confidence"] == "Strong")}
            # Stop expansion only for uniquely strong content evidence. A
            # rejected candidate never suppresses a search for another owner.
            if not owners or owners[0]["confidence"] != "Strong" or doc.get("decisions", {}).get(owners[0]["id"]) == "rejected":
                next_pending.append(f)
        save_round()
        pending = next_pending
    progress(98, "Saving review queue and related date suggestions")
