"""Strict archive inspection, verified backups, and ZIP rewrites."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .config import OksgConfig, probe_writable_directory
from .media import VIDEO_SUFFIXES, require_tool, run

ZIP_AUDIO_SUFFIXES = {".cdg", ".mp3", ".wav"}


@dataclass(frozen=True)
class VerifiedBackup:
    """Proof that an archive backup matched its source before mutation."""

    source: Path
    backup: Path
    sha256: str


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_repair_backup(config: OksgConfig) -> None:
    if not probe_writable_directory(config.repair_backup_dir):
        raise SystemExit(
            f"Repair backup directory is missing or not writable: {config.repair_backup_dir}"
        )


def backup_zip_for_repair(zip_path: Path, config: OksgConfig) -> VerifiedBackup:
    require_repair_backup(config)
    for _ in range(20):
        target = config.repair_backup_dir / (
            f"{zip_path.stem}.{time.strftime('%Y%m%d-%H%M%S')}.{uuid.uuid4().hex[:10]}.zip"
        )
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        try:
            with os.fdopen(fd, "wb") as dest, zip_path.open("rb") as source:
                shutil.copyfileobj(source, dest)
                dest.flush()
                os.fsync(dest.fileno())
            source_hash = sha256sum(zip_path)
            if target.stat().st_size != zip_path.stat().st_size or sha256sum(target) != source_hash:
                raise SystemExit(f"Backup verification failed; refusing to repair: {zip_path}")
            return VerifiedBackup(zip_path, target, source_hash)
        except BaseException:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
            raise
    raise SystemExit(f"Could not create an exclusive repair backup for: {zip_path}")


def verify_backup(zip_path: Path, backup: VerifiedBackup) -> None:
    try:
        same_source = backup.source.resolve() == zip_path.resolve()
        same_file = backup.backup.samefile(zip_path)
    except OSError:
        same_file = False
    if not same_source or same_file or not backup.backup.is_file():
        raise SystemExit(f"A verified backup is required before rewriting: {zip_path}")
    if sha256sum(zip_path) != backup.sha256 or sha256sum(backup.backup) != backup.sha256:
        raise SystemExit(f"Backup verification failed; refusing to repair: {zip_path}")


def zip_member_suffix(name: str) -> str:
    return Path(name).suffix.lower()


def is_zip_dir(name: str) -> bool:
    return name.endswith("/")


def significant_zip_members(names: list[str]) -> list[str]:
    return [name for name in names if not is_zip_dir(name)]


def is_root_level_zip_member(name: str) -> bool:
    return bool(name) and not name.startswith(("/", "\\")) and "/" not in name and "\\" not in name


def validate_zip_member_paths(zip_path: Path, names: list[str]) -> None:
    unexpected = [name for name in names if not is_root_level_zip_member(name)]
    if unexpected:
        raise SystemExit(f"{zip_path.name}: unexpected ZIP member paths: {', '.join(unexpected)}")


def inspect_cdg_zip_members(zip_path: Path) -> tuple[str | None, str | None, str | None, list[str]]:
    with zipfile.ZipFile(zip_path) as zf:
        names = significant_zip_members(zf.namelist())
    validate_zip_member_paths(zip_path, names)
    videos = [n for n in names if zip_member_suffix(n) in VIDEO_SUFFIXES]
    cdgs = [n for n in names if zip_member_suffix(n) == ".cdg"]
    mp3s = [n for n in names if zip_member_suffix(n) == ".mp3"]
    wavs = [n for n in names if zip_member_suffix(n) == ".wav"]
    extras = [n for n in names if zip_member_suffix(n) not in ZIP_AUDIO_SUFFIXES | VIDEO_SUFFIXES]
    if extras:
        raise SystemExit(f"{zip_path.name}: unexpected ZIP members: {', '.join(extras)}")
    if videos and wavs:
        raise SystemExit(
            f"{zip_path.name}: multiple embedded media members: {', '.join(videos + wavs)}"
        )
    if not cdgs and not mp3s and not wavs:
        return None, None, None, videos
    if len(cdgs) != 1 or (len(mp3s) != 1 and len(wavs) != 1):
        raise SystemExit(
            f"{zip_path.name}: expected exactly one .cdg and one .mp3, or one .cdg and one .wav for conversion; "
            f"found {len(cdgs)} cdg, {len(mp3s)} mp3, and {len(wavs)} wav"
        )
    audio = mp3s[0] if mp3s else wavs[0]
    if Path(cdgs[0]).stem != Path(audio).stem:
        raise SystemExit(
            f"{zip_path.name}: .cdg/audio base names do not match: {Path(cdgs[0]).stem!r} vs {Path(audio).stem!r}"
        )
    return cdgs[0], mp3s[0] if mp3s else None, wavs[0] if wavs else None, videos + wavs


def validate_zip_pair(zip_path: Path) -> tuple[str, str]:
    cdg, mp3, wav, removable = inspect_cdg_zip_members(zip_path)
    if removable or wav or not cdg or not mp3:
        raise SystemExit(f"{zip_path.name}: zip must be repaired before renaming")
    return cdg, mp3


def zip_member_audit_statuses(names: list[str], expected_stem: str) -> list[tuple[str, list[str]]]:
    statuses = []
    cdg_count = sum(zip_member_suffix(n) == ".cdg" for n in names)
    mp3_count = sum(zip_member_suffix(n) == ".mp3" for n in names)
    for name in names:
        suffix = zip_member_suffix(name)
        state = []
        if suffix not in {".cdg", ".mp3"}:
            state.append("EXTRA FILE")
        if suffix in {".cdg", ".mp3"} and Path(name).stem != expected_stem:
            state.append("NAME ERROR")
        statuses.append((name, state))
    if cdg_count != 1:
        statuses.append(
            (f"{expected_stem}.cdg", ["MISSING CDG" if not cdg_count else f"{cdg_count} CDG FILES"])
        )
    if mp3_count != 1:
        statuses.append(
            (f"{expected_stem}.mp3", ["MISSING MP3" if not mp3_count else f"{mp3_count} MP3 FILES"])
        )
    return statuses


def rewrite_zip_from_data(
    zip_path: Path, entries: list[tuple[str, bytes]], backup: VerifiedBackup
) -> None:
    verify_backup(zip_path, backup)
    with tempfile.NamedTemporaryFile(dir=zip_path.parent, suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as dest:
            for name, data in entries:
                dest.writestr(name, data)
        tmp_path.replace(zip_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def rewrite_zip_member_names(zip_path: Path, final_name: str, backup: VerifiedBackup) -> None:
    cdg, mp3 = validate_zip_pair(zip_path)
    with zipfile.ZipFile(zip_path) as source:
        entries = [(f"{final_name}.cdg", source.read(cdg)), (f"{final_name}.mp3", source.read(mp3))]
    rewrite_zip_from_data(zip_path, entries, backup)


def rewrite_zip_cdg_only(zip_path: Path, cdg: str, mp3: str, backup: VerifiedBackup) -> None:
    with zipfile.ZipFile(zip_path) as source:
        entries = [(Path(cdg).name, source.read(cdg)), (Path(mp3).name, source.read(mp3))]
    rewrite_zip_from_data(zip_path, entries, backup)


def convert_wav_file_to_mp3_bytes(wav_path: Path) -> bytes:
    require_tool("ffmpeg")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        mp3_path = Path(tmp.name)
    try:
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(wav_path),
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "2",
                str(mp3_path),
            ],
            capture=True,
        )
        return mp3_path.read_bytes()
    finally:
        mp3_path.unlink(missing_ok=True)


def rewrite_zip_cdg_wav_as_mp3(
    zip_path: Path, cdg: str, wav: str, final_name: str, backup: VerifiedBackup
) -> None:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)
    try:
        with zipfile.ZipFile(zip_path) as source:
            cdg_data = source.read(cdg)
            wav_path.write_bytes(source.read(wav))
        rewrite_zip_from_data(
            zip_path,
            [
                (f"{final_name}.cdg", cdg_data),
                (f"{final_name}.mp3", convert_wav_file_to_mp3_bytes(wav_path)),
            ],
            backup,
        )
    finally:
        wav_path.unlink(missing_ok=True)


def rewrite_zip_from_local_pair(
    zip_path: Path, cdg: Path, mp3: Path, final_name: str, backup: VerifiedBackup
) -> None:
    rewrite_zip_from_data(
        zip_path,
        [(f"{final_name}.cdg", cdg.read_bytes()), (f"{final_name}.mp3", mp3.read_bytes())],
        backup,
    )
