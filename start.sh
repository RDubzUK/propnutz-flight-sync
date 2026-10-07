#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1
if [ ! -x .venv/bin/python ]; then
  uv venv --python 3.11
  uv pip install --python .venv/bin/python -e .
fi
exec .venv/bin/python -m fpv_audio_pairing.web --host 0.0.0.0 --port 8768 "$@"
