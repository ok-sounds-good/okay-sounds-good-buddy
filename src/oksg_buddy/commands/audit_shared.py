"""Audit shared release names, media pairs, and archive contents."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from ..archives import significant_zip_members, zip_member_audit_statuses
from ..config import OksgConfig
from ..shared import shared_media_inventory, shared_rename_plan


@dataclass(frozen=True)
class AuditSharedOptions:
    """Options for the shared-folder audit command."""

    shared_folder: str | None = None


def user_path(value: str, base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return ((base or Path.cwd()) / path).resolve()


def display_path(path: Path) -> Path:
    """Prefer project-relative diagnostics without rejecting valid external paths."""
    return path


def run(*, config: OksgConfig, options: AuditSharedOptions = AuditSharedOptions()) -> None:
    shared = user_path(options.shared_folder) if options.shared_folder else config.shared_folder
    if not shared.exists():
        raise SystemExit(f"Shared folder not found: {shared}")

    print(f"Shared folder: {shared}")
    print()

    bad_names: list[tuple[str, str | None]] = []
    for old, new in shared_rename_plan(shared, config.creator_code):
        if new is None or old != new:
            bad_names.append((old, new))

    print("Harley naming")
    if not bad_names:
        print("OK   all shared stems match Harley-style naming")
    else:
        for old, new in bad_names:
            if new:
                print(f"FIX  {old}")
                print(f"  -> {new}")
            else:
                print(f"MISS could not parse: {old}")

    print()
    inventory = shared_media_inventory(shared)
    only_zip = [stem for stem, has_zip, has_mp4 in inventory if has_zip and not has_mp4]
    only_mp4 = [stem for stem, has_zip, has_mp4 in inventory if has_mp4 and not has_zip]
    both = [stem for stem, has_zip, has_mp4 in inventory if has_zip and has_mp4]
    neither = [stem for stem, has_zip, has_mp4 in inventory if not has_zip and not has_mp4]

    print(f"Shared releases ({len(inventory)})")
    for stem, has_zip, has_mp4 in inventory:
        if has_zip and has_mp4:
            kind = "zip+mp4"
        elif has_zip:
            kind = "zip"
        elif has_mp4:
            kind = "mp4"
        else:
            kind = "missing media"
        print(f"OK   {stem} [{kind}]")

    print()
    print("=" * 58)
    print(f"{config.creator_code} shared media audit complete")
    print("=" * 58)
    print(f"Shared folder: {shared}")
    print(f"Releases: {len(inventory)}")
    print(f"Zip + MP4: {len(both)}")
    print(f"Zip only: {len(only_zip)}")
    print(f"MP4 only: {len(only_mp4)}")
    if neither:
        print(f"Missing media: {len(neither)}")
    print("=" * 58)

    print()
    audit_shared_zip_contents(shared, config.creator_code)


def audit_shared_zip_contents(shared: Path, creator_code: str = "OKSG") -> None:
    zips = sorted(shared.glob("*.zip"))
    if not zips:
        print("Zip contents")
        print("OK   no zip files to inspect")
        return

    print(f"Zip contents ({len(zips)})")
    clean: list[str] = []
    bad: list[str] = []
    for zip_path in zips:
        expected = zip_path.stem
        with zipfile.ZipFile(zip_path) as zf:
            names = significant_zip_members(zf.namelist())

        member_statuses = zip_member_audit_statuses(names, expected)
        zip_ok = len(member_statuses) == 2 and all(not status for _, status in member_statuses)
        print(f"{'OK' if zip_ok else 'BAD':<3}  {zip_path.name}")
        for name, statuses in member_statuses:
            label = f" [{', '.join(statuses)}]" if statuses else ""
            print(f"|-   {Path(name).name}{label}")

        if zip_ok:
            clean.append(zip_path.name)
        else:
            bad.append(zip_path.name)

    print()
    print("=" * 58)
    print(f"{creator_code} shared zip-content audit complete")
    print("=" * 58)
    print(f"Scanned: {len(zips)}")
    print(f"Clean: {len(clean)}")
    print(f"Bad: {len(bad)}")
    print("=" * 58)
    if bad:
        raise SystemExit(1)
