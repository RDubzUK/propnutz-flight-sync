param([switch]$Lan, [int]$Port = 8768)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
foreach ($Tool in @("uv", "ffmpeg", "ffprobe")) {
    if (-not (Get-Command $Tool -ErrorAction SilentlyContinue)) {
        throw "Missing $Tool. See docs\INSTALL.md or launch start.cmd for setup instructions."
    }
}
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
uv sync --frozen --python 3.11
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
$BindAddress = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
uv run --frozen fpv-audio-pairing --host $BindAddress --port $Port --open
if ($LASTEXITCODE -ne 0) { throw "Flight Sync stopped with an error. Run uv run --frozen fpv-audio-pairing --check." }
