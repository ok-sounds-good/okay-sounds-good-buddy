"""Install a launcher that targets the package console entrypoint directly."""

import os
import shlex
import stat
from pathlib import Path

from ..config import REPOSITORY_ROOT

VERSION = "1"


def shim_content(repo: Path, *, windows: bool) -> str:
    if windows:
        return f'@echo off\n"{repo}\\.venv\\Scripts\\oksg.exe" %*\n'
    return f'#!/bin/sh\nexec {shlex.quote(str(repo / ".venv/bin/oksg"))} "$@"\n'


def run(
    *, repo: Path = REPOSITORY_ROOT, home: Path | None = None, windows: bool | None = None
) -> int:
    repo = repo.resolve()
    home = home or Path.home()
    windows = os.name == "nt" if windows is None else windows
    target_dir = home / ("bin" if windows else ".local/bin")
    target = target_dir / ("oksg.cmd" if windows else "oksg")
    if input(f"Install shim at {target}? [y/N] ").strip().lower() != "y":
        return 1
    target_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(shim_content(repo, windows=windows), encoding="utf-8")
    if not windows:
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    target.with_name(target.name + ".oksg-meta").write_text(
        f"repo={repo}\nsetup_version={VERSION}\n", encoding="utf-8"
    )
    print(f"Installed shim: {target}")
    print(f"Add {target_dir} to PATH if it is not already present.")
    return 0
