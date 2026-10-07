# Changelog

## Unreleased

- Replace the Filename time indicator in Video lists & match scope with Modified date, using each recording's saved filesystem timestamp.
- Show the file's modification date and time beneath its filename in the browser's local time zone. Existing sessions do not need rescanning for this display.

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
