# Installation and operation

## What this version runs

This is a local Python application with a web interface. Python, FFmpeg, your recordings and session JSON files live on the **machine running the app**. Another PC can view that app over a trusted LAN, but its browser does not perform processing or store the shared session data. Hosting this Python version on a public web server would put users' processing and data on that server.

Recommended initial setup: a desktop or laptop, Python 3.11 supplied by uv, and enough free space for aligned exports. Audio analysis does not require a GPU. Preview/export decoding and encoding are performed by FFmpeg. No Rust, radio calibration or telemetry parser is needed.

## 1. Install prerequisites

Install [uv using its official instructions](https://docs.astral.sh/uv/getting-started/installation/). Common options:

Windows PowerShell:

```powershell
winget install --id astral-sh.uv -e
```

macOS with Homebrew:

```bash
brew install uv ffmpeg
```

Linux/macOS official uv installer:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Ubuntu/Pop!_OS, install FFmpeg separately:

```bash
sudo apt update
sudo apt install ffmpeg
```

Windows: use one of the Windows builds linked by the [official FFmpeg download page](https://ffmpeg.org/download.html), extract it, and add the directory containing both `ffmpeg.exe` and `ffprobe.exe` to your user PATH. Restart PowerShell afterwards. The same page links macOS binaries if Homebrew is unavailable.

Confirm these commands can be found:

```text
uv --version
ffmpeg -version
ffprobe -version
```

Git is optional if you receive a source ZIP. To clone the private repository, your GitHub account must be granted access. Authenticate through Git or GitHub CLI; do not paste access tokens into source files or commands in a shared document.

## 2. Download the project

```bash
git clone https://github.com/RDubzUK/propnutz-flight-sync.git
cd propnutz-flight-sync
```

Alternatively, extract a source ZIP and open a terminal in the directory containing `pyproject.toml` and `uv.lock`. Keep this directory separate from `fpv-radio-motion-pairing`.

## 3. Install and launch

These commands work on Windows, Linux and macOS:

```bash
uv sync --frozen --python 3.11
uv run --frozen fpv-audio-pairing --host 127.0.0.1 --port 8768
```

uv creates a project-specific `.venv` and installs dependencies from `uv.lock`. First installation needs internet access; once installed, branding, processing and the app run locally. Open **http://localhost:8768/**. Keep the terminal open; press Ctrl+C to stop.

On Linux/macOS, `./start.sh --host 127.0.0.1` is an alternative launcher. Run `chmod +x start.sh` if a ZIP extraction lost its executable permission. The launcher's first-time pip install does not enforce `uv.lock`, so run `uv sync --frozen --python 3.11` first for the documented dependency versions.

## LAN access

```bash
uv run --frozen fpv-audio-pairing --host 0.0.0.0 --port 8768
```

Open `http://<server-LAN-IP>:8768/` on the other machine. On Windows, allow the app through the firewall for your private network if prompted. Folder selection shows files on the server running the app. Mount an SMB share there or, on a Windows server, use a mapped drive/UNC path.

This version has no user accounts or per-user access isolation. Use it on a trusted local network; the public PropNutz website requires the separate architecture discussed in the hosting investigation.

## Dedicated data folder

By default, data is saved under `data/` in the project. An optional dedicated folder can keep data outside the checkout:

PowerShell:

```powershell
$env:FPV_AUDIO_DATA_DIR = 'E:\PropNutzFlightSyncData'
uv run --frozen fpv-audio-pairing --host 127.0.0.1 --port 8768
```

Linux/macOS:

```bash
export FPV_AUDIO_DATA_DIR="$HOME/PropNutzFlightSyncData"
uv run --frozen fpv-audio-pairing --host 127.0.0.1 --port 8768
```

Choose a new folder, distinct from the original app's storage. Set the same value every time you start. If moving existing data, stop the app first and copy the entire old `data/` directory's contents to the new folder. Original videos remain in their source folders.

## Optional Linux user service

Copy `deploy/fpv-audio-pairing.service` to `~/.config/systemd/user/`, creating that directory if needed. Edit `WorkingDirectory` and `ExecStart` to match your checkout and its `.venv/bin/python`. The supplied file uses this machine's `~/vscode_projects/fpv-audio-pairing` path; a clone named `propnutz-flight-sync` needs that changed. Set `--host 127.0.0.1` in `ExecStart` for local-only use, or retain `0.0.0.0` for LAN access. Add `Environment=FPV_AUDIO_DATA_DIR=/absolute/data/path` if desired.

```bash
systemctl --user daemon-reload
systemctl --user enable --now fpv-audio-pairing.service
systemctl --user status fpv-audio-pairing.service
```

Stop: `systemctl --user stop fpv-audio-pairing.service`. Logs: `journalctl --user -u fpv-audio-pairing.service -n 50`.

## Updates and backups

Stop the app and back up `data/` before updating. For a Git checkout:

```bash
git pull --ff-only
uv sync --frozen --python 3.11
```

Restart using the command or service above. Repository tags preserve the pre-investigation snapshot and documented release. Source, `.venv` and data serve different purposes: source and `uv.lock` recreate the program; `data/` restores sessions, cached fingerprints and exports. Keep source videos separately too. Existing session files contain their original absolute paths, so moving to a different machine may require creating a new session using the new paths. JSON import/relink is not implemented in this local version.

## Troubleshooting

| Symptom | Action |
|---|---|
| `uv` not found | Reopen the terminal after installation; follow uv's PATH instructions. |
| Missing FFmpeg or ffprobe | Put both binaries on PATH and restart the terminal/service. |
| Port already in use | Stop the other Flight Sync instance or choose another `--port`. |
| Remote browser cannot connect | Check the server IP, `--host 0.0.0.0`, service status and private-network firewall. |
| Browse cannot open a folder | Check that it exists on the server and that its user can access the mounted share. |
| No recordings found | Choose folders with supported video files or tick Include subfolders. Recursive source folders must not contain one another. |
| Browser cannot play the original | Use 480p fragments on demand; current Chrome/Edge support the required H.264 Media Source playback. |
| Few or no audio candidates | Increase sampled audio from each end or align a known pair manually; audio presence is not evidence of useful sound. |
| Exports take time or fail for lack of disk space | They encode full-resolution originals. DNxHR is substantially larger; use H.264 or a shorter common interval. |
| A task says interrupted after restart | Run it again; saved fingerprints are reused. |

See the [user guide](USER_GUIDE.md) for the matching workflow and timing conventions.
