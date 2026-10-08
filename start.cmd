@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo Install uv first: winget install --id astral-sh.uv -e
  echo Then close this window and double-click start.cmd again.
  pause
  exit /b 1
)
where ffmpeg >nul 2>nul
if errorlevel 1 goto missing_ffmpeg
where ffprobe >nul 2>nul
if errorlevel 1 goto missing_ffmpeg
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
uv sync --frozen --python 3.11
if errorlevel 1 goto failed
uv run --frozen fpv-audio-pairing --host 127.0.0.1 --port 8768 --open %*
if errorlevel 1 goto failed
exit /b 0
:missing_ffmpeg
echo Install FFmpeg with both ffmpeg.exe and ffprobe.exe on your PATH:
echo https://ffmpeg.org/download.html
echo Restart Windows Explorer or sign out if a new PATH is not picked up.
pause
exit /b 1
:failed
echo Flight Sync could not start. Keep the error above when asking for help.
echo Diagnostic command: uv run --frozen fpv-audio-pairing --check
pause
exit /b 1
