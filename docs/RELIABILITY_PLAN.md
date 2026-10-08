# Local reliability milestone

The 8 October 2026 scope covers the local application only. The public browser edition is excluded.

1. Measure audio decisions against explicitly labelled matching/non-matching reference pairs. Record expected offsets, timing error, policy version and sample counts. Provide independent source-time checkpoints to check sync drift and optional decoded export-frame checks. Never turn an evidence score into a probability without measurements.
2. Persist reject, review-later and no-counterpart decisions; offer filters, a next-review action and completion counts. Preserve decisions across searches.
3. Retry unresolved audio searches at larger boundaries, reuse caches and show reasons. Keep date-derived confirmations separate from independently verified clock anchors. Preserve clock conflicts and detect within-recording sync drift.
4. Group FPV parts around a StickCam flight, order by the shared timeline, show gaps/overlaps/conflicting assignments and export confirmed parts together.
5. Save/open portable JSON projects or bundles containing fingerprints, retain source identities, relink recordings and provide automatic backup/recovery. Never bundle original videos or delete exports during recovery.
6. Provide cross-platform launchers, local diagnostics/support reports and resumable match/validation/export tasks. Reuse completed export parts only after checking their sources, alignment and output timing.

Acceptance includes automated known-answer checks and local API/browser checks. Actual Windows GPU behaviour and DaVinci Resolve acceptance require runs on those machines; no claim of that verification is made by local Linux checks.
