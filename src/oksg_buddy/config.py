"""Configuration loading and validation."""

import os
import re
import tomllib
import uuid
from pathlib import Path

from .models import OksgConfig

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPOSITORY_ROOT / ".config.toml"
CREATOR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9]{2,7}$")


class ConfigError(ValueError):
    """A user-fixable configuration problem."""


def probe_writable_directory(directory: Path) -> bool:
    """Verify that a directory supports the writes needed for repair backups."""
    if not directory.is_dir():
        return False
    probe_path = directory / f".oksg-write-probe-{uuid.uuid4().hex}"
    created = False
    operation_ok = False
    cleanup_ok = True
    try:
        fh = probe_path.open("xb")
        created = True
        with fh:
            fh.write(b"oksg backup write probe\n")
            fh.flush()
            os.fsync(fh.fileno())
        operation_ok = True
    except OSError:
        pass
    finally:
        if created:
            try:
                probe_path.unlink()
            except OSError:
                cleanup_ok = False
    return operation_ok and cleanup_ok


def _config_value(data: dict, section: str, key: str, default=None):
    value = data.get(section, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{section}] must be a table")
    return value.get(key, default)


def validate_config_data(data: dict, *, require_existing: bool = True) -> OksgConfig:
    errors: list[str] = []
    raw_paths = {
        "karaoke_root": _config_value(data, "workspace", "karaoke_root"),
        "shared_folder": _config_value(data, "workspace", "shared_folder"),
        "repair_backup_dir": _config_value(data, "workspace", "repair_backup_dir"),
    }
    paths: dict[str, Path] = {}
    for key, raw in raw_paths.items():
        if not isinstance(raw, str) or not raw.strip():
            errors.append(f"workspace.{key} must be an absolute path")
            continue
        path = Path(raw).expanduser()
        if not path.is_absolute():
            errors.append(f"workspace.{key} must be absolute: {raw}")
        paths[key] = path
        if require_existing and key != "repair_backup_dir" and not path.is_dir():
            errors.append(f"workspace.{key} is not an existing directory: {path}")
    backup = paths.get("repair_backup_dir")
    shared = paths.get("shared_folder")
    if backup and shared:
        try:
            if backup.resolve() == shared.resolve() or shared.resolve() in backup.resolve().parents:
                errors.append("workspace.repair_backup_dir must be outside shared_folder")
        except OSError:
            pass
        if require_existing and not probe_writable_directory(backup):
            errors.append(f"workspace.repair_backup_dir is missing or not writable: {backup}")
    code = _config_value(data, "branding", "creator_code", "OKSG")
    if not isinstance(code, str) or not CREATOR_CODE_RE.fullmatch(code.upper()):
        errors.append("branding.creator_code must match [A-Z][A-Z0-9]{2,7}")
    name = _config_value(data, "branding", "creator_name", "Okay, Sounds Good Karaoke")
    if not isinstance(name, str) or not name.strip():
        errors.append("branding.creator_name must be non-empty")
    logo_raw = _config_value(data, "assets", "logo_path", "")
    logo = Path(logo_raw).expanduser() if isinstance(logo_raw, str) and logo_raw else None
    if logo and (not logo.is_file() or not os.access(logo, os.R_OK)):
        errors.append(f"assets.logo_path is not a readable file: {logo}")
    font_raw = _config_value(data, "assets", "font_dirs", [])
    if not isinstance(font_raw, list):
        errors.append("assets.font_dirs must be an array")
        font_raw = []
    font_dirs = tuple(Path(item).expanduser() for item in font_raw if isinstance(item, str))
    for path in font_dirs:
        if not path.is_dir():
            errors.append(f"assets.font_dirs entry is not a directory: {path}")
    if errors:
        raise ConfigError("\n".join(errors))
    return OksgConfig(
        paths["karaoke_root"].resolve(),
        paths["shared_folder"].resolve(),
        paths["repair_backup_dir"].resolve(),
        code.upper(),
        name.strip(),
        logo.resolve() if logo else None,
        tuple(path.resolve() for path in font_dirs),
    )


def load_config(path: Path = DEFAULT_CONFIG_PATH, *, require_existing: bool = True) -> OksgConfig:
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration not found: {path}. Run `oksg configure`.") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    try:
        mode = path.stat().st_mode
        if mode & 0o022:
            raise ConfigError(f"Configuration is group/world-writable: {path}")
    except FileNotFoundError:
        pass
    return validate_config_data(data, require_existing=require_existing)
