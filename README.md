# PropNutz Flight Sync

An associated [PropNutz](https://www.propnutz.co.uk/) tool for FPV and StickCam audio pairing. The interface follows the site's warehouse style: charcoal, warm cream, red and blue accents, Barlow typography and the PropNutz wordmark. Branding assets are served locally so the app does not need an internet connection to display them.

A separate, smaller companion to FPV Radio Motion Pairing. Match FPV recordings to StickCam recordings using audio fingerprints, review their alignment, and export their common footage as two separate clips.

This project has its own folder, Python environment, port and data. It does not import the original project, share its sessions or change its service. There is no StickCam calibration, visual motion extraction, telemetry parser, Rust dependency or portrait editor.

The package and project folder remain named `fpv-audio-pairing`. Barlow and Barlow Condensed are bundled under the SIL Open Font License; copies of the licenses are in `fpv_audio_pairing/static/brand/`. The warehouse image and favicon come from the PropNutz site and are used for its associated tool.

## Documentation

- [Installation guide](docs/INSTALL.md): Windows, Linux and macOS setup, FFmpeg, LAN access, startup, updates and troubleshooting.
- [User guide](docs/USER_GUIDE.md): matching scopes, pair review, alignment, clock suggestions, exports and session backups.
- [Release notes](CHANGELOG.md): fixes and update history. Use v0.1.1 or later for the Windows frontend startup fix.
- [Client-only website investigation](docs/BROWSER_FEASIBILITY.md): local JSON/files, browser processing, large-video limits and the recommended separate browser edition.
- [Project plan](PROJECT_PLAN.md): implemented scope and remaining work.

The repository is public: [RDubzUK/propnutz-flight-sync](https://github.com/RDubzUK/propnutz-flight-sync). Anyone can clone it or download a release source ZIP. Videos, session data, caches and exports are excluded from Git.

## Quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and [FFmpeg/ffprobe](https://ffmpeg.org/download.html) first. uv can install the required Python 3.11 interpreter. No Rust toolchain, GPU or original project is required.

```bash
git clone https://github.com/RDubzUK/propnutz-flight-sync.git
cd propnutz-flight-sync
uv sync --frozen --python 3.11
uv run --frozen fpv-audio-pairing --host 127.0.0.1 --port 8768
```

Open **http://localhost:8768/**. For LAN access, change the host to `0.0.0.0` and open `http://<server-LAN-IP>:8768/` on another device. The CLI and `start.sh` default to LAN binding; the quick-start command above explicitly chooses local-only access. The original app uses port 8767.

The same `uv sync` and `uv run` commands work in Windows PowerShell, Linux shells and macOS Terminal. If Git is unavailable, download and extract the source ZIP, enter its directory, then run the final two commands. The committed `uv.lock` records dependency versions.

An optional Linux user service is provided in `deploy/fpv-audio-pairing.service`; edit its two paths to match your checkout before installing it. See the installation guide.

## Workflow

1. Name the session and browse to the FPV and StickCam folders. The StickCam browser starts at the FPV folder if none has been chosen yet. Mounted SMB shares are supported; paths refer to the server running the application.
2. The app scans recording durations, codecs, audio availability, file modification dates and filename camera timestamps. Each recording has an audio/fingerprint/modified-date status table, with its modification date and time shown beneath the filename. Files remain in their source folders.
3. Search all recordings, selected recordings on either side, or selected recordings on both sides. A 10%, 25% or 50% seed search samples one feed evenly while searching all candidates on the other feed. For a specific FPV clip, use the dedicated **Find StickCam counterpart** section: choose its filename and search against all audio-bearing StickCam recordings, with a ranked shortlist and progress in that section.
4. Audio matching reads the first and last 30 seconds by default, suppresses repetitive spectral hashes, and compares spectral landmarks plus audio trends at the same offset. Expand the sampled range to find useful sounds farther from the ends. Fingerprints persist across app restarts; source size, modified date, algorithm and sampling settings determine cache validity.
5. Review a candidate with both videos playing in sync throughout the full range where both have footage. Matching audio establishes the offset; its duration does not trim playback or exports. Green bands identify agreeing audio sections, with a button to jump to the first one. Adjust the offset in seconds or 0.05 second steps. A positive offset means an event occurs later in StickCam than in FPV. A manual pair can be opened when audio is missing or inconclusive.
6. Confirm an alignment, whether found by audio, dates or manual adjustment. Its modified-date difference, duration-adjusted camera clock and sync offset are logged, and other overlapping recordings are suggested, including multiple FPV parts for one StickCam video. Candidate rows also show when modified dates corroborate an audio alignment. Suggestions remain unconfirmed until reviewed.
7. Export the current confirmed pair or all confirmed pairs. Fast trim copies the original video/audio without re-encoding and keeps each source's frame cadence by default. Cuts between keyframes require editor support for MP4 edit lists. Accurate H.264 MP4 or DNxHR HQX MOV trimming is available, with original rates or an explicitly chosen constant-rate conversion. Optional trimming is relative to the common timeline. Output timing is inspected and recorded in the alignment manifest. Place both files at the same point in an editing timeline; confirm fast-cut playback in your editor.

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

Browser-compatible originals play directly with automatic buffering and HTTP range support. Other codecs use cached **4 second, 480p fragments near the playhead**, rather than creating a full 720p proxy before viewing. Playback reads up to six chunks ahead, including while temporarily paused to refill, and shows loading/buffering spinners on both feeds. StickCam audio is selected by default. **Preview acceleration: Auto** detects optional decoding support on the app host: NVIDIA CUDA, Linux VAAPI for Intel/AMD, Windows Direct3D 11 across vendors, or macOS VideoToolbox. Supported CUDA/VAAPI paths also resize on the GPU; preview encoding remains on the CPU. Unsupported drivers/clips fall back to CPU, and **CPU only** bypasses hardware attempts with a separate cache. Existing Auto chunks are reused. Preview generation is limited to two concurrent requests and its cache is pruned around 1 GiB. Browser H.264 Media Source support is required for fragment playback. Previews are 30fps; exports always read the originals and preserve source cadence by default.

Default app storage:

```text
data/sessions/<session-id>/session.json
data/sessions/<session-id>/audio/          # persisted fingerprints
data/sessions/<session-id>/previews/       # disposable browser fragments
data/exports/<session>_aligned_<time>/     # default output with readable names
data/export-index/<session-id>/           # export-location metadata only
```

**Output folder → Browse…** selects a destination on the app host, including mounted shares. Typed new folders are created when exporting, and the destination is remembered for the session. Each export uses a readable session/time folder; single-pair clips sit directly inside it, while batches use numbered FPV-name subfolders. Saved exports show their full location. Remote users can save through **Download ZIP** on their viewing PC. Older GUID-folder exports remain compatible.

**Deleting a session removes only its session document, fingerprints and previews. Source videos, export-location metadata and completed exports remain.** Saved exports can be downloaded even after their session is deleted, provided the output drive/share is available at the saved path. The ZIP download streams without writing a second copy of the export archive. Failed or cancelled exports can leave partial files at the chosen destination; these are not offered as completed downloads. Recursive source rescans exclude registered export folders.

Set `FPV_AUDIO_DATA_DIR` to use a different dedicated storage location. Keep it separate from the original app's data. Processing runs in a bounded background queue; tasks show progress, elapsed time and an estimate once work has started. Cancellation is immediate for exports and occurs between sections for audio decoding.

The server is intended for a trusted local machine/LAN. SMB authentication is handled by the operating system's mounted share, not stored by this application.
