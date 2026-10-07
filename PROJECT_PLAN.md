# Audio edition project plan

Public tool branding: **PropNutz Flight Sync**, associated with propnutz.co.uk. Keep the independent project and package names unchanged.

## Objective

A minimal end-to-end workflow from two source folders to reviewed audio matches and equal-length exports. Keep the original FPV Radio Motion Pairing project independent.

## Implemented scope

- Independent package, environment, local data and port 8768.
- Folder browsing, mounted shares, named sessions, rename/delete and folder rescan.
- Collapsible panels; creation panel hidden after choosing a session.
- Two video lists with durations and status tables for audio, saved fingerprints and filename timestamps.
- All/selected/seed matching scopes and cached boundary audio fingerprints.
- Dedicated Find StickCam counterpart workflow: one FPV recording against all audio-bearing StickCam recordings, with local progress, saved search summary and ranked review links.
- Distinctive spectral matching with independent, same-offset audio trend checks and repeated-section evidence.
- Several candidate StickCam owners per FPV clip, without forcing a one-to-one relationship.
- Synchronized two-video review, audio feed selection, slow playback and editable alignment.
- Saved audio trends with matching sections and a playback cursor.
- User-confirmed clock anchors, end/start modification date interpretation and optional filename timestamps.
- Timestamp suggestions for other clips and split FPV parts, with inconsistent/repeated clock handling.
- Manual alignment when audio is unavailable.
- Confirmed-pair exports of the common interval, optional trimming, equal frame counts and streamed ZIP download.
- Exports remain available after session deletion.

## Deliberate exclusions

No radio detection, gimbal calibration, stick tracking, gyro extraction, derived motion, stabilization or 9:16 composition. No source files or caches shared with the original app.

## Review criteria

The user reviews content evidence and shared playback before confirming an alignment. Timestamp suggestions are never presented as verified audio matches. Export timing depends on that reviewed alignment. Missing/unusable audio remains visible and supports manual alignment rather than an invented match.

## Possible later work

- A measured audio benchmark built from user-confirmed flights to tune confidence thresholds.
- Piecewise clock models for camera clock drift or mid-session clock resets.
- Resumable export jobs and finer per-encoder progress.
- Standalone desktop packaging if requested after the simpler workflow is established.
