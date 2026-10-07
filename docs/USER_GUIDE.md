# Using PropNutz Flight Sync

## 1. Create a session

Give the session a useful name, then choose separate FPV and StickCam folders. **Browse** navigates the machine running the app. The StickCam browser starts at the chosen FPV folder when its own path is blank. Choose **Use this folder** above the file list. Mounted network shares work if the server user can access them.

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
- **Seed recordings** at 10%, 25% or 50% samples one feed evenly and retains the search candidates on the other. It reduces the initial search; it does not automatically confirm the unprocessed files.

## 3. Find matching flights

Start with **30 seconds from each end**. This is designed for shared sound around takeoff/landing; most flight audio may differ substantially between camera locations. Expand to 60 seconds, two minutes or five minutes when useful sounds fall farther from the boundaries. A short recording's audio is read as one interval.

Matching caches extracted audio fingerprints and reuses them on subsequent searches. Changed files or extraction settings have separate cache entries. The progress display is inside **Find matching flights**, with elapsed time, estimated remaining time and cancellation. Cancellation can wait for the current audio section to finish decoding.

The shortlist combines spectral landmarks and independent audio trends at one proposed offset. A strong label requires several independent agreeing sections and separation from competing candidates. **Evidence scores are not percentages of certainty.** No candidate is automatically confirmed.

### Find a StickCam counterpart for one FPV recording

Use the dedicated **Find StickCam counterpart** section between matching and pair review:

1. Choose the FPV recording by filename; its duration and audio availability are shown.
2. Choose how much audio to sample from each end, starting at 30 seconds.
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

Once playback looks aligned, choose **Confirm this pair & suggest others**. Every confirmed pair contributes, including audio matches, reviewed timestamp suggestions and manually aligned pairs. The app logs the raw modified-date difference and derives a camera start-clock difference using duration and offset, then immediately suggests other overlapping recordings and split FPV parts without analyzing their audio again.

- Modification dates normally represent recording ends; select recording start when your files behave that way.
- Optional filename timestamps are treated as recording starts.
- One confirmed flight gives a tentative clock model. Independent confirmed flights can corroborate it.
- Conflicting confirmed clocks or repeated/reset timestamps are reported and excluded where appropriate.
- A timestamp candidate is a **suggestion**, not an audio-confirmed match. Review it too.

The clock panel lists the confirmed pairs used and their raw date differences. **Evidence** in Pair Review and the counterpart shortlist shows modified dates separately from audio. Date-based proposals are labelled **Modified-date suggestion**. An audio/manual candidate shows **Modified dates agree** when its sync offset is within two seconds of the learned clock prediction, or **Modified dates disagree** otherwise. Each row includes the predicted offset, difference, tolerance and number of independent confirmed flights. Expand **Confirmed pairs used** to see the supporting filenames and confirmed offsets.

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

This version does not yet import/download a session JSON from the interface or store sessions in remote clients' browsers. Those capabilities belong to the planned client-only version.
