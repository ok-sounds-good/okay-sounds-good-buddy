"""Reusable media discovery, download, conversion, and staging mechanics."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .models import SongInfo
from .naming import code_regex, normalize_stem

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


def run(
    args: list[str], cwd: Path = REPOSITORY_ROOT, capture: bool = False
) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=str(cwd), check=True, text=True, capture_output=capture)


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required tool: {name}")


def youtube_metadata(url: str) -> dict:
    require_tool("yt-dlp")
    proc = run(["yt-dlp", "--dump-single-json", "--skip-download", url], capture=True)
    return json.loads(proc.stdout)


def audio_basename(info: SongInfo) -> str:
    return info.work_folder_name.replace("/", "-").replace(":", " -")


def find_best_audio_download(folder: Path, base: str) -> Path | None:
    candidates = [
        path
        for path in folder.glob(f"{base}.*")
        if path.is_file()
        and path.suffix.lower() not in {".mp3", ".part", ".ytdl"}
        and not path.name.endswith(".temp")
    ]
    return (
        sorted(candidates, key=lambda path: (path.stat().st_mtime, path.name), reverse=True)[0]
        if candidates
        else None
    )


def md5sum(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_annotated_mp3_path(folder: Path, base: str, annotation: str, candidate: Path) -> Path:
    first = folder / f"{base} - {annotation}.mp3"
    if not first.exists() or md5sum(first) == md5sum(candidate):
        return first
    idx = 2
    while True:
        path = folder / f"{base} - {annotation}-{idx}.mp3"
        if not path.exists() or md5sum(path) == md5sum(candidate):
            return path
        idx += 1


def create_midico_mp3(source: Path, folder: Path, base: str) -> Path:
    annotation = "48-kHz-stereo-libmp3lame-128k"
    target, tmp = folder / f"{base}.mp3", folder / f"{base}.tmp.mp3"
    if tmp.exists():
        tmp.unlink()
    try:
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-ar",
                "48000",
                "-ac",
                "2",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "128k",
                str(tmp),
            ]
        )
        if target.exists():
            if md5sum(target) == md5sum(tmp):
                tmp.unlink()
                return target
            annotated = unique_annotated_mp3_path(folder, base, annotation, tmp)
            if annotated.exists():
                tmp.unlink()
                return annotated
            tmp.replace(annotated)
            return annotated
        tmp.replace(target)
        return target
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise


def download_audio(url: str, folder: Path, info: SongInfo) -> tuple[Path, Path]:
    require_tool("yt-dlp")
    require_tool("ffmpeg")
    base = audio_basename(info)
    best_audio = find_best_audio_download(folder, base)
    if best_audio is None:
        run(["yt-dlp", "-f", "bestaudio/best", "-o", str(folder / f"{base}.%(ext)s"), url])
        best_audio = find_best_audio_download(folder, base)
    if best_audio is None:
        raise SystemExit(f"Expected best-audio download was not created for: {base}")
    return best_audio, create_midico_mp3(best_audio, folder, base)


def user_path(value: str, base: Path = Path.cwd()) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def unique_matches(folder: Path, suffix: str) -> list[Path]:
    return sorted(path for path in folder.rglob(f"*{suffix}") if path.is_file())


def validate_explicit_file(label: str, explicit: str, folder: Path, suffix: str) -> Path:
    path = user_path(explicit, base=folder)
    if not path.is_file():
        raise SystemExit(f"{label} not found: {path}")
    if path.suffix.lower() != suffix.lower():
        raise SystemExit(f"--{label} requires a {suffix} file: {path}")
    return path


def media_candidates(folder: Path, suffix: str) -> list[Path]:
    return unique_matches(folder, suffix)


def preferred_existing_mp4(
    folder: Path, final_name: str, code: str = "OKSG"
) -> tuple[Path | None, list[Path]]:
    preferred = folder / f"{final_name}.mp4"
    if preferred.exists():
        return preferred, []
    matches = unique_matches(folder, ".mp4")
    matcher = code_regex(code)
    code_match = matcher.search(final_name)
    if code_match:
        wanted_code = int(code_match.group(1))
        exact_code = [
            path
            for path in matches
            if matcher.search(path.name) and int(matcher.search(path.name).group(1)) == wanted_code
        ]
        if len(exact_code) == 1:
            return exact_code[0], []
    if len(matches) == 1:
        return matches[0], []
    return None, matches


def stage_mp4_for_final_name(source: Path, final_name: str, folder: Path) -> Path:
    dest = folder / f"{final_name}.mp4"
    if source.resolve() == dest.resolve():
        return dest
    if dest.exists():
        raise SystemExit(f"Refusing to overwrite existing MP4: {dest}")
    shutil.copy2(source, dest)
    return dest


def convert_mov_to_mp4(mov: Path, output: Path) -> None:
    require_tool("ffmpeg")
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing MP4: {output}")
    try:
        run(
            [
                "ffmpeg",
                "-i",
                str(mov),
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "60",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
    except BaseException:
        if output.exists():
            output.unlink()
        raise


def video_candidates_for(final_name: str, root: Path, code: str = "OKSG") -> list[Path]:
    wanted = normalize_stem(final_name)
    matcher = code_regex(code)
    code_match = matcher.search(final_name)
    release_code = code_match.group(1) if code_match else None
    all_videos = [
        path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    ]
    exact = [path for path in all_videos if normalize_stem(path.stem) == wanted]
    if exact:
        return sorted(exact, key=video_sort_key)
    if release_code:
        wanted_code = int(release_code)
        coded = [
            path
            for path in all_videos
            if matcher.search(str(path)) and int(matcher.search(str(path)).group(1)) == wanted_code
        ]
        if coded:
            return sorted(coded, key=video_sort_key)
    loose_map = {
        "OKSG-0002 - Gerard Way - Piano Jam (Ambulance)": ["GW-Piano-jam/GW-Piano-jam.mp4"],
        "OKSG-0003 - Hotelier - Your Deep Rest": ["YourDeepRest/video.mp4"],
        "OKSG-0004 - Prettiots - Suicide Hotline": [
            "The Prettiots - Suicide Hotline/Untitled Project.mp4"
        ],
        "OKSG-002 - Gerard Way - Piano Jam (Ambulance)": ["GW-Piano-jam/GW-Piano-jam.mp4"],
        "OKSG-003 - The Hotelier - Your Deep Rest": ["YourDeepRest/video.mp4"],
        "OKSG-004 - The Prettiots - Suicide Hotline": [
            "The Prettiots - Suicide Hotline/Untitled Project.mp4"
        ],
    }
    return [root / path for path in loose_map.get(final_name, []) if (root / path).exists()]


def video_sort_key(path: Path) -> tuple[int, int, str]:
    ext_rank = {".mp4": 0, ".m4v": 1, ".mov": 2, ".avi": 3, ".mkv": 4}
    return (ext_rank.get(path.suffix.lower(), 9), len(path.parts), str(path))


def convert_video_to_shared_mp4(source: Path, dest: Path) -> None:
    require_tool("ffmpeg")
    if dest.exists():
        raise SystemExit(f"Refusing to overwrite existing MP4: {dest}")
    try:
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "60",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                "-f",
                "mp4",
                str(dest),
            ]
        )
    except BaseException:
        if dest.exists():
            dest.unlink()
        raise
