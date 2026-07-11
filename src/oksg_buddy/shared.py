"""Shared-folder inventory and no-replace publication services."""

from __future__ import annotations

import os
import shutil
import uuid
import zipfile
from pathlib import Path

from .archives import zip_member_suffix
from .config import OksgConfig
from .media import convert_video_to_shared_mp4
from .naming import harley_name_for


def default_shared_folder(repo_root: Path, config: OksgConfig | None = None) -> Path:
    if config:
        return config.shared_folder
    candidates = [repo_root.parent / "OKSG Karaoke", repo_root.parents[1] / "OKSG Karaoke"]
    return next((path for path in candidates if path.exists()), candidates[0])


def shared_media_stems(shared: Path) -> list[str]:
    return sorted(
        {p.stem for p in shared.iterdir() if p.is_file() and p.suffix.lower() in {".zip", ".mp4"}}
    )


def shared_media_inventory(shared: Path) -> list[tuple[str, bool, bool]]:
    return [
        (stem, (shared / f"{stem}.zip").exists(), (shared / f"{stem}.mp4").exists())
        for stem in shared_media_stems(shared)
    ]


def shared_rename_plan(shared: Path, code: str = "OKSG") -> list[tuple[str, str | None]]:
    return [(stem, harley_name_for(stem, code)) for stem in shared_media_stems(shared)]


def temporary_shared_path(shared: Path, final_name: str, kind: str, suffix: str = ".tmp") -> Path:
    return shared / f".{final_name}.{kind}.{uuid.uuid4().hex}{suffix}"


def fsync_file(path: Path) -> None:
    # Windows requires a writable file descriptor for fsync.
    with path.open("r+b") as fh:
        os.fsync(fh.fileno())


def publish_new_shared_file(temporary: Path, destination: Path) -> None:
    try:
        os.link(temporary, destination)
    except FileExistsError as exc:
        raise SystemExit(f"Refusing to overwrite existing MP4: {destination}") from exc
    except OSError as exc:
        raise SystemExit(
            f"Could not atomically publish shared MP4 (hard links are unavailable): {destination}. The source ZIP was left unchanged."
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def stage_local_mp4(source: Path, destination: Path, *, convert: bool) -> Path:
    temporary = temporary_shared_path(destination.parent, destination.stem, "mp4")
    try:
        (
            convert_video_to_shared_mp4(source, temporary)
            if convert
            else shutil.copy2(source, temporary)
        )
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise OSError(f"Staged MP4 is missing or empty: {temporary}")
        fsync_file(temporary)
        publish_new_shared_file(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def restore_shared_mp4(shared: Path, final_name: str, source: Path, dry_run: bool) -> Path:
    destination = shared / f"{final_name}.mp4"
    if destination.exists() or dry_run:
        return destination
    return stage_local_mp4(source, destination, convert=source.suffix.lower() != ".mp4")


def restore_shared_mp4_from_zip_member(
    shared: Path, zip_path: Path, final_name: str, member: str, dry_run: bool
) -> Path:
    destination = shared / f"{final_name}.mp4"
    if destination.exists() or dry_run:
        return destination
    suffix = zip_member_suffix(member)
    output_tmp = temporary_shared_path(shared, destination.stem, "mp4")
    source_tmp = (
        output_tmp
        if suffix == ".mp4"
        else temporary_shared_path(shared, destination.stem, "source", suffix)
    )
    try:
        with zipfile.ZipFile(zip_path) as archive:
            info = archive.getinfo(member)
            with archive.open(info) as source, source_tmp.open("wb") as staged:
                shutil.copyfileobj(source, staged)
                staged.flush()
                os.fsync(staged.fileno())
            if source_tmp.stat().st_size != info.file_size:
                raise OSError(f"Staged ZIP member has unexpected size: {source_tmp}")
        if suffix != ".mp4":
            convert_video_to_shared_mp4(source_tmp, output_tmp)
            if not output_tmp.is_file() or output_tmp.stat().st_size == 0:
                raise OSError(f"Converted MP4 is missing or empty: {output_tmp}")
            fsync_file(output_tmp)
        publish_new_shared_file(output_tmp, destination)
    finally:
        source_tmp.unlink(missing_ok=True)
        output_tmp.unlink(missing_ok=True)
    return destination
