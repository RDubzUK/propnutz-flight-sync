# Desktop third-party components

The desktop distribution includes Electron, a frozen Python backend, and separate
FFmpeg/FFprobe executables. Their licenses apply independently. This document does
not assign a license to PropNutz Flight Sync.

## FFmpeg and FFprobe

The build uses the pinned `ffmpeg-static` and `@derhuerst/ffprobe-static` npm
packages from [eugeneware/ffmpeg-static](https://github.com/eugeneware/ffmpeg-static).
These packages identify their wrapper license as `GPL-3.0-or-later`. The license
and configuration of each native binary are recorded in the files supplied with
that binary; consult those files when redistributing it.

The installed application's `resources/media` directory contains:

- `ffmpeg` and `ffprobe` (`.exe` on Windows), with each original `.README` and
  `.LICENSE` sidecar supplied by the binary distributor.
- `ffmpeg-package/` and `ffprobe-package/`, containing each npm package's original
  `LICENSE`, `README.md`, and `package.json`.
- `ffmpeg.version.txt` and `ffprobe.version.txt` (`.exe.version.txt` on Windows),
  containing the actual binary's version and build configuration output.
- `manifest.json`, identifying the platform, architecture, npm package versions,
  declared upstream binary release, and actual FFmpeg/FFprobe versions.

On macOS these resources are inside `PropNutz Flight Sync.app/Contents/Resources`.
The build fails if a binary or its required notices are missing. It also rejects
binaries for another platform/architecture and FFmpeg builds without the
`libx264`, `aac`, and `dnxhd` encoders used by the application.

The upstream package's [binary build script](https://github.com/eugeneware/ffmpeg-static/blob/master/download-binaries/index.sh)
records the distributor locations and notice extraction. The package's
[source notes](https://github.com/eugeneware/ffmpeg-static#sources-of-the-binaries)
identify Windows builds from [Gyan](https://www.gyan.dev/ffmpeg/builds/), Linux
builds from [John Van Sickle](https://johnvansickle.com/ffmpeg/), and macOS builds
from [evermeet.cx](https://evermeet.cx/ffmpeg/) or [OSX Experts](https://osxexperts.net/).
Use the bundled version output and binary README to identify the exact build;
the npm package version alone does not establish the native FFmpeg version.

FFmpeg's own [license and redistribution information](https://ffmpeg.org/legal.html)
and [source downloads](https://ffmpeg.org/download.html) describe its upstream
licensing. Distributors must satisfy the applicable binary's license, including
any corresponding-source obligations; this notice is not a source-code offer.

## Electron, Python, and application assets

Electron's distribution includes its `LICENSE` and `LICENSES.chromium.html`
notices, which are retained by electron-builder. See
[Electron's license](https://github.com/electron/electron/blob/main/LICENSE).
The frozen backend contains Python and the dependencies resolved in `uv.lock`;
see that lockfile and the packages' included metadata for exact versions.
[Python's license](https://docs.python.org/3/license.html) and
[PyInstaller's license and bootloader exception](https://pyinstaller.org/en/stable/license.html)
describe those components' terms.

The bundled web assets retain their existing notices under
`backend/_internal/fpv_audio_pairing/static/brand`, including the Barlow and
Barlow Condensed font licenses. See that directory's `README.md` for asset
attribution.
