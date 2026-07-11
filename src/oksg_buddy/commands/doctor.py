"""Configuration and dependency diagnostics."""

import shutil
from pathlib import Path

from .. import config as config_service


def run(*, path: Path) -> int:
    print(f"Config: {path}")
    try:
        config = config_service.load_config(path)
    except config_service.ConfigError as exc:
        print(f"FAIL configuration: {exc}")
        return 1
    print(f"OK   workspace: {config.karaoke_root}")
    print(f"OK   shared folder: {config.shared_folder}")
    print(f"OK   repair backups: {config.repair_backup_dir}")
    print(f"OK   creator: {config.creator_code} / {config.creator_name}")
    print(f"OK   ffmpeg: {shutil.which('ffmpeg') or 'missing'}")
    print(f"OK   yt-dlp: {shutil.which('yt-dlp') or 'missing'}")
    print(
        f"Fonts: {', '.join(str(p) for p in config.font_dirs) or 'platform discovery + Pillow fallback'}"
    )
    return 0
