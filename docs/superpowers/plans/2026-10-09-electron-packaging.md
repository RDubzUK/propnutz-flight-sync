# Electron packaging implementation plan

**Goal:** Ship PropNutz Flight Sync as a self-contained desktop application with native GitHub builds and draft releases.

**Architecture:** Electron owns a frozen Python/FastAPI child process, launched on authenticated loopback HTTP. PyInstaller packages the existing engine and static interface; electron-builder bundles it with native FFmpeg/ffprobe. A GitHub matrix builds each platform on its native runner.

**Constraints:** Preserve the existing Python CLI. Store desktop data under Electron's per-user application directory, respecting `FPV_AUDIO_DATA_DIR`. No runtime dependency installation. Windows/Linux x64 and macOS x64/arm64. Version tags create draft releases after all builds pass. Initial installers are unsigned (macOS ad-hoc signed).

- [x] Add the Python desktop entry point and integration tests covering authentication, readiness, port conflicts, data isolation, and shutdown.
- [x] Add the Electron shell and child-process lifecycle tests covering readiness, early exit, timeout, and cleanup. Keep Node unavailable to the renderer and restrict navigation/permissions.
- [x] Freeze the backend with static assets/distribution metadata, stage FFmpeg and ffprobe plus license notices, and smoke-test the frozen bundle.
- [x] Configure native installers and locked Node/Python build dependencies.
- [x] Add native GitHub Actions builds, tag/version checks, artifact uploads, checksums, and draft release creation.
- [x] Document installation, developer builds, persistent data, release steps, and signing limitations.
- [x] Run existing/new tests, a frozen-backend smoke test, a local Linux package build, and an independent review. Record any platform checks that require GitHub runners.

## Verification

- Clean public-registry `npm ci` passed; lockfile contains only `registry.npmjs.org` URLs.
- Python: 33 tests, 32 passed, one native Windows Job Object test skipped on Linux.
- Node lifecycle/navigation tests: 6 passed.
- Frozen-backend smoke passed with only bundled media tools on PATH.
- Packaged Linux Electron UI: modules/API/diagnostics, renderer isolation, shutdown, and preferences across restart passed through Playwright/CDP in a virtual display.
- Linux AppImage and Debian package built successfully; final artifacts were regenerated after review fixes and have SHA256 checksums in `release/SHA256SUMS`.
- Actionlint and workflow version/artifact/checksum checks passed. Independent review found no remaining actionable issues.
- Windows and macOS native builds, signing behavior, and the Windows Job Object runtime test require their GitHub runners; no remote workflows were triggered locally.
