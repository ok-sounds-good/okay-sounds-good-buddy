"""Normalize shared release names after validating and backing up archives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import archives as archive_services
from .. import shared as shared_services
from ..config import OksgConfig

validate_zip_pair = archive_services.validate_zip_pair
shared_rename_plan = shared_services.shared_rename_plan


@dataclass(frozen=True)
class NormalizeSharedOptions:
    """Target and dry-run controls for shared-name normalization."""

    shared_folder: str | None = None
    dry_run: bool = False


def user_path(value: str, base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return ((base or Path.cwd()) / path).resolve()


def display_path(path: Path) -> Path:
    """Prefer project-relative diagnostics without rejecting valid external paths."""
    return path


def run(*, config: OksgConfig, options: NormalizeSharedOptions = NormalizeSharedOptions()) -> None:
    shared = user_path(options.shared_folder) if options.shared_folder else config.shared_folder
    if not shared.exists():
        raise SystemExit(f"Shared folder not found: {shared}")
    if not shared.is_dir():
        raise SystemExit(f"Shared folder is not a directory: {shared}")

    # Validate every archive before deciding whether any names need changing.
    for zip_path in sorted(shared.glob("*.zip")):
        validate_zip_pair(zip_path)

    plan = [
        (old, new)
        for old, new in shared_rename_plan(shared, config.creator_code)
        if new and old != new
    ]
    if not plan:
        print("No shared files need Harley renaming.")
        return

    targets: set[Path] = set()
    for old, new in plan:
        for suffix in [".zip", ".mp4"]:
            src = shared / f"{old}{suffix}"
            dest = shared / f"{new}{suffix}"
            if src.exists():
                if dest.exists() and dest != src:
                    raise SystemExit(f"Refusing to overwrite existing file: {dest}")
                if dest in targets:
                    raise SystemExit(f"Multiple shared files would normalize to: {dest}")
                targets.add(dest)

    print(f"Shared folder: {shared}")
    print(f"{'Would rename' if options.dry_run else 'Renaming'} {len(plan)} shared stems")
    for old, new in plan:
        print(f"{old}")
        print(f"  -> {new}")
        zip_path = shared / f"{old}.zip"
        mp4_path = shared / f"{old}.mp4"
        if zip_path.exists():
            validate_zip_pair(zip_path)
        if not zip_path.exists() and not mp4_path.exists():
            raise SystemExit(f"No shared zip or mp4 found for: {old}")

    if options.dry_run:
        return

    # Back up every archive before the first normalization mutation so a
    # multi-release run cannot touch a creator's only copy without recovery.
    backups = {}
    for old, _new in plan:
        zip_path = shared / f"{old}.zip"
        if zip_path.exists():
            backups[zip_path] = archive_services.backup_zip_for_repair(zip_path, config)
            print(f"Verified repair backup: {backups[zip_path].backup}")

    for old, new in plan:
        zip_path = shared / f"{old}.zip"
        mp4_path = shared / f"{old}.mp4"
        if zip_path.exists():
            archive_services.rewrite_zip_member_names(zip_path, new, backups[zip_path])
            zip_path.rename(shared / f"{new}.zip")
        if mp4_path.exists():
            mp4_path.rename(shared / f"{new}.mp4")

    print()
    print("=" * 58)
    print(f"{config.creator_code} shared name normalization complete")
    print("=" * 58)
    print(f"Renamed stems: {len(plan)}")
    print("=" * 58)
