# PropNutz Flight Sync

An associated [PropNutz](https://www.propnutz.co.uk/) tool for FPV and StickCam audio pairing. The interface follows the site's warehouse style: charcoal, warm cream, red and blue accents, Barlow typography and the PropNutz wordmark. Branding assets are served locally so the app does not need an internet connection to display them.

A separate, smaller companion to FPV Radio Motion Pairing. Match FPV recordings to StickCam recordings using audio fingerprints, review their alignment, and export their common footage as two separate clips.

This project has its own folder, Python environment, port and data. It does not import the original project, share its sessions or change its service. There is no StickCam calibration, visual motion extraction, telemetry parser, Rust dependency or portrait editor.

The package and project folder remain named `fpv-audio-pairing`. Barlow and Barlow Condensed are bundled under the SIL Open Font License; copies of the licenses are in `fpv_audio_pairing/static/brand/`. The warehouse image and favicon come from the PropNutz site and are used for its associated tool.

## Run

Requires Python 3.11 or newer, [uv](https://docs.astral.sh/uv/) and FFmpeg/ffprobe on PATH.

```bash
cd /home/rdubz/vscode_projects/fpv-audio-pairing
./start.sh
```

Open **http://localhost:8768/**, or **http://192.168.0.114:8768/** from the LAN if the server still has that IP. The default bind is `0.0.0.0`. The original app retains port 8767.

Alternatively:

```bash
uv venv --python 3.11
uv pip install --python .venv/bin/python -e .
.venv/bin/python -m fpv_audio_pairing.web --host 0.0.0.0 --port 8768
```

Windows:

```powershell
uv venv --python 3.11
uv pip install --python .venv/Scripts/python.exe -e .
.venv/Scripts/python.exe -m fpv_audio_pairing.web --host 0.0.0.0 --port 8768
```

An optional independent user service is provided in `deploy/fpv-audio-pairing.service`.

## Workflow

1. Name the session and browse to the FPV and StickCam folders. The StickCam browser starts at the FPV folder if none has been chosen yet. Mounted SMB shares are supported; paths refer to the server running the application.
2. The app scans recording durations, codecs, audio availability and filename camera timestamps. Each recording has an audio/fingerprint/timestamp status table. Files remain in their source folders.
3. Search all recordings, selected recordings on either side, or selected recordings on both sides. A 10%, 25% or 50% seed search samples one feed evenly while searching all candidates on the other feed.
4. Audio matching reads the first and last 30 seconds by default, suppresses repetitive spectral hashes, and compares spectral landmarks plus audio trends at the same offset. Expand the sampled range to find useful sounds farther from the ends. Fingerprints persist across app restarts; source size, modified date, algorithm and sampling settings determine cache validity.
5. Review a candidate with both videos playing in sync. The shared range is shown for each source. Green bands identify agreeing audio sections. Adjust the offset in seconds or 0.05 second steps. A positive offset means an event occurs later in StickCam than in FPV. A manual pair can be opened when audio is missing or inconclusive.
6. Confirm an alignment. Its camera clock difference is logged, and other overlapping recordings are suggested, including multiple FPV parts for one StickCam video. Suggestions remain unconfirmed until reviewed.
7. Export the current confirmed pair or all confirmed pairs. Both outputs begin at zero, use the same frame rate and have exactly the same video frame count. Choose H.264 MP4 or DNxHR HQX MOV. Optional trimming is relative to their common timeline. Place both exported files at the same point in an editing timeline.

## What confidence means

Evidence scores are **not probabilities**. Strong audio candidates require distinctive spectral landmarks, a separate trend correlation at the same offset, several agreeing 3 second sections and separation from competing StickCam candidates. Possible and weak candidates are offered for review. Nothing is automatically confirmed. Duration similarity is never used to identify a flight.

Audio matching cannot reliably identify recordings containing only silence, repeated beeps, wind or unrelated/motor-dominated sound. Clock suggestions offer no new audio proof. Neither export frame counts nor matching filenames make an uncertain offset frame accurate.

## Camera clocks and split recordings

`offset = StickCam source time − FPV source time`.

The raw modified-date difference is retained. By default, file modification times are assumed to represent recording ends, so duration is subtracted to estimate the start clock. Change this to recording start when appropriate. Optional filename timestamps are assumed to describe recording starts. Incorrect camera dates, including 1970, can still supply relative ordering.

For a confirmed alignment:

```text
clock difference = StickCam start clock − FPV start clock + offset
predicted offset = clock difference + FPV start clock − StickCam start clock
```

Each predicted offset is intersected with both source durations to get a possible shared interval. There is no forced one-to-one assignment. A model from one flight is tentative; multiple independent confirmed flights can corroborate it. Clock differences disagreeing by more than two seconds disable suggestions for that clock. Repeated timestamps are excluded because copy operations and reset cameras can destroy ordering. Separate camera resets may require separate sessions.

## Playback and storage

Browser-compatible originals play directly. Other codecs use cached **4 second, 480p fragments near the playhead**, rather than creating a full 720p proxy before viewing. Preview generation is limited to two concurrent requests and its cache is pruned around 1 GiB. Browser H.264 Media Source support is required for fragment playback. Exports always read the original footage.

Default app storage:

```text
data/sessions/<session-id>/session.json
data/sessions/<session-id>/audio/          # persisted fingerprints
data/sessions/<session-id>/previews/       # disposable browser fragments
data/exports/<session-id>/<export-id>/     # aligned originals and manifest
```

**Deleting a session removes only its session document, fingerprints and previews. Source videos and completed exports remain.** Saved exports can be downloaded even after their session is deleted. The ZIP download streams without writing a second copy of the export archive. Failed or cancelled exports can leave partial files under `data/exports`; these are not offered as completed downloads.

Set `FPV_AUDIO_DATA_DIR` to use a different dedicated storage location. Keep it separate from the original app's data. Processing runs in a bounded background queue; tasks show progress, elapsed time and an estimate once work has started. Cancellation is immediate for exports and occurs between sections for audio decoding.

The server is intended for a trusted local machine/LAN. SMB authentication is handled by the operating system's mounted share, not stored by this application.
