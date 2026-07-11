"""Create a new karaoke project from explicit or downloaded metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import OksgConfig
from ..media import download_audio, youtube_metadata
from ..models import SongInfo, ThumbnailFonts
from ..naming import clean_piece, next_release_number, parse_artist_song
from ..thumbnails import make_thumbnail


@dataclass(frozen=True)
class NewSongOptions:
    """Source metadata, naming, and rendering options for a new project."""

    url: str
    artist: str | None = None
    song: str | None = None
    folder: str | None = None
    number: int | None = None
    thumbnail_style: str = "retro"
    font: str | None = None
    font_release: str | None = None
    font_band: str | None = None
    font_song: str | None = None
    font_banner: str | None = None
    no_download: bool = False


def resolve_song_info(options: NewSongOptions) -> tuple[SongInfo, dict | None]:
    metadata = None
    parsed = None

    if options.url and not (options.artist and options.song):
        metadata = youtube_metadata(options.url)
        if metadata.get("artist") and metadata.get("track"):
            parsed = SongInfo(metadata["artist"], metadata["track"])
        else:
            parsed = parse_artist_song(metadata.get("title", ""))
    elif options.url:
        metadata = {"webpage_url": options.url, "original_url": options.url, "title": ""}

    artist = options.artist or (parsed.artist if parsed else None)
    song = options.song or (parsed.song if parsed else None)

    if not artist or not song:
        title = metadata.get("title", "") if metadata else ""
        if title:
            print(f"Could not confidently parse artist/song from: {title}")
        raise SystemExit("Pass --artist and --song.")

    return SongInfo(clean_piece(artist), clean_piece(song)), metadata


def safe_mkdir(path: Path) -> None:
    if path.exists():
        return
    path.mkdir(parents=True)


def user_path(value: str, base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return ((base or Path.cwd()) / path).resolve()


def display_path(path: Path) -> Path:
    """Prefer project-relative diagnostics without rejecting valid external paths."""
    return path


def write_status_file(
    folder: Path, info: SongInfo, number: int, metadata: dict | None, code: str = "OKSG"
) -> None:
    title = metadata.get("title", "") if metadata else ""
    url = metadata.get("webpage_url") or metadata.get("original_url") if metadata else ""
    status = f"""# {info.work_folder_name}

Release code: {code}-{number:04d}
YouTube source: {url}
Source title: {title}

## Checklist

- [ ] Upload the best-audio download to x-minus.
- [ ] Download instrumental.
- [ ] Build lyric timing in MidiCo with `{info.work_folder_name}.mp3`.
- [ ] Replace audio with instrumental.
- [ ] Import Thumbnail.png into the video project.
- [ ] Export CDG and MOV.
- [ ] Run finish-song to package CDG/MP3 and convert MOV to MP4.
- [ ] Upload MP4 and Thumbnail.png to YouTube.
"""
    path = folder / "OKSG_STATUS.md"
    if not path.exists():
        path.write_text(status, encoding="utf-8")


def thumbnail_fonts_from_options(options: NewSongOptions) -> ThumbnailFonts:
    base = options.font
    release = options.font_release or base
    return ThumbnailFonts(
        band=options.font_band or release,
        song=options.font_song or release,
        banner=options.font_banner or base,
    )


def run(*, config: OksgConfig, options: NewSongOptions) -> None:
    info, metadata = resolve_song_info(options)
    root = config.karaoke_root
    code = config.creator_code
    number = options.number or next_release_number(root, code)
    folder = root / (options.folder or info.work_folder_name)
    safe_mkdir(folder)

    thumbnail_path = folder / "Thumbnail.png"
    make_thumbnail(
        info, thumbnail_path, options.thumbnail_style, thumbnail_fonts_from_options(options), config
    )
    write_status_file(folder, info, number, metadata, code)

    audio_paths: tuple[Path, Path] | None = None
    if options.url and not options.no_download:
        audio_paths = download_audio(options.url, folder, info)

    print(f"Created: {folder}")
    print(f"Release code: {code}-{number:04d}")
    print(f"Thumbnail: {thumbnail_path}")
    if audio_paths:
        print(f"Best audio: {audio_paths[0]}")
        print(f"MP3: {audio_paths[1]}")
