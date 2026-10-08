# Audio edition project plan

Public tool branding: **PropNutz Flight Sync**, associated with propnutz.co.uk. Keep the independent project and package names unchanged.

## Objective

A minimal end-to-end workflow from two source folders to reviewed audio matches and equal-length exports. Keep the original FPV Radio Motion Pairing project independent.

## Implemented scope

- Simple interface by default, with the core matching/review/export workflow and automatic audio/export settings. Browser-local Expert preference exposes technical controls without changing session data.
- Selected-StickCam split-flight timeline and synchronized preview, including StickCam-only gaps and conflicting alternatives. Prevent overlapping split-part confirmations/group exports; retain original offsets for correction.

- Independent package, environment, local data and port 8768.
- Folder browsing, mounted shares, named sessions, rename/delete and folder rescan.
- Collapsible panels; creation panel hidden after choosing a session.
- Two video lists with durations, modification dates and status tables for audio, saved fingerprints and modified-date availability.
- All/selected/seed matching scopes and cached boundary audio fingerprints.
- Dedicated Find StickCam counterpart workflow: one FPV recording against all audio-bearing StickCam recordings, with local progress, saved search summary and ranked review links.
- Distinctive spectral matching with independent, same-offset audio trend checks and repeated-section evidence.
- Several candidate StickCam owners per FPV clip, without forcing a one-to-one relationship.
- Synchronized two-video review throughout the full shared footage, independent of audio-evidence length; audio feed selection, slow playback, editable alignment and a jump to matching audio.
- Saved audio trends with matching sections and a playback cursor.
- User-confirmed clock anchors, end/start modification date interpretation and optional filename timestamps.
- Timestamp suggestions for other clips and split FPV parts, with inconsistent/repeated clock handling.
- Show modified-date corroboration on audio/manual candidates, contributing independently verified anchors and independent-flight counts. Date-only confirmations require a separate content check before teaching the clock; date signals never confirm a match automatically.
- Include modified dates explicitly in Pair Review evidence and the selected preview, with predicted offsets, tolerance, contributing pair filenames and refresh of older session evidence on load.
- Manual alignment when audio is unavailable.
- Confirmed-pair exports of the common interval: fast stream-copy cuts with edit lists, accurate trimming, original source cadence by default, optional fixed-rate conversion, measured timing and streamed ZIP download.
- Preview read-ahead, refill/resume control, per-player buffering indicators and StickCam audio by default.
- Detect optional GPU preview decoding on each app host (CUDA, Linux VAAPI, Windows Direct3D 11, macOS VideoToolbox), with GPU resizing where supported, cached-chunk reuse, CPU fallback and a CPU-only override.
- Exports remain available after session deletion.
- Select/remember export destinations on the app host, with readable session/time and clip folders, full saved paths, preserved legacy downloads and an independent location index. Exclude generated outputs from recursive source scanning.

## Deliberate exclusions

No radio detection, gimbal calibration, stick tracking, gyro extraction, derived motion, stabilization or 9:16 composition. No source files or caches shared with the original app.

## Review criteria

The user reviews content evidence and shared playback before confirming an alignment. Timestamp suggestions are never presented as verified audio matches. Export timing depends on that reviewed alignment. Missing/unusable audio remains visible and supports manual alignment rather than an invented match.

## Local reliability milestone (0.4.0)

- Durable reject/review-later/no-counterpart decisions, review filters, next-candidate navigation and completion counts.
- Adaptive 30/60/120/300-second boundary retries for unresolved audio, cached per-recording comparisons and restart/cancel resume.
- Modified-date agreement defaults to ±5 seconds, configurable from 1–10 seconds through the API (UI offers 2/5/10). Filename agreement remains ±2 seconds. Dates never invalidate a content match.
- Independently entered source-event checkpoints, individual playback and constant-offset/drift warnings. Exports with conflicting checkpoints require explicit acknowledgement; no automatic speed changes.
- Label matching/non-matching reference pairs, optionally record a measured offset, run the current policy against those known answers, and download a measured report. Identity-only labels do not establish timing accuracy.
- Group split FPV parts on the StickCam timeline, show confirmed gaps/overlaps/conflicting owners, export flight parts together and include a flight manifest.
- Save/open JSON or bounded fingerprint bundles, stable recording IDs, content-assisted relinking and retained original camera dates.
- Ten automatic metadata backups, explicit recovery, preserved pre-restore JSON, and an instance lock for the app's data folder.
- Resume completed export pairs after checking their timing/inputs, per-source FFmpeg progress, optional decoded start/middle/end cut comparisons.
- Bounded MP4 edit-list presentation ends; disable generated timecode tracks that distort durations on the local FFmpeg build.
- Locked cross-platform launchers, a Windows prerequisite setup script, local diagnostics and path-redacted support reports.

See [the milestone scope](docs/RELIABILITY_PLAN.md) and [validation guide](docs/VALIDATION.md).

## Remaining empirical work

- Build a larger, independently labelled real-flight collection to measure errors before tuning confidence thresholds. A known same-flight pair can still fail the conservative Strong gates; report it as a missed match.
- Actual Windows/macOS, GPU driver, 10–40-flight performance and DaVinci Resolve acceptance must be measured on those machines. Local generated fixtures do not establish those results.
- Mid-session camera resets may require separate sessions; segmented clock models are not implemented.
- The public browser-only PropNutz edition is excluded from this milestone.
