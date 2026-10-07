# Changelog

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
