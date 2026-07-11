$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Error "uv is required. Install it from https://docs.astral.sh/uv/ after reviewing the official instructions."
}
Set-Location $Repo
uv python install
uv sync
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Host "Optional tool missing: ffmpeg" }
if (-not (Get-Command yt-dlp -ErrorAction SilentlyContinue)) { Write-Host "Optional tool missing: yt-dlp" }
uv run oksg configure
if ($env:OKSG_INSTALL_SHIM -eq "1") { uv run oksg install-shim }
