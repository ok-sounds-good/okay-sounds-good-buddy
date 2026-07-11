#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "WSL detected. Use Linux paths and run this script inside WSL."
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/ after reviewing the official instructions."
  exit 1
fi
cd "$SCRIPT_DIR"
uv python install
uv sync
for tool in ffmpeg yt-dlp; do
  command -v "$tool" >/dev/null 2>&1 || echo "Optional tool missing: $tool; install it using your platform's package manager after review."
done
uv run oksg configure
if [[ "${OKSG_INSTALL_SHIM:-}" == "1" ]]; then uv run oksg install-shim; fi
