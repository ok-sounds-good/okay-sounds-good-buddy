"""Render one or all thumbnail styles for a karaoke project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import OksgConfig
from ..media import audio_basename, youtube_metadata
from ..models import SongInfo, ThumbnailFonts
from ..naming import clean_piece, parse_artist_song
from ..thumbnails import THUMBNAIL_STYLES, make_thumbnail


@dataclass(frozen=True)
class ThumbnailOptions:
    """Metadata, destination, style, and font choices for rendering."""

    artist: str | None = None
    song: str | None = None
    url: str | None = None
    folder: str | None = None
    output: str | None = None
    style: str | None = None
    font: str | None = None
    font_release: str | None = None
    font_band: str | None = None
    font_song: str | None = None
    font_banner: str | None = None


def resolve_song_info(options: ThumbnailOptions) -> tuple[SongInfo, dict | None]:
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


def thumbnail_fonts_from_options(options: ThumbnailOptions) -> ThumbnailFonts:
    base = options.font
    release = options.font_release or base
    return ThumbnailFonts(
        band=options.font_band or release,
        song=options.font_song or release,
        banner=options.font_banner or base,
    )


def run(*, config: OksgConfig, options: ThumbnailOptions) -> None:
    root = config.karaoke_root
    info, _ = resolve_song_info(options)
    folder = root / (options.folder or info.work_folder_name)
    fonts = thumbnail_fonts_from_options(options)
    if options.style is None:
        if options.output:
            raise SystemExit("--output requires --style because all styles create separate files.")
        for style in THUMBNAIL_STYLES:
            output = folder / f"{audio_basename(info)} - {style}.png"
            make_thumbnail(info, output, style, fonts, config)
            print(f"Thumbnail: {output}")
        return

    output = Path(options.output) if options.output else folder / "Thumbnail.png"
    if not output.is_absolute():
        output = root / output
    make_thumbnail(info, output, options.style, fonts, config)
    print(f"Thumbnail: {output}")
