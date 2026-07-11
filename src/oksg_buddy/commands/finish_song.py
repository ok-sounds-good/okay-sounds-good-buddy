"""Package completed karaoke media and optionally copy it to shared storage."""

from __future__ import annotations

import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ..config import OksgConfig
from ..media import (
    convert_mov_to_mp4,
    md5sum,
    media_candidates,
    preferred_existing_mp4,
    stage_mp4_for_final_name,
    validate_explicit_file,
)
from ..models import SongInfo
from ..naming import next_release_number, parse_artist_song, release_name


@dataclass(frozen=True)
class FinishSongOptions:
    """Inputs and write controls for completing one karaoke release."""

    folder: str
    artist: str | None = None
    song: str | None = None
    number: int | None = None
    mp3: str | None = None
    cdg: str | None = None
    mp4: str | None = None
    mov: str | None = None
    mp4_only: bool = False
    dry_run: bool = False
    copy_to_shared: bool = True


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


def choose_file(
    label: str, explicit: str | None, folder: Path, suffix: str, required: bool
) -> Path | None:
    if explicit:
        return validate_explicit_file(label, explicit, folder, suffix)
    if not required:
        return None
    matches = media_candidates(folder, suffix)
    if not matches:
        raise SystemExit(f"No {suffix} file found under {folder}")
    if len(matches) > 1:
        print(f"Multiple {label} candidates found:")
        for idx, path in enumerate(matches, 1):
            print(f"  {idx}. {display_path(path)}")
        raise SystemExit(f"Pass --{label} to choose one.")
    return matches[0]


def choose_existing_mp4(
    explicit: str | None, folder: Path, final_name: str, code: str = "OKSG"
) -> Path | None:
    if explicit:
        return validate_explicit_file("mp4", explicit, folder, ".mp4")
    selected, ambiguous = preferred_existing_mp4(folder, final_name, code)
    if selected or not ambiguous:
        return selected
    print("Multiple mp4 candidates found:")
    for idx, path in enumerate(ambiguous, 1):
        print(f"  {idx}. {display_path(path)}")
    raise SystemExit("Pass --mp4 to choose one.")


def package_cdg(mp3: Path, cdg: Path, final_name: str, package_dir: Path) -> Path:
    safe_mkdir(package_dir)
    staged = package_dir / final_name
    safe_mkdir(staged)
    staged_mp3 = staged / f"{final_name}.mp3"
    staged_cdg = staged / f"{final_name}.cdg"
    shutil.copy2(mp3, staged_mp3)
    shutil.copy2(cdg, staged_cdg)

    zip_path = package_dir / f"{final_name}.zip"
    if zip_path.exists():
        raise SystemExit(f"Refusing to overwrite existing zip: {zip_path}")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(staged_mp3, arcname=staged_mp3.name)
        zf.write(staged_cdg, arcname=staged_cdg.name)
    return zip_path


def youtube_markdown(
    info: SongInfo,
    final_name: str,
    mp4: Path | None,
    thumbnail: Path | None,
    creator_name: str = "Okay, Sounds Good Karaoke",
    creator_code: str = "OKSG",
) -> str:
    title = f"{info.artist} - {info.song} (Karaoke, Instrumental, Lyrics)"
    tags = [
        info.artist,
        info.song,
        f"{info.artist} karaoke",
        f"{info.song} karaoke",
        f"{info.artist} instrumental",
        f"{info.song} instrumental",
        "karaoke",
        "instrumental",
        "lyrics",
        "lyric video",
        creator_name,
    ]
    tag_text = ", ".join(dict.fromkeys(tags))
    mp4_line = str(mp4) if mp4 else ""
    thumbnail_line = str(thumbnail) if thumbnail else ""
    return f"""# YouTube Upload

## Title

{title}

## Description

Karaoke / instrumental lyric video for "{info.song}" by {info.artist}.

Created by {creator_name}.

## Tags

{tag_text}

## Files

Video: {mp4_line}
Thumbnail: {thumbnail_line}

## Shorts / Notes

{creator_code} release name: {final_name}
"""


def write_youtube_file(
    folder: Path, info: SongInfo, final_name: str, mp4: Path | None, config: OksgConfig
) -> Path:
    thumbnail = folder / "Thumbnail.png"
    if not thumbnail.exists():
        generated = folder / "Thumbnail.generated.png"
        thumbnail = generated if generated.exists() else thumbnail
    path = folder / "YOUTUBE.md"
    path.write_text(
        youtube_markdown(
            info, final_name, mp4, thumbnail, config.creator_name, config.creator_code
        ),
        encoding="utf-8",
    )
    return path


def print_completion_block(lines: list[str], creator_code: str) -> None:
    print()
    print("=" * 58)
    print(f"{creator_code} finish-song complete")
    print("=" * 58)
    for line in lines:
        print(line)
    print("=" * 58)


def default_shared_folder(config: OksgConfig) -> Path:
    return config.shared_folder


def copy_to_shared(path: Path, label: str, config: OksgConfig) -> Path | None:
    shared = default_shared_folder(config)
    if not shared.exists():
        raise SystemExit(f"Shared folder not found: {shared}")
    if not shared.is_dir():
        raise SystemExit(f"Shared folder is not a directory: {shared}")

    shared_path = shared / path.name
    if shared_path.exists():
        if (
            label == "mp4"
            and path.stat().st_size == shared_path.stat().st_size
            and md5sum(path) == md5sum(shared_path)
        ):
            print(f"Shared {label} already exists, skipped copy: {shared_path}")
            return shared_path
        raise SystemExit(f"Shared {label} already exists: {shared_path}")

    temporary = shared / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        shutil.copy2(path, temporary)
        if shared_path.exists():
            raise SystemExit(f"Shared {label} already exists: {shared_path}")
        temporary.replace(shared_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"Copied {label} to shared folder: {shared_path}")
    return shared_path


def run(*, config: OksgConfig, options: FinishSongOptions) -> None:
    folder = user_path(options.folder)
    if not folder.exists():
        raise SystemExit(f"Folder not found: {folder}")

    info = SongInfo(options.artist, options.song) if options.artist and options.song else None
    number = options.number or next_release_number(config.karaoke_root, config.creator_code)
    if info is None:
        parsed = parse_artist_song(folder.name)
        if parsed is None:
            raise SystemExit("Pass --artist and --song.")
        info = parsed

    final_name = release_name(info, number, config.creator_code)
    package_dir = folder / final_name

    mp3 = choose_file("mp3", options.mp3, folder, ".mp3", required=not options.mp4_only)
    cdg = choose_file("cdg", options.cdg, folder, ".cdg", required=not options.mp4_only)
    mov = choose_file("mov", options.mov, folder, ".mov", required=False)
    existing_mp4 = choose_existing_mp4(options.mp4, folder, final_name, config.creator_code)
    if options.mp4_only and not existing_mp4 and not mov:
        raise SystemExit("MP4-only release needs an existing MP4 or a MOV passed with --mov.")

    if options.dry_run:
        print(f"Final name: {final_name}")
        print(f"Package folder: {package_dir}")
        if mp3:
            print(f"MP3: {mp3}")
        if cdg:
            print(f"CDG: {cdg}")
        if existing_mp4:
            print(f"Existing MP4: {existing_mp4}")
            if existing_mp4 != folder / f"{final_name}.mp4":
                print(f"Final MP4 output: {folder / (final_name + '.mp4')}")
            print(f"Shared MP4: {default_shared_folder(config) / (final_name + '.mp4')}")
        if mov:
            print(f"MOV: {mov}")
            print(f"MP4 output: {folder / (final_name + '.mp4')}")
            print(f"Shared MP4: {default_shared_folder(config) / (final_name + '.mp4')}")
        print(f"YouTube file: {folder / 'YOUTUBE.md'}")
        return

    completed: list[str] = [f"Name: {final_name}"]
    zip_path = None
    mp4_out = None

    if not options.mp4_only and mp3 and cdg:
        zip_path = package_cdg(mp3, cdg, final_name, package_dir)
        print(f"Zip: {zip_path}")
        completed.append(f"Zip: {zip_path}")
        if options.copy_to_shared:
            shared_zip = copy_to_shared(zip_path, "zip", config)
            if shared_zip:
                completed.append(f"Shared zip: {shared_zip}")

    if existing_mp4:
        mp4_out = stage_mp4_for_final_name(existing_mp4, final_name, folder)
        if mp4_out == existing_mp4:
            print(f"MP4: {mp4_out}")
        else:
            print(f"MP4: {mp4_out} copied from {existing_mp4}")
        completed.append(f"MP4: {mp4_out}")
        if options.copy_to_shared:
            shared_mp4 = copy_to_shared(mp4_out, "mp4", config)
            if shared_mp4:
                completed.append(f"Shared MP4: {shared_mp4}")
    elif mov:
        mp4_out = folder / f"{final_name}.mp4"
        if mp4_out.exists():
            print(f"MP4 already exists, skipped conversion: {mp4_out}")
        else:
            convert_mov_to_mp4(mov, mp4_out)
            print(f"MP4: {mp4_out}")
        completed.append(f"MP4: {mp4_out}")
        if options.copy_to_shared:
            shared_mp4 = copy_to_shared(mp4_out, "mp4", config)
            if shared_mp4:
                completed.append(f"Shared MP4: {shared_mp4}")

    youtube_path = write_youtube_file(folder, info, final_name, mp4_out, config)
    completed.append(f"YouTube notes: {youtube_path}")
    print_completion_block(completed, config.creator_code)
