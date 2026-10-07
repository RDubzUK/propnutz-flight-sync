# Changelog

## Unreleased

- Add an export destination folder picker and typed paths, remembering the choice per session. Write single pairs directly into readable session/time folders and batches into numbered FPV-name subfolders; avoid overwriting earlier exports.
- Show full output paths, maintain an export index outside session data, and retain ZIP downloads/session-deletion behavior for custom destinations and older GUID-folder exports. Exclude registered outputs from recursive source rescans and remove successful encoding logs from completed clip folders.
- Place the audio display toggle and both saved audio fingerprint energy charts above Modified-date evidence in the pair preview.
- Show modified-date suggestions as an explicit evidence source in Pair Review and the single-FPV shortlist, alongside audio evidence. Include the predicted sync offset, agreement difference, tolerance, independent confirmed-flight count and expandable supporting pair filenames.
- Add a modified-date evidence panel beneath the selected pair's synchronized preview. Distinguish a date-based suggestion from independent agreement with an audio/manual alignment, and identify confirmed pairs as clock anchors rather than using them as evidence for themselves.
- Refresh derived date evidence on session load, including older saved confirmations, without rescanning audio, generating new pairs or changing saved offsets. Show conflicting/repeated dates as unavailable evidence, and hide old audio scores after their alignment evidence has been cleared.

## v0.3.0 — 7 October 2026

- Add fast MP4 stream-copy trimming without video/audio re-encoding, with explicit edit-list compatibility guidance and output timing checks. Preserve source frame cadence by default; retain accurate H.264/DNxHR trimming and optional fixed-rate conversion.
- Read preview chunks farther ahead, preserve read-ahead while paused for buffering, and cancel requests only after an actual seek rather than because a prefetched chunk is ahead of the playhead.
- Add refill/resume hysteresis, per-player loading/buffering spinners, original-video automatic preload and larger HTTP response chunks. Allow timestamp rounding/AAC priming at fragment boundaries.
- Detect optional preview hardware decoding on each app host: NVIDIA CUDA, Linux VAAPI for AMD/Intel, Windows Direct3D 11 across vendors and macOS VideoToolbox. Resize on the GPU where supported; fall back to CPU for unsupported drivers/clips. Add Auto/CPU controls with a separate CPU cache and show the fragment preparation method below each player.
- Default Pair Review's audio selector to StickCam.
- Use every reviewed confirmation as a modified-date anchor, including manual alignments and timestamp suggestions. Show the contributing pairs, annotate date agreement/disagreement on existing audio candidates and prefer date-supported candidates within their evidence tier. Keep duration-adjusted clock suggestions compatible with split FPV files; count independent flights rather than FPV parts. Check duplicate timestamps within each feed, rather than treating a date shared across both feeds as unreliable.
- Recompute pair review/export ranges from complete source durations and the saved sync offset when loading sessions, including older saved pairs. Audio evidence cannot override the shared-footage range.
- Show matching-audio seconds separately from full shared footage, with buttons to return to its start or jump to matching audio. Keep green bands limited to the observed audio evidence.
- Replace the Filename time indicator in Video lists & match scope with Modified date, using each recording's saved filesystem timestamp.
- Show the file's modification date and time beneath its filename in the browser's local time zone. Existing sessions do not need rescanning for this display.

These changes were code reviewed and FFmpeg option availability was inspected on the Linux host. Playback/export timing and hardware paths have not been exercised on real footage in this update, or verified on Windows/macOS and AMD/Intel machines.

## v0.2.0 — 7 October 2026

- Add a dedicated Find StickCam counterpart section with an FPV recording picker, audio sampling control, progress/cancel display and ranked StickCam candidates.
- Search exactly one FPV recording against all readable audio-bearing StickCam recordings, independently of the general matching scope and seed percentage.
- Reuse session fingerprints and preserve matches for other FPV recordings; save the last counterpart search in session JSON.
- Show confirmed matches and audio candidates alongside clearly labelled learned timestamp suggestions. Review opens the existing synchronized preview and export workflow.
- Show missing-audio/scan requirements and extraction failures explicitly.
- Report the installed package version through the system API.

## v0.1.2 — 7 October 2026

- Serialize session-list reads with background JSON saves, fixing an internal read/write race that can prevent replacing an open file on Windows.
- Retry atomic replacement for Windows errors 5, 32 and 33, with a bounded total delay of two seconds.
- Preserve the previous saved JSON and retain a complete pending JSON when replacement fails. Report the recovery path and writable-folder guidance instead of losing the pending save.
- Return readable session-save errors to the frontend and keep temporary-file cleanup errors from masking the original failure.
- Show a stopped task as failed even when its failure status cannot be saved; mark that status as unsaved and clear it after a successful restart of the task.
- Register a queued worker only after its initial job status has been saved.
- Serialize session deletion with the same storage lock.

Windows open handles can restrict rename/delete operations depending on their sharing flags. [Microsoft file-sharing documentation](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew). Code review identified the internal race; the exact cause of the reported access denial and the fix have not been verified on the user's Windows machine.

## v0.1.1 — 7 October 2026

- Serve JavaScript modules and CSS with explicit MIME types, independent of Windows registry file associations. This addresses a frontend startup failure that leaves Browse and Prepare session unresponsive.
- Revalidate script/style caches and explicitly identify the HTML response.
- Show frontend import/startup failures in the page and keep setup buttons disabled until their handlers are registered.
- Allow operation when the browser blocks localStorage. Remembering the selected session is optional; the server's saved session data is unaffected.
- Keep paired previews resumable when buffering or correcting timing. Deliberately interrupted play requests and requests from previous pairs do not stop the current review.
- Document Windows updates, the harmless uv hardlink fallback and startup troubleshooting.

The Windows-specific cause is inferred from the reported request log and the application's reliance on OS MIME mappings. This patch has not been exercised on a Windows machine by the maintainer in this session.

## v0.1.0 — 7 October 2026

Initial preserved release of the audio-only PropNutz Flight Sync app, including cross-platform installation and usage guides. The `snapshot-2026-10-07` tag retains the original source snapshot.
