# Desktop app

PropNutz Flight Sync packages the existing interface in an Electron window with a bundled Python backend, FFmpeg and ffprobe. Installers do not require a separate Python, Node.js, uv or FFmpeg installation. Processing stays on your computer; source videos stay in the folders you select.

## Install

Download an installer from [GitHub Releases](https://github.com/S33G/propnutz-flight-sync/releases), once a desktop release has been published. Choose a release asset rather than GitHub's automatically generated source-code archives.

| Computer | Download | Installation |
|---|---|---|
| Windows x64 | `.exe` | Run the NSIS installer, then open PropNutz Flight Sync. |
| Linux x64 | `.AppImage` | Mark the file executable (`chmod +x <filename>.AppImage`), then run it. |
| Debian/Ubuntu x64 | `.deb` | Install with `sudo apt install ./<filename>.deb`. |
| Intel Mac | `x64.dmg` or `x64.zip` | Open the DMG and drag the app to Applications, or extract the ZIP. |
| Apple Silicon Mac | `arm64.dmg` or `arm64.zip` | Open the DMG and drag the app to Applications, or extract the ZIP. |

The filenames include the app version, operating system and architecture. Linux x64 downloads use the names `x86_64.AppImage` and `amd64.deb`; both are for Intel/AMD 64-bit computers. Windows and Linux ARM builds are not included. Linux builds target Ubuntu 22.04 or newer compatible distributions; AppImage may require the distribution's FUSE compatibility package, while `.deb` installs system dependencies through apt.

Initial Windows installers are unsigned. macOS apps use ad-hoc signing, which does not identify a verified developer, and are not notarized. Windows SmartScreen or macOS Gatekeeper can therefore prompt or block first launch. Only open builds you trust; macOS's **System Settings → Privacy & Security → Open Anyway** may be available after an attempted launch, as described in [Apple's instructions](https://support.apple.com/en-gb/102445). Do not disable operating-system protections globally. A managed computer may require approval from its administrator.

Published releases include `SHA256SUMS`. On Linux, place it beside the downloaded assets and use `sha256sum --check --ignore-missing SHA256SUMS`. On macOS, calculate `shasum -a 256 <filename>`; on Windows, use `Get-FileHash <filename> -Algorithm SHA256`. Compare the result with the corresponding entry in `SHA256SUMS`.

## Data, updates and existing projects

Desktop data is stored in a `data` subdirectory of Electron's per-user application-data folder:

| System | Default data folder |
|---|---|
| Windows | `%APPDATA%\PropNutz Flight Sync\data` |
| macOS | `~/Library/Application Support/PropNutz Flight Sync/data` |
| Linux | `${XDG_CONFIG_HOME:-~/.config}/PropNutz Flight Sync/data` |

`FPV_AUDIO_DATA_DIR`, when set in the app's launch environment, overrides this location. Choose a dedicated writable folder. Back it up while the app is closed, along with source recordings and any separately chosen export folders. Installing a newer app replaces the program; it does not migrate data from an existing source checkout. Updates are installed manually from GitHub Releases.

To bring existing work into the desktop app, use **Save project JSON** or **Save project + fingerprints** in the source version, then **Open project** in the desktop app and relink its recording folders. Project bundles do not contain the original recordings. See the [user guide](USER_GUIDE.md) for project transfer and recovery.

The desktop app starts its backend on an automatically chosen loopback port and limits access to its own session. It reuses that port on later launches to retain browser preferences. If another program takes the port, it selects a new one; the interface preference and last selected session then reset, while all saved project data remains available. It stops the backend when the app quits. **File → Open app data folder** opens its data, and **File → Open logs folder** opens the bounded local backend log. For trusted LAN access, continue using the separate [source installation](INSTALL.md).

## Build and run from source

Build on the same operating system and architecture as the intended installer. The Python executable and media tools are platform-specific, so changing an electron-builder architecture flag alone is not sufficient to cross-compile the app.

Prerequisites:

- Node.js 22.13.1 or newer and npm.
- Python 3.11 and [uv](https://docs.astral.sh/uv/getting-started/installation/); uv can install Python.
- Internet access for the first dependency/tool download, and the platform's normal packaging tools. On Linux, `.deb` packaging requires tools such as `dpkg` and `fakeroot`; macOS builds require a Mac with Xcode Command Line Tools.

From the repository root:

```bash
npm ci
uv sync --frozen --group desktop --python 3.11
npm test
uv run --frozen --group desktop python -m unittest discover -s tests
npm run build:desktop
npm run smoke:backend
npm start
```

`build:desktop` freezes the Python backend using PyInstaller and stages FFmpeg/ffprobe from the locked npm dependencies. `smoke:backend` starts that frozen executable and checks authentication, API responses, bundled interface assets and media tools. `npm start` opens Electron using the frozen backend, so run `build:desktop` first and rebuild after backend or bundled static-asset changes.

Create installers after building and smoke-testing:

```bash
# Windows x64, from Windows:
npm run dist -- --win --x64

# Linux x64, from Linux:
npm run dist -- --linux --x64

# Intel macOS, from an Intel Mac:
npm run dist -- --mac --x64

# Apple Silicon macOS, from an Apple Silicon Mac:
npm run dist -- --mac --arm64
```

Installers appear in `release/`. The `dist` script disables automatic publishing. The source web app remains available through the commands in the [installation guide](INSTALL.md).

## GitHub builds and releases

The [Desktop builds workflow](../.github/workflows/desktop.yml) runs on pull requests, pushes to `main`, `v*` tag pushes, and manual dispatch. It validates matching versions in `package.json`, `package-lock.json` and `pyproject.toml`, then tests and builds these native targets:

| Runner | Target | Files |
|---|---|---|
| `windows-2022` | Windows x64 | NSIS `.exe` |
| `ubuntu-22.04` | Linux x64 | `.AppImage`, `.deb` |
| `macos-15-intel` | macOS x64 | `.dmg`, `.zip` |
| `macos-15` | macOS arm64 | `.dmg`, `.zip` |

These architecture-specific macOS labels follow [GitHub's runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners). Successful builds upload versioned artifacts to the workflow run for 14 days. Download them from the run's **Artifacts** section; GitHub may require sign-in for workflow artifacts.

To prepare a release:

1. Set the same `X.Y.Z` version in `package.json` and `pyproject.toml`, refresh `package-lock.json` with `npm install --package-lock-only`, and refresh `uv.lock` with `uv lock`.
2. Commit the changes and push a matching `vX.Y.Z` tag, for example `git tag v0.4.0` followed by `git push origin v0.4.0`. Use a new version if that tag already exists.
3. Wait for all four builds. Only a successful tag-push run creates a **draft** GitHub release containing the seven installers/archives and `SHA256SUMS`.
4. Download and open each installer on its target platform, review the generated release notes, then publish the draft when ready.

A mismatched tag fails before packaging. Pull requests, branch pushes and manual runs only upload workflow artifacts. Build jobs have read-only repository permissions; only the release job receives `contents: write`. No signing secrets are required. Re-running a tag build can refresh assets on an existing draft; it refuses to overwrite a published release.

For verified developer distribution later, configure Windows code signing and an Apple Developer ID signing identity plus notarization in electron-builder and the workflow. The current workflow disables automatic certificate discovery and the macOS configuration uses ad-hoc signing, so adding credentials alone does not enable verified macOS signing. Keep signing credentials in GitHub Actions secrets and restrict them to trusted release runs. See electron-builder v26's [Windows signing](https://www.electron.build/v26/docs/features/code-signing/code-signing-win/) and [macOS signing](https://www.electron.build/v26/docs/features/code-signing/code-signing-mac/) guidance.
