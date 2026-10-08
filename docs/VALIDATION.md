# Accuracy and recovery validation

## Known-answer collection

In Pair Review, open **Add a known answer to the validation collection**. Save clearly identified matching flights and definitely incorrect pairs. For an unconfirmed match, explicitly check that you independently know its identity. Labels never automatically confirm a pair or teach a camera clock.

Leave **Known offset** blank when you know the flight but have not measured its sync. This tests identity only. Enter an independently measured StickCam-minus-FPV offset to test timing as well; default allowed error is 0.15 seconds. A wrong estimated offset counts as a failed positive case even if the recordings are correctly identified.

**Accuracy & reference collection → Run reference validation** compares every reference FPV against the session's readable StickCam recordings. It uses the same evidence gates and competing-owner margin as matching. Reports include correct matches, false positives, missed/wrong-offset matches, correct non-matches, skipped sources, offset errors, algorithm/policy versions and the sampling boundary. Skipped recordings are excluded from measured precision/recall. A small or deliberately easy collection is not a general success rate. Save the report locally and rerun after changing labels, sources or policy.

Use several independent flights, different microphones/cameras, motor and wind noise, silence, repeated beeps, unequal durations, shared audio only at one end, copied dates, and split FPV files. Include incorrect pairs with similar background sounds. Hold out some flights when tuning thresholds; do not adjust thresholds until every known example passes and then report those same examples as independent accuracy evidence.

## Within-recording sync

Open **Check timing across this recording**. Uncheck **Link playback** to scrub/play each source separately. Identify the same event near the start and end, enter both source times, and save the checkpoints. **Use current times** is convenient after independent scrubbing; copying linked playheads only repeats the current offset and supplies no independent evidence.

Two points can detect changing sync; three or more help spot a mistaken event. The display reports fitted drift and coverage. A 0.1-second estimated change across the shared interval prompts a drift warning. These are review aids, not a calibrated clock-error model. No video is stretched automatically. Check a shorter interval or independently amend the alignment before exporting. A warning must be acknowledged if exporting anyway.

## Export checks

Every export checks video timing against the requested interval with native-frame rounding. Fast trim preserves compressed packets and limits the MP4 presentation range with edit lists; editors must honor those lists. Accurate H.264/DNxHR trims preserve source cadence unless fixed-rate conversion is selected. Generated timecode tracks are disabled because the local FFmpeg build produced stretched durations with a demux-derived encoder time base.

Optional **Compare decoded start/middle/end frames** checks low-resolution cut frames against adjacent frames around the expected original source time. Results are stored in `alignment.json`. A consistent static scene does not prove exact timing or flight identity. These checks are slower and do not replace opening the exports in your editing application. Audio timing and the two sources' content alignment still need review.

## Automated checks

```bash
uv run --frozen python -m unittest discover -s tests -v
```

The 22 checks passed on 8 October. Fixtures are generated locally and contain no user videos. Checks cover audio positives/non-matches and known offsets, full overlap, clock tolerance/anchor independence/conflicts, drift, grouping, decisions across reruns, retaining better short audio samples, checkpoints, portable caches, JSON recovery and native-rate fast/accurate exports.

The 8 October Linux acceptance run also exercised actual HTTP APIs and the browser interface on an isolated app with generated 24fps StickCam and 30fps FPV clips. Two offsets (3.2 and 19.2 seconds) were identified, JSON/bundle transfers relinked successfully, and 32/16-second fast cuts passed timing and decoded sample checks. Resuming an interrupted export kept the first completed pair byte-for-byte unchanged and regenerated the incomplete second pair. This does not claim Windows/GPU/Resolve or large-batch acceptance.

## Initial real-flight baseline

Two matching identities already known from the user's session were labelled without claiming a measured offset. At 30 seconds per end, one passed the conservative Strong gates and one remained a possible candidate. At 120 seconds per end, neither passed those gates, although the estimated offsets stayed close to the shorter-sample estimates. More flight noise can weaken global trend checks; wider sampling is not automatically better. Adaptive search stops on a strong shorter sample and retains a pair's best sampled evidence during retries.

These are two positive examples with no independently measured timing labels or labelled real non-matches. They do not establish precision, timing accuracy or general reliability. The saved reference reports expose the misses and their reasons; conservative thresholds were not relaxed just to make the examples pass. A larger labelled collection remains necessary.
