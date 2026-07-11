"""Package-native OKSG command-line interface."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .commands import (
    audit_shared,
    configure,
    doctor,
    finish_song,
    install_shim,
    new_song,
    normalize_shared,
    repair_shared_videos,
    repair_shared_zips,
    thumbnail,
)
from .config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from .thumbnails import THUMBNAIL_STYLES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oksg",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Helpers for Okay, Sounds Good Karaoke song prep and packaging.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Configuration TOML path (default: repository .config.toml).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def fonts(c):
        c.add_argument(
            "--font", help="Font for all thumbnail text; accepts a path or installed font name."
        )
        c.add_argument(
            "--font.release",
            "--font-release",
            dest="font_release",
            help="Font for the band and song.",
        )
        c.add_argument(
            "--font.band", "--font-band", dest="font_band", help="Font for the band name."
        )
        c.add_argument(
            "--font.song", "--font-song", dest="font_song", help="Font for the song title."
        )
        c.add_argument(
            "--font.banner", "--font-banner", dest="font_banner", help="Font for the OKSG banner."
        )

    n = sub.add_parser(
        "new-song",
        help="Create a song workspace, thumbnail, checklist, and source audio.",
        description="Create a working folder from a YouTube source and prepare its first assets.",
    )
    n.add_argument("--url", required=True, help="YouTube URL for the source recording.")
    n.add_argument("--artist", help="Artist name; skips artist detection from YouTube metadata.")
    n.add_argument("--song", help="Song title; skips title detection from YouTube metadata.")
    n.add_argument(
        "--folder",
        help="Working-folder name under the Karaoke directory. Defaults to 'Artist - Song'.",
    )
    n.add_argument(
        "--number", type=int, help="OKSG release number. Defaults to the next number found locally."
    )
    n.add_argument(
        "--thumbnail-style",
        choices=list(THUMBNAIL_STYLES),
        default="retro",
        help="Initial Thumbnail.png style. Default: retro.",
    )
    fonts(n)
    n.add_argument(
        "--no-download",
        action="store_true",
        help="Create the folder and thumbnail without downloading source audio.",
    )
    t = sub.add_parser(
        "thumbnail",
        help="Generate one or all thumbnail styles.",
        description="Create Retro, Classic, and Typewriter thumbnails for a song.",
    )
    t.add_argument("--artist", help="Artist name. Required unless --url supplies usable metadata.")
    t.add_argument("--song", help="Song title. Required unless --url supplies usable metadata.")
    t.add_argument("--url", help="Optional YouTube URL used to identify the artist and song.")
    t.add_argument(
        "--folder",
        help="Destination folder. Defaults to 'Artist - Song' under the Karaoke directory.",
    )
    t.add_argument("--output", help="Output path for one style. Requires --style.")
    t.add_argument("--style", choices=list(THUMBNAIL_STYLES), help="Generate only one style.")
    fonts(t)
    f = sub.add_parser(
        "finish-song",
        help="Package CDG/MP3 and/or prepare a release MP4.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Package a finished song and write YouTube upload notes. By default, outputs are copied to the shared folder.",
        epilog="MP4-only example:\n  oksg finish-song --folder . --artist 'Band' --song 'Song' --number 25 --mp4-only\n\nWithout --mp4-only, an MP3 and CDG are required to build the karaoke ZIP. The command searches the folder when a file option is omitted, and asks you to choose if it finds more than one candidate.",
    )
    f.add_argument(
        "--folder",
        required=True,
        help="Song working folder to search for inputs and write outputs. Use '.' for the current folder.",
    )
    f.add_argument(
        "--artist",
        help="Artist for release and YouTube names. Defaults to parsing the folder name.",
    )
    f.add_argument(
        "--song",
        help="Song title for release and YouTube names. Defaults to parsing the folder name.",
    )
    f.add_argument(
        "--number", type=int, help="OKSG release number. Defaults to the next number found locally."
    )
    f.add_argument(
        "--mp3",
        help="Instrumental MP3 for the CDG ZIP. Auto-detected when exactly one MP3 exists; not needed with --mp4-only.",
    )
    f.add_argument(
        "--cdg",
        help="CDG graphics file for the CDG ZIP. Auto-detected when exactly one CDG exists; not needed with --mp4-only.",
    )
    f.add_argument(
        "--mp4",
        help="Existing video to release. It is renamed/copied to the final OKSG MP4 name. Use when multiple MP4s exist.",
    )
    f.add_argument(
        "--mov", help="MidiCo MOV export to convert to MP4 when no release MP4 is available."
    )
    f.add_argument(
        "--mp4-only",
        action="store_true",
        help="Skip CDG/MP3 ZIP packaging. Finish only an existing MP4 or converted MOV.",
    )
    f.add_argument(
        "--dry-run",
        action="store_true",
        help="Show discovered inputs and planned outputs without creating or copying files.",
    )
    f.add_argument(
        "--no-copy-to-shared",
        dest="copy_to_shared",
        action="store_false",
        help="Keep finished files in the working folder instead of copying them to the shared folder.",
    )
    f.set_defaults(copy_to_shared=True)
    repair = sub.add_parser(
        "repair-shared-zips",
        help="Repair CDG ZIP contents in the shared folder.",
        description="Remove extra files from shared CDG ZIPs and restore valid CDG/MP3 pairs.",
    )
    repair.add_argument("--shared-folder", help="Defaults to ../OKSG Karaoke if mounted locally.")
    repair.add_argument(
        "--dry-run", action="store_true", help="Show repairs without changing ZIP files."
    )
    repair_videos = sub.add_parser(
        "repair-shared-videos",
        help="Restore missing shared MP4 siblings.",
        description="Find local video exports for ZIP releases that are missing their shared MP4.",
    )
    repair_videos.add_argument(
        "--shared-folder", help="Defaults to the mounted OKSG Karaoke shared folder."
    )
    repair_videos.add_argument(
        "--dry-run",
        action="store_true",
        help="Show possible restores without copying or converting videos.",
    )
    audit = sub.add_parser(
        "audit-shared",
        help="Check shared naming and release completeness.",
        description="Report shared ZIP and MP4 releases, ZIP contents, and Harley-style naming problems.",
    )
    audit.add_argument(
        "--shared-folder", help="Defaults to the mounted OKSG Karaoke shared folder."
    )
    normalize = sub.add_parser(
        "normalize-shared-names",
        help="Rename shared releases to Harley style.",
        description="Rename shared ZIP/MP4 files and matching ZIP members to the Harley naming convention.",
    )
    normalize.add_argument(
        "--shared-folder", help="Defaults to the mounted OKSG Karaoke shared folder."
    )
    normalize.add_argument(
        "--dry-run", action="store_true", help="Show the rename plan without changing any files."
    )
    for name in ("configure", "doctor", "install-shim"):
        sub.add_parser(name, help=f"Run {name}.")
    for command in sub.choices.values():
        command.add_argument(
            "--config", type=Path, default=argparse.SUPPRESS, help=argparse.SUPPRESS
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    args = build_parser().parse_args(argv)
    if args.command == "configure":
        return configure.run(path=args.config)
    if args.command == "doctor":
        return doctor.run(path=args.config)
    if args.command == "install-shim":
        return install_shim.run()
    try:
        config = load_config(args.config)
        d = vars(args).copy()
        d.pop("command")
        d.pop("config")
        if args.command == "new-song":
            new_song.run(config=config, options=new_song.NewSongOptions(**d))
        elif args.command == "thumbnail":
            thumbnail.run(config=config, options=thumbnail.ThumbnailOptions(**d))
        elif args.command == "finish-song":
            finish_song.run(config=config, options=finish_song.FinishSongOptions(**d))
        elif args.command == "audit-shared":
            audit_shared.run(config=config, options=audit_shared.AuditSharedOptions(**d))
        elif args.command == "normalize-shared-names":
            normalize_shared.run(
                config=config, options=normalize_shared.NormalizeSharedOptions(**d)
            )
        elif args.command == "repair-shared-zips":
            repair_shared_zips.run(
                config=config, options=repair_shared_zips.RepairSharedZipsOptions(**d)
            )
        elif args.command == "repair-shared-videos":
            repair_shared_videos.run(
                config=config, options=repair_shared_videos.RepairSharedVideosOptions(**d)
            )
    except ConfigError as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"Command failed: {' '.join(exc.cmd)}", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        return exc.returncode
    return 0
