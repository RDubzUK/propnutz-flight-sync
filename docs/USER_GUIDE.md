# Using PropNutz Flight Sync

## Simple and Expert interfaces

**Simple** is the default. The selector at the top remembers your choice in this browser. Use sessions/source folders, video lists, Find matching flights, Find StickCam counterpart, Pair Review and Aligned exports. The leading candidate for each FPV clip is shown in Pair Review; the counterpart section can show alternative StickCam matches.

Simple uses 30-second audio samples, automatic retries up to two minutes per end, all files in the selected scope, and the session's saved camera-date interpretation. Review both sources and choose **Confirm reviewed pair & suggest others**. This confirmation records that you checked the content. Exports use the full shared footage, stream copy and original frame rates. Hidden Expert trim/rate settings do not affect Simple exports.

**Expert** exposes audio sampling/settings, detailed evidence and waveforms, manual offsets, timing checkpoints, project transfer/recovery, accuracy reports, diagnostics and split-flight review. Switching interfaces does not discard saved data. If a session needs recovery, Simple provides a button to open the required Expert tools.

The detailed instructions below include Expert controls. In Simple, leave matching and export settings to the app; switch to Expert when you need to adjust them. Simple previews use automatic codec/acceleration selection and normal playback speed.

In **Flights & split recordings**, choose one StickCam recording from the dropdown. Its complete timeline shows a proposed sequence of FPV parts with no overlaps. Preview a part or seek on the timeline: both videos play at the saved offset, and gaps show only StickCam. **Review & confirm this part** opens Pair Review for alignment changes and confirmation. Conflicting alternatives remain listed for inspection; no saved offsets are shifted to fit them. New confirmations and grouped exports reject overlapping parts of the same StickCam flight, allowing one frame of source timestamp rounding at joins.

## 1. Create a session

Give the session a useful name, then choose separate FPV and StickCam folders. **Browse** navigates the machine running the app. The StickCam browser starts at the chosen FPV folder when its own path is blank. Choose **Use this folder** above the file list. Mounted network shares work if the server user can access them.

Saved session cards show a cached FPV image in both Simple and Expert. The app chooses an FPV recording near the session's average modified date and takes a frame at about 90 seconds, or earlier for shorter clips. Only a still image is decoded; no full-video preview conversion is needed.

Enable **Include subfolders** when required. Prepare the session and allow metadata scanning to finish. Session creation then folds away; use **New session** for another set of recordings. Existing sessions can be renamed or rescanned.

## 2. Inspect recordings and choose scope

The two file lists show filenames, durations, resolution, frame rate and three indicators:

| Indicator | Meaning |
|---|---|
| Audio track | FFprobe found an audio stream. This can still be silence or motor noise. |
| Fingerprints | Usable sampled audio features are saved in this session. |
| Modified date | The file's modification timestamp was captured from the filesystem. Its date and time appear beneath the filename in your browser's local time zone. |

Green tick means available; red cross means absent/unusable; dash means not yet scanned or prepared.

- **All videos** searches the entire session.
- **Selected videos**, selecting only FPV clips, searches those against all audio-bearing StickCam clips.
- Selecting only StickCam clips searches those against all audio-bearing FPV clips.
- Selecting both sides compares only those selected subsets.
- In Expert, **Seed recordings** at 10%, 25% or 50% samples one feed evenly and retains the search candidates on the other. It reduces the initial search; it does not automatically confirm the unprocessed files.

## 3. Find matching flights

Start with **30 seconds from each end**. This is designed for shared sound around takeoff/landing; most flight audio may differ substantially between camera locations. Expand to 60 seconds, two minutes or five minutes when useful sounds fall farther from the boundaries. A short recording's audio is read as one interval.

Matching caches extracted audio fingerprints and reuses them on subsequent searches. Changed files or extraction settings have separate cache entries. The progress display is inside **Find matching flights**, with elapsed time, estimated remaining time and cancellation. Cancellation can wait for the current audio section to finish decoding.

The shortlist combines spectral landmarks and independent audio trends at one proposed offset. A strong label requires several independent agreeing sections and separation from competing candidates. **Evidence scores are not percentages of certainty.** No candidate is automatically confirmed.

### Find a StickCam counterpart for one FPV recording

Use the dedicated **Find StickCam counterpart** section between matching and pair review:

1. Choose the FPV recording by filename; its duration and audio availability are shown.
2. Simple chooses the audio sample size automatically. In Expert, choose how much audio to sample from each end, starting at 30 seconds.
3. Click **Find StickCam counterpart**. It searches only that FPV clip against all readable audio-bearing StickCam recordings, regardless of list selections or the seed percentage in the general matcher.
4. Follow progress and cancellation in this section. Saved fingerprints are reused.
5. Review the ranked StickCam candidates. Confirmed pairs appear first, then audio candidates; existing learned timestamp suggestions remain clearly labelled.
6. Click **Review** to scroll to the synchronized preview, adjust the offset if needed and confirm the pair. Exports use the normal aligned-export section.

The most recent counterpart search is saved with the session. Searching one FPV recording preserves matches for other FPV recordings. If no useful audio match is found, increase the sampled range. A clip without an audio track cannot be searched by audio; existing clock suggestions and manual alignment remain available. A candidate is never confirmed automatically.

## 4. Review the pair

Click **Review** to scroll to the synchronized players. Use **Play together**, pause, shared seek, slow playback and the audio selector. The players show the original timestamps and stay within the shared footage interval.

The timeline covers **all footage available from both sources at the saved sync offset**, including before and after matching audio. Ten seconds of matching audio can anchor several minutes of shared video. Each pair's range is recomputed from the full video durations when the session is loaded; sampled audio and green evidence bands never trim this range. The same full range is available for export unless you explicitly trim it.

**Start of shared footage** returns to the earliest point present in both recordings. **Jump to matching audio** goes to the first green evidence section so you can check synchronization, then seek or play anywhere in the full shared range. The review shows matching-audio seconds separately from the full shared-footage length. If the offset itself places one recording near its end, only the remaining footage can overlap; adjusting the reviewed offset recalculates the range.

Browser-compatible originals play directly. If a camera codec cannot be played, choose **480p fragments on demand**. Only short fragments near the playhead are generated, while exports retain source resolution.

StickCam is the default **Listen to** feed. Each player shows a spinner while loading, seeking or buffering; a ready player can show that it is waiting for the other feed. Short previews read up to 24 seconds ahead during playback and retain that intent while temporarily paused to buffer. Both feeds refill before resuming together. Encoding/reading slower than real time can still cause buffering.

**Preview acceleration** defaults to **Auto**, detecting the machine running the app rather than the PC viewing it. Available backends include NVIDIA CUDA, Linux VAAPI (Intel/AMD), Windows Direct3D 11 (across vendors) and macOS VideoToolbox. GPU decoding requires a compatible driver, FFmpeg build and source codec. CUDA/VAAPI can also resize on the GPU; preview H.264 encoding stays on the CPU. Failed hardware attempts fall back to CPU and are not repeatedly retried for the same source format until the app restarts. Hardware acceleration is optional and its speed depends on the machine and footage.

Choose **CPU only** if a GPU driver causes trouble. This uses a separate fragment cache, avoiding reuse of fragments created in Auto mode. The label below each player shows Original video, CPU preview or the GPU backend that prepared its last fragment. Cached Auto fragments can have been prepared on another machine and are still reused. This setting controls server fragment preparation; browser decoding of originals is managed by the browser.

Saved audio energy trends are shown below the players. Green bands show sampled sections that agree at the proposed offset; gaps are unsampled audio. This is an energy trend display, not a full-recording waveform.

### Adjust alignment

The convention is:

```text
offset = StickCam timestamp − FPV timestamp for the same event
```

If an event is at FPV `00:20` and StickCam `00:42`, use offset `+22` seconds. The common footage starts at FPV `00:00` and StickCam `00:22` in that example. The common end is whichever recording runs out first.

Use the offset field or ±0.05 second buttons, apply the adjustment and replay. An adjustment clears confirmation. For missing/unhelpful audio, expand **Choose a pair manually**, select one video of each type and set an initial offset.

## 5. Confirm and suggest the rest

Once playback looks aligned, choose **Confirm this pair & suggest others**. Every independently verified pair contributes, including audio matches and manually aligned pairs. A timestamp suggestion requires the explicit independent-content checkbox before it becomes a new anchor. The app logs the raw modified-date difference and derives a camera start-clock difference using duration and offset, then immediately suggests other overlapping recordings and split FPV parts without analyzing their audio again.

- Modification dates normally represent recording ends; select recording start when your files behave that way.
- Optional filename timestamps are treated as recording starts.
- One confirmed flight gives a tentative clock model. Independent confirmed flights can corroborate it.
- Conflicting confirmed clocks or repeated/reset timestamps are reported and excluded where appropriate.
- A timestamp candidate is a **suggestion**, not an audio-confirmed match. Review it too.

The clock panel lists the confirmed pairs used and their raw date differences. **Evidence** in Pair Review and the counterpart shortlist shows modified dates separately from audio. Date-based proposals are labelled **Modified-date suggestion**. An audio/manual candidate shows **Modified dates agree** when its sync offset is within the configured tolerance (five seconds by default) of the learned clock prediction, or **Modified dates disagree** otherwise. Each row includes the predicted offset, difference, tolerance and number of independent confirmed flights. Expand **Confirmed pairs used** to see the supporting filenames and confirmed offsets.

The same information appears in a **Modified-date evidence** panel beneath the selected pair's preview. A confirmed pair is shown as a clock anchor; it is not counted as evidence for its own alignment. Conflicting clock anchors and repeated dates are explicitly identified as unusable evidence. Existing saved confirmations receive current date evidence when the session loads, without another audio search, rescan or offset change.

Within the same evidence tier, date-supported candidates appear first. If dates predict a different offset, that difference is shown without overwriting the audio/manual alignment or score. One confirmed flight remains tentative; multiple FPV parts of the same StickCam flight do not count as independent flights. Matching date signals do not automatically confirm a pair.

Several FPV files can relate to one StickCam recording, including split DJI/O4 recordings. Each part gets its own overlapping interval and can be confirmed/exported separately. Different video lengths do not count against a content match.

## 6. Export common footage

In **Aligned exports**, choose the current confirmed pair or all confirmed pairs. **Fast trim** and **Original frame rates** are the defaults:

Use **Output folder → Browse…** to choose where the clips are written, including a mounted network share. You can also type a new folder path; missing folders are created when exporting. The destination is on the **machine running Flight Sync**. It is remembered for the session after an export starts. When using another PC over the LAN, **Download ZIP** saves through that PC's browser instead.

Each export creates a new readable folder, for example `Node Court_aligned_2026-10-07_21-15-00`. A single pair's FPV clip, StickCam clip and `alignment.json` sit directly inside it. Multiple pairs get numbered subfolders named after their FPV clips. Existing folders/files are not overwritten. Leave Output folder blank to use readable folders under the app's `data/exports/`. Completed rows show the full **Saved to** path, which you can select/copy. Session-data folders cannot be chosen as destinations because session deletion removes them.

- **Fast trim · no re-encoding** copies video/audio into MP4, retaining original codecs, resolution and frame cadence. It is generally limited by storage speed. Cuts between keyframes retain decoding preroll and use MP4 edit lists to hide it. An editor must honor those edit lists; if it exposes extra frames or the cut fails timing checks, choose Accurate trim. The app does not silently fall back to a slow re-encode.
- **Accurate trim · H.264 MP4** decodes and re-encodes the requested interval for a broadly compatible cut.
- **Accurate trim · DNxHR HQX MOV** re-encodes to larger editing files.

**Original frame rates** keeps each source's timing cadence, including fractional rates. Two sources can therefore have different frame counts. Accurate trim also offers an explicit constant-rate conversion; choosing 24/25/30/50/60fps resamples both sources to that rate and can drop/duplicate frames. Fast trim always preserves original rates.

Optional trim values are measured from the beginning of the common interval. Leave the end blank for full overlap; when exporting all pairs, each uses its own common end. An explicit end must fit inside every selected pair.

Outputs use the same requested shared interval and a common zero-time origin. Native frame/packet boundaries can round the starts/ends by a small amount; frame counts need not be equal. Completed outputs are inspected for duration/start timing, with an opening-packet presentation-time check for fast cuts, avoiding a full video decode. The included `alignment.json` records the requested interval, offset and measured output timing. Fixed-rate accurate exports retain the equal-frame-count check.

Download the ZIP and place both clips at the same timeline position in DaVinci Resolve or another editor. Verify a fast cut in your editor because edit-list support is essential. Output timing checks do not correct an inaccurate match or guarantee every editor's behavior. See [FFmpeg seeking](https://ffmpeg.org/ffmpeg.html#Main-options) and [MP4 edit-list options](https://ffmpeg.org/ffmpeg-formats.html#mov_002c-mp4_002c-ismv).

The ZIP streams directly during download. Outputs are retained at the chosen destination, and **Saved exports** lists completed downloads even if the session has been deleted. A small export index stays in app data; moving the output folder or disconnecting its drive/share makes the download unavailable until that path is restored. Older exports in GUID folders retain their download links. Recursive source rescans skip registered export folders, including incomplete outputs, to avoid importing generated clips as source recordings.

## Session data and backup

The current local version stores `session.json`, audio caches and preview fragments under `data/sessions/` on the app server. Export locations are indexed under `data/export-index/`; aligned outputs are written to your chosen folder, or readable folders under `data/exports/` by default. Originals remain in their source folders. Stop processing and back up app data, chosen export folders and original recordings to preserve work.

**Delete session data** removes that session's JSON and caches, keeping original recordings and completed exports. Deletion cannot be reversed in the app; restore a local backup to recover a session. If a job is running, cancel it and wait until it stops before deletion.

Portable project JSON and optional fingerprint bundles can be saved/opened in Sessions. Processing and the active session still live on the app host; a remote client's browser does not become its data store.

## Review queue and flight groups

Use **Show pairs** to switch between awaiting review, all pairs, strong audio, confirmed, later or rejected. **Review next** opens the next available candidate. **Reject pair** and **Review later** persist across matching runs. Return a rejected/later pair to the queue when you want to reconsider it. In the unmatched list, **Mark no counterpart** dismisses that recording's current candidates and excludes it from ordinary all-video searches; **Allow searches again** restores its eligibility. Explicitly selecting it also allows a fresh search.

The summary counts FPV parts, not independent flights. Unsearched means no completed attempt yet; unmatched means searched without an available candidate or explicitly marked no counterpart. Missing/error recordings are shown separately. **Flights & split recordings** groups parts under a StickCam file, orders them by their StickCam times and shows gaps/overlaps between confirmed parts. Conflicting confirmed StickCam owners remain visible. **Export confirmed flight parts** uses the export settings below; no files are concatenated and original frame rates stay independent. `flights.json` records each part's placement.

## Audio retry and date tolerance

Automatic retries start with your chosen boundary and expand unresolved FPV searches through 60/120/300 seconds as allowed by **Maximum audio per end**. Strong content candidates stop further expansion for that FPV clip. Each pair retains its best sampled evidence if a wider range contains more noise. All possible StickCam owners remain searchable; dates do not prune audio candidates. Disable retries for a bounded short scan. Per-recording outcomes explain unresolved evidence. Both fingerprints and completed comparison rounds can be resumed after cancellation/restart.

Modified-date evidence defaults to **±5 seconds** (choose 2/5/10 in the UI); filename clocks remain ±2 seconds. This is clock evidence tolerance, not audio synchronization tolerance. A date disagreement never downgrades an audio match. Date-only confirmations do not teach new clock anchors until **I checked the content independently** is selected and the pair is confirmed again. Previously confirmed audio/manual pairs retain their anchor meaning.

## Save, open, relink and recover

In Sessions, **Save project JSON** downloads the session document. **Save project + fingerprints** adds audio caches, not originals or disposable previews. Open either on another installation with **Open project**; it creates a new session and leaves existing sessions untouched. Open **Relink recordings & recover session data**, choose the source folders and relink. Original recording IDs, reviewed offsets, stored camera dates and labels are preserved for recognized files.

Relinking checks relative/name/size candidates plus a bounded head/tail fingerprint where available. This is not a whole-file integrity proof. Identical names in several folders remain unresolved. Legacy recordings without a saved content identity can need another review. A copied file's new modification date does not overwrite the saved camera date used by that project. Imported audio caches are validated before reuse; moving files does not require decoding them again when a compatible identity cache is available.

Ten automatic metadata backups are kept under the session folder, no more than once a minute for ordinary progress writes, with extra snapshots before important review/relink changes. **Show backups → Restore selected backup** restores metadata only; the current JSON is kept separately. Existing exports are preserved through the independent export index. Deleting a session also deletes its internal backups; save a portable project first if you want to retain its review decisions.

## Resume and accuracy checks

**Resume saved task** appears for interrupted, failed or cancelled tasks. Search reuses durable completed recording comparisons. Export checks completed pairs against the original source signatures/alignment and their output timing, then reuses them; an incomplete pair is regenerated. A changed alignment requires a new export. FFmpeg processing displays per-source progress where available.

Known answers, timing checkpoints, individual playback, measured reference reports and optional decoded export samples are explained in [Accuracy validation](VALIDATION.md). These controls supply evidence and recovery; they do not automatically certify a recording or stretch footage.
