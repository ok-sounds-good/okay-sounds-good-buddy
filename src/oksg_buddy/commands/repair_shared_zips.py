"""Repair shared archives while preserving backups and video siblings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import archives as archive_services
from .. import shared as shared_services
from ..config import OksgConfig
from ..media import VIDEO_SUFFIXES
from ..media import video_candidates_for as package_video_candidates_for
from ..naming import normalize_stem

require_repair_backup = archive_services.require_repair_backup
inspect_cdg_zip_members = archive_services.inspect_cdg_zip_members
zip_member_suffix = archive_services.zip_member_suffix


@dataclass(frozen=True)
class RepairSharedZipsOptions:
    """Target and dry-run controls for shared-archive repair."""

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


def find_local_cdg_mp3(final_name: str, root: Path) -> tuple[Path, Path]:
    wanted = normalize_stem(final_name)
    cdgs = [p for p in root.rglob("*.cdg") if normalize_stem(p.stem) == wanted]
    mp3s = [p for p in root.rglob("*.mp3") if normalize_stem(p.stem) == wanted]

    if len(cdgs) != 1 or len(mp3s) != 1:
        raise SystemExit(
            f"{final_name}: expected exactly one local .cdg and one local .mp3, "
            f"found {len(cdgs)} cdg and {len(mp3s)} mp3"
        )
    return cdgs[0], mp3s[0]


def video_candidates_for(final_name: str, root: Path, code: str = "OKSG") -> list[Path]:
    return package_video_candidates_for(final_name, root, code)


def run(
    *, config: OksgConfig, options: RepairSharedZipsOptions = RepairSharedZipsOptions()
) -> None:
    shared = user_path(options.shared_folder) if options.shared_folder else config.shared_folder
    if not options.dry_run:
        require_repair_backup(config)
    if not shared.exists():
        raise SystemExit(f"Shared folder not found: {shared}")
    if not shared.is_dir():
        raise SystemExit(f"Shared folder is not a directory: {shared}")

    zips = sorted(shared.glob("*.zip"))
    if not zips:
        raise SystemExit(f"No zip files found in: {shared}")

    changed: list[str] = []
    clean: list[str] = []
    print(f"Scanning {len(zips)} zip files in {shared}")
    inspected: list[tuple[Path, str, str | None, str | None, list[str]]] = []
    for zip_path in zips:
        details = inspect_cdg_zip_members(zip_path)
        video_members = [name for name in details[3] if zip_member_suffix(name) in VIDEO_SUFFIXES]
        if len(video_members) > 1:
            raise SystemExit(
                f"{zip_path.name}: found multiple embedded videos: {', '.join(video_members)}"
            )
        inspected.append((zip_path, zip_path.stem, *details))

    backups = {}
    if not options.dry_run:
        for zip_path, _final_name, cdg_member, mp3_member, wav_member, removable in inspected:
            if removable or wav_member or not cdg_member or not mp3_member:
                backups[zip_path] = archive_services.backup_zip_for_repair(zip_path, config)
                print(f"Verified repair backup: {backups[zip_path].backup}")

    for zip_path, final_name, cdg_member, mp3_member, wav_member, removable in inspected:
        if removable:
            video_members = [
                name for name in removable if zip_member_suffix(name) in VIDEO_SUFFIXES
            ]
            if len(video_members) > 1:
                raise SystemExit(
                    f"{zip_path.name}: found multiple embedded videos: {', '.join(video_members)}"
                )
            if video_members:
                mp4_dest = shared / f"{final_name}.mp4"
                if not mp4_dest.exists():
                    print(f"     preserving sibling MP4 from {video_members[0]}")
                    if not options.dry_run:
                        shared_services.restore_shared_mp4_from_zip_member(
                            shared, zip_path, final_name, video_members[0], options.dry_run
                        )
            local_pair = None
            if cdg_member and wav_member and not mp3_member:
                print(
                    f"FIX  {zip_path.name}: converting {wav_member} to MP3 and removing {', '.join(removable)}"
                )
            elif not cdg_member or not mp3_member:
                local_pair = find_local_cdg_mp3(final_name, config.karaoke_root)
                print(
                    f"FIX  {zip_path.name}: replacing video-only zip with "
                    f"{local_pair[0].name} + {local_pair[1].name}"
                )
            else:
                print(f"FIX  {zip_path.name}: removing {', '.join(removable)}")
            changed.append(zip_path.name)
            if not options.dry_run:
                if cdg_member and mp3_member:
                    archive_services.rewrite_zip_cdg_only(
                        zip_path, cdg_member, mp3_member, backups[zip_path]
                    )
                elif cdg_member and wav_member:
                    archive_services.rewrite_zip_cdg_wav_as_mp3(
                        zip_path, cdg_member, wav_member, final_name, backups[zip_path]
                    )
                else:
                    cdg_path, mp3_path = local_pair or find_local_cdg_mp3(
                        final_name, config.karaoke_root
                    )
                    archive_services.rewrite_zip_from_local_pair(
                        zip_path, cdg_path, mp3_path, final_name, backups[zip_path]
                    )
        else:
            if cdg_member and wav_member and not mp3_member:
                print(f"FIX  {zip_path.name}: converting {wav_member} to MP3")
                changed.append(zip_path.name)
                if not options.dry_run:
                    archive_services.rewrite_zip_cdg_wav_as_mp3(
                        zip_path, cdg_member, wav_member, final_name, backups[zip_path]
                    )
                continue
            if not cdg_member or not mp3_member:
                cdg_path, mp3_path = find_local_cdg_mp3(final_name, config.karaoke_root)
                print(
                    f"FIX  {zip_path.name}: rebuilding from local {cdg_path.name} + {mp3_path.name}"
                )
                changed.append(zip_path.name)
                if not options.dry_run:
                    archive_services.rewrite_zip_from_local_pair(
                        zip_path, cdg_path, mp3_path, final_name, backups[zip_path]
                    )
                continue
            print(f"OK   {zip_path.name}")
            clean.append(zip_path.name)

    print()
    print("=" * 58)
    print(f"{config.creator_code} shared zip repair complete")
    print("=" * 58)
    print(f"Shared folder: {shared}")
    print(f"Scanned: {len(zips)}")
    print(f"Already clean: {len(clean)}")
    print(f"{'Would fix' if options.dry_run else 'Fixed'}: {len(changed)}")
    print("=" * 58)
