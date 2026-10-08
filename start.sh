#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1
command -v uv >/dev/null || { echo "Install uv: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null || { echo "Install FFmpeg and ffprobe, then launch again: https://ffmpeg.org/download.html"; exit 1; }
uv sync --frozen --python 3.11
exec uv run --frozen fpv-audio-pairing --host 127.0.0.1 --port 8768 --open "$@"
