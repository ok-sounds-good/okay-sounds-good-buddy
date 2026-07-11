"""Immutable application data models."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OksgConfig:
    """Validated creator configuration and filesystem locations."""

    karaoke_root: Path
    shared_folder: Path
    repair_backup_dir: Path
    creator_code: str
    creator_name: str
    logo_path: Path | None
    font_dirs: tuple[Path, ...]


@dataclass(frozen=True)
class SongInfo:
    """Artist and song-title metadata for one karaoke project."""

    artist: str
    song: str

    @property
    def work_folder_name(self) -> str:
        """Return the conventional working-directory name."""

        return f"{self.artist} - {self.song}"


@dataclass(frozen=True)
class ThumbnailFonts:
    """Optional font selections for each thumbnail text role."""

    band: str | None = None
    song: str | None = None
    banner: str | None = None


@dataclass(frozen=True)
class ThumbnailStyle:
    """Rendering dimensions, colors, and fonts for a thumbnail profile."""

    background: tuple[int, int, int]
    song_color: tuple[int, int, int]
    band_color: tuple[int, int, int]
    banner_color: tuple[int, int, int]
    song_box: tuple[int, int, int]
    band_box: tuple[int, int, int]
    song_y: int
    band_gap: int
    logo_y: int
    logo_size: tuple[int, int]
    banner_y: int
    pixelate: bool
    default_band_font: str | None
    default_song_font: str | None
    default_banner_font: str | None


@dataclass(frozen=True)
class SharedName:
    """Parsed creator release name used in the shared folder."""

    number: int
    artist: str
    song: str
    code: str = "OKSG"

    @property
    def stem(self) -> str:
        """Return the normalized shared-file stem."""

        return f"{self.code}-{self.number:04d} - {self.artist} - {self.song}"
