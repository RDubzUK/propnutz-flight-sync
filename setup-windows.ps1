# Installs documented prerequisites through Microsoft's winget registry.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "Install Microsoft App Installer (winget), or follow docs\INSTALL.md for manual setup."
}
foreach ($Package in @(@("uv", "astral-sh.uv"), @("ffmpeg", "Gyan.FFmpeg"))) {
    if (-not (Get-Command $Package[0] -ErrorAction SilentlyContinue)) {
        winget install --id $Package[1] --exact --source winget
        if ($LASTEXITCODE -ne 0) { throw "Installation of $($Package[1]) failed. See docs\INSTALL.md." }
    }
}
# New installers may have updated the user PATH while this shell was open.
$env:PATH = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") + ";" + "$env:LOCALAPPDATA\Microsoft\WinGet\Links"
& "$PSScriptRoot\start.ps1"
