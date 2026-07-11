# Okay, Sounds Good Buddy

`oksg` is a command-line toolkit for preparing karaoke songs and maintaining a shared release library. It downloads source audio, generates thumbnails, packages CD+G releases, converts video, audits release names and ZIP contents, and safely repairs supported problems.

Creator-specific configuration, branding, fonts, logos, and media are kept outside the repository.

## Features

- Start a song workspace from a YouTube URL.
- Generate thumbnails with configurable styles, fonts, and branding.
- Package matching CDG and MP3 files into a release ZIP.
- Convert MOV exports and publish MP4-only releases.
- Audit shared releases for naming, format, and ZIP-content problems.
- Normalize release names and repair supported ZIP and video issues.
- Protect every ZIP rewrite with a verified backup.

## Requirements

- [`uv`](https://docs.astral.sh/uv/) for Python and package management.
- `yt-dlp` for downloading source media.
- `ffmpeg` for audio extraction and video conversion.

`yt-dlp` and `ffmpeg` are only required by commands that process media. Configuration, help, tests, and shared-folder audits do not require them.

## Quick Start

Run the setup script for your platform:

```bash
./setup.sh       # macOS, Linux, or WSL
./setup.ps1      # native Windows PowerShell
```

The setup process creates the managed environment and guides you through creating the local, ignored `.config.toml`. Confirm the resulting configuration with:

```bash
uv run oksg doctor
uv run oksg --help
uv run python -m oksg_buddy --help
```

For manual setup, run `uv sync` followed by `uv run oksg configure`. You can then run commands through `uv run oksg` or the repository launcher, `./oksg`. See [Configuration](docs/configuration.md) for configuration details and [Windows and WSL](docs/windows-and-wsl.md) for platform-specific guidance.

## Typical Workflow

Start a project from a YouTube URL:

```bash
oksg new-song --url "YOUTUBE_URL"
```

If the title cannot be parsed reliably, provide it explicitly:

```bash
oksg new-song --url "YOUTUBE_URL" --artist "Band" --song "Song"
```

After creating and exporting the karaoke track, package a CD+G release and, optionally, convert a MOV video:

```bash
oksg finish-song \
  --folder "Band - Song" \
  --artist "Band" \
  --song "Song" \
  --number 25 \
  --mp3 "Song.mp3" \
  --cdg "Song.cdg" \
  --mov "Song.mov"
```

Use `--dry-run` to review paths and planned changes. `finish-song` copies completed releases to the configured shared folder by default; pass `--no-copy-to-shared` to keep them local.

For an MP4-only release:

```bash
oksg finish-song \
  --folder "Band - Song" \
  --artist "Band" \
  --song "Song" \
  --number 25 \
  --mp4-only
```

## Release Layout

The shared folder is set explicitly in `.config.toml`. `CODE` below represents the creator code chosen during setup. Each release may contain a CD+G ZIP, an MP4, or both:

```text
CODE-0001 - Artist - Title.zip
CODE-0001 - Artist - Title.mp4
```

A valid CD+G ZIP contains exactly one matching CDG and MP3 pair at its root:

```text
CODE-0001 - Artist - Title.zip
|- CODE-0001 - Artist - Title.cdg
|- CODE-0001 - Artist - Title.mp3
```

## Shared-Library Commands

| Command | Purpose |
| --- | --- |
| `oksg audit-shared` | Report naming, release-format, and ZIP-content problems without changing files. |
| `oksg normalize-shared-names --dry-run` | Preview standardized ZIP, MP4, CDG, and MP3 names. |
| `oksg normalize-shared-names` | Apply the previewed naming changes. |
| `oksg repair-shared-zips --dry-run` | Preview supported ZIP repairs. |
| `oksg repair-shared-zips` | Repair supported CD+G ZIP layouts, including embedded video and WAV cases. |
| `oksg repair-shared-videos --dry-run` | Preview recovery of missing sibling MP4s from local project media. |
| `oksg repair-shared-videos` | Restore recoverable sibling MP4s. |

The audit treats every ZIP member other than the expected CDG and MP3 pair as an extra file. Repair is deliberately narrower: it handles supported video and WAV layouts, but stops on arbitrary unexpected members, unsafe paths, ambiguous media, or other cases it cannot repair safely.

## Safety

Commands that change the shared folder support `--dry-run`; preview their work before applying it.

Before changing an existing ZIP, `oksg` creates an exclusive, checksum-verified copy of the original. By default, these backups are stored in the repository's ignored `.repair-backups/` directory, which must remain outside the shared release folder. You can configure another local directory if you do not want the releases and their repair backups stored on the same drive. There is no option to rewrite a ZIP without a verified backup.

When preserving video from a ZIP, `oksg` stages and verifies the MP4 before publishing it beside the ZIP. If the shared filesystem cannot provide the required no-replace behavior, the operation stops and leaves the ZIP unchanged.

See [Release and safety](docs/release-and-safety.md) for the detailed guarantees and limitations.

## Development

```bash
UV_CACHE_DIR=/tmp/oksg-uv-cache uv sync
UV_CACHE_DIR=/tmp/oksg-uv-cache uv run python -m unittest discover -v
UV_CACHE_DIR=/tmp/oksg-uv-cache uv run python -m compileall -q src tests
uv build
git diff --check
```

Tests use temporary project and shared folders; they do not read or change a contributor's configured media or shared library. See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture and validation requirements.
