"""Interactive configuration command."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path

from oksg_buddy import config as oksg

VERSION = "1"


def prompt_path(label: str, default: str = "", *, directory: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{label}{suffix}: ").strip() or default
        path = Path(value).expanduser()
        if path.is_absolute() and (not directory or path.is_dir()):
            return str(path)
        print("Enter an absolute path" + (" to an existing directory." if directory else "."))


def write_config(path: Path, values: dict) -> None:
    lines = ["[workspace]"]
    for key in ("karaoke_root", "shared_folder", "repair_backup_dir"):
        lines.append(f"{key} = {json.dumps(values[key])}")
    lines += [
        "",
        "[branding]",
        f"creator_code = {json.dumps(values['creator_code'])}",
        f"creator_name = {json.dumps(values['creator_name'])}",
        "",
        "[assets]",
        f"logo_path = {json.dumps(values.get('logo_path', ''))}",
        "font_dirs = [",
    ]
    lines.extend(f"  {json.dumps(item)}," for item in values.get("font_dirs", []))
    lines += ["]", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp_name, path)
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def config_from_values(values: dict, *, require_existing: bool) -> oksg.OksgConfig:
    return oksg.validate_config_data(
        {
            "workspace": {
                key: values[key] for key in ("karaoke_root", "shared_folder", "repair_backup_dir")
            },
            "branding": {
                "creator_code": values["creator_code"],
                "creator_name": values["creator_name"],
            },
            "assets": {
                "logo_path": values.get("logo_path", ""),
                "font_dirs": values.get("font_dirs", []),
            },
        },
        require_existing=require_existing,
    )


def run(*, path: Path) -> int:
    existing = {}
    if path.exists():
        try:
            config = oksg.load_config(path, require_existing=False)
            existing = {
                "karaoke_root": str(config.karaoke_root),
                "shared_folder": str(config.shared_folder),
                "repair_backup_dir": str(config.repair_backup_dir),
                "creator_code": config.creator_code,
                "creator_name": config.creator_name,
                "logo_path": str(config.logo_path or ""),
                "font_dirs": [str(p) for p in config.font_dirs],
            }
        except Exception:
            pass
    karaoke_root = prompt_path(
        "Karaoke workspace",
        existing.get("karaoke_root", str(Path.home() / "Music/Karaoke")),
        directory=True,
    )
    shared_folder = prompt_path(
        "Shared folder",
        existing.get("shared_folder", str(Path.home() / "Music/OKSG Karaoke")),
        directory=True,
    )
    backup = prompt_path(
        "Repair backup directory",
        existing.get("repair_backup_dir", str(oksg.REPOSITORY_ROOT / ".repair-backups")),
    )
    code = input(
        f"Creator code [{existing.get('creator_code', 'OKSG')}]: "
    ).strip().upper() or existing.get("creator_code", "OKSG")
    name = input(
        f"Creator name [{existing.get('creator_name', 'Okay, Sounds Good Karaoke')}]: "
    ).strip() or existing.get("creator_name", "Okay, Sounds Good Karaoke")
    logo = input(f"Optional logo path [{existing.get('logo_path', '')}]: ").strip()
    fonts = [
        item.strip()
        for item in input("Optional font directories (comma-separated): ").split(",")
        if item.strip()
    ]
    values = {
        "karaoke_root": karaoke_root,
        "shared_folder": shared_folder,
        "repair_backup_dir": backup,
        "creator_code": code,
        "creator_name": name,
        "logo_path": logo,
        "font_dirs": fonts,
    }
    try:
        config_from_values(values, require_existing=False)
    except oksg.ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    print("\nConfiguration to write:")
    print(values)
    if input("Write this configuration? [y/N] ").strip().lower() != "y":
        print("Configuration not written.")
        return 1
    if not Path(backup).exists():
        if input(f"Create backup directory {backup}? [y/N] ").strip().lower() != "y":
            print("Backup directory is required; configuration not written.", file=sys.stderr)
            return 1
        Path(backup).mkdir(parents=True)
    try:
        config_from_values(values, require_existing=True)
    except oksg.ConfigError as exc:
        print(f"Configuration is not usable; nothing was written:\n{exc}", file=sys.stderr)
        return 2
    write_config(path, values)
    print(f"Wrote {path} (mode 600 where supported)")
    return 0
