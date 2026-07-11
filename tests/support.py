from __future__ import annotations

import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from oksg_buddy.models import OksgConfig


@dataclass(frozen=True)
class ProjectTree:
    root: Path
    shared: Path
    config: OksgConfig


@contextmanager
def temporary_project() -> Iterator[ProjectTree]:
    with tempfile.TemporaryDirectory() as directory:
        music = Path(directory) / "Music"
        root = music / "Karaoke"
        shared = music / "OKSG Karaoke"
        backups = music / "repair-backups"
        root.mkdir(parents=True)
        shared.mkdir()
        backups.mkdir()
        config = OksgConfig(root, shared, backups, "OKSG", "Okay, Sounds Good Karaoke", None, ())
        yield ProjectTree(root, shared, config)
