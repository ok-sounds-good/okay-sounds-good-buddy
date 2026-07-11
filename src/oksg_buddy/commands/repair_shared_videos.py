"""Restore missing shared MP4 siblings from local project media."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import shared as shared_services
from ..config import OksgConfig
from ..media import video_candidates_for as package_video_candidates_for

restore_shared_mp4 = shared_services.restore_shared_mp4


@dataclass(frozen=True)
class RepairSharedVideosOptions:
    """Target and dry-run controls for shared-video restoration."""

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


def video_candidates_for(final_name: str, root: Path, code: str = "OKSG") -> list[Path]:
    return package_video_candidates_for(final_name, root, code)


def run(
    *, config: OksgConfig, options: RepairSharedVideosOptions = RepairSharedVideosOptions()
) -> None:
    shared = user_path(options.shared_folder) if options.shared_folder else config.shared_folder
    if not shared.exists():
        raise SystemExit(f"Shared folder not found: {shared}")
    if not shared.is_dir():
        raise SystemExit(f"Shared folder is not a directory: {shared}")

    zips = sorted(shared.glob("*.zip"))
    if not zips:
        raise SystemExit(f"No zip files found in: {shared}")

    missing: list[str] = []
    restored: list[str] = []
    already: list[str] = []
    for zip_path in zips:
        final_name = zip_path.stem
        dest = shared / f"{final_name}.mp4"
        if dest.exists():
            print(f"OK   {dest.name}")
            already.append(dest.name)
            continue

        candidates = video_candidates_for(final_name, config.karaoke_root, config.creator_code)
        if not candidates:
            print(f"MISS {final_name}: no local video candidate")
            missing.append(final_name)
            continue

        source = candidates[0]
        action = (
            "copying"
            if source.suffix.lower() == ".mp4"
            else f"converting {source.suffix.lower()} to mp4"
        )
        print(f"FIX  {dest.name}: {action} from {display_path(source)}")
        restore_shared_mp4(shared, final_name, source, options.dry_run)
        restored.append(dest.name)

    print()
    print("=" * 58)
    print(f"{config.creator_code} shared MP4 repair complete")
    print("=" * 58)
    print(f"Shared folder: {shared}")
    print(f"Already present: {len(already)}")
    print(f"{'Would restore' if options.dry_run else 'Restored'}: {len(restored)}")
    print(f"Missing: {len(missing)}")
    if missing:
        print("Missing names:")
        for name in missing:
            print(f"- {name}")
    print("=" * 58)
    if missing:
        raise SystemExit(1)
