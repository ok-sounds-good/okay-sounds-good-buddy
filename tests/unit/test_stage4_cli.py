from __future__ import annotations

import ast
import dataclasses
import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path, PurePosixPath
from unittest import mock

from oksg_buddy import cli
from oksg_buddy.commands import configure, doctor, finish_song, install_shim, new_song, thumbnail

REPO = Path(__file__).resolve().parents[2]
COMMANDS = REPO / "src/oksg_buddy/commands"


class Stage4CliTests(unittest.TestCase):
    def test_parser_preserves_pre_stage4_help_content(self):
        parser = cli.build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, cli.argparse._SubParsersAction)
        )
        finish = subparsers.choices["finish-song"]
        finish_help = {
            option: action.help for action in finish._actions for option in action.option_strings
        }
        self.assertEqual(
            finish.description,
            "Package a finished song and write YouTube upload notes. By default, outputs are copied to the shared folder.",
        )
        self.assertEqual(
            finish.epilog,
            "MP4-only example:\n  oksg finish-song --folder . --artist 'Band' --song 'Song' --number 25 --mp4-only\n\nWithout --mp4-only, an MP3 and CDG are required to build the karaoke ZIP. The command searches the folder when a file option is omitted, and asks you to choose if it finds more than one candidate.",
        )
        expected_finish = {
            "--artist": "Artist for release and YouTube names. Defaults to parsing the folder name.",
            "--song": "Song title for release and YouTube names. Defaults to parsing the folder name.",
            "--number": "OKSG release number. Defaults to the next number found locally.",
            "--mp3": "Instrumental MP3 for the CDG ZIP. Auto-detected when exactly one MP3 exists; not needed with --mp4-only.",
            "--cdg": "CDG graphics file for the CDG ZIP. Auto-detected when exactly one CDG exists; not needed with --mp4-only.",
            "--mp4": "Existing video to release. It is renamed/copied to the final OKSG MP4 name. Use when multiple MP4s exist.",
            "--mov": "MidiCo MOV export to convert to MP4 when no release MP4 is available.",
            "--dry-run": "Show discovered inputs and planned outputs without creating or copying files.",
            "--no-copy-to-shared": "Keep finished files in the working folder instead of copying them to the shared folder.",
        }
        for option, expected in expected_finish.items():
            self.assertEqual(finish_help[option], expected)

        expected_commands = {
            "repair-shared-zips": (
                "Remove extra files from shared CDG ZIPs and restore valid CDG/MP3 pairs.",
                {
                    "--shared-folder": "Defaults to ../OKSG Karaoke if mounted locally.",
                    "--dry-run": "Show repairs without changing ZIP files.",
                },
            ),
            "repair-shared-videos": (
                "Find local video exports for ZIP releases that are missing their shared MP4.",
                {
                    "--shared-folder": "Defaults to the mounted OKSG Karaoke shared folder.",
                    "--dry-run": "Show possible restores without copying or converting videos.",
                },
            ),
            "audit-shared": (
                "Report shared ZIP and MP4 releases, ZIP contents, and Harley-style naming problems.",
                {"--shared-folder": "Defaults to the mounted OKSG Karaoke shared folder."},
            ),
            "normalize-shared-names": (
                "Rename shared ZIP/MP4 files and matching ZIP members to the Harley naming convention.",
                {
                    "--shared-folder": "Defaults to the mounted OKSG Karaoke shared folder.",
                    "--dry-run": "Show the rename plan without changing any files.",
                },
            ),
        }
        command_help = {choice.dest: choice.help for choice in subparsers._choices_actions}
        self.assertEqual(
            command_help["repair-shared-zips"], "Repair CDG ZIP contents in the shared folder."
        )
        self.assertEqual(
            command_help["repair-shared-videos"], "Restore missing shared MP4 siblings."
        )
        self.assertEqual(
            command_help["audit-shared"], "Check shared naming and release completeness."
        )
        self.assertEqual(
            command_help["normalize-shared-names"], "Rename shared releases to Harley style."
        )
        for command, (description, expected_options) in expected_commands.items():
            command_parser = subparsers.choices[command]
            self.assertEqual(command_parser.description, description)
            option_help = {
                option: action.help
                for action in command_parser._actions
                for option in action.option_strings
            }
            for option, expected in expected_options.items():
                self.assertEqual(option_help[option], expected)

    def test_large_command_options_are_frozen(self):
        instances = (
            new_song.NewSongOptions("u"),
            finish_song.FinishSongOptions("."),
            thumbnail.ThumbnailOptions(),
        )
        for instance in instances:
            cls = type(instance)
            self.assertTrue(cls.__dataclass_params__.frozen)
            with self.assertRaises(dataclasses.FrozenInstanceError):
                instance.x = 1

    def test_cli_dispatches_explicit_frozen_options(self):
        config = mock.Mock()
        with (
            mock.patch.object(cli, "load_config", return_value=config),
            mock.patch.object(new_song, "run") as run,
        ):
            self.assertEqual(
                cli.main(
                    ["new-song", "--url", "u", "--artist", "A", "--song", "S", "--no-download"]
                ),
                0,
            )
        run.assert_called_once()
        self.assertIs(run.call_args.kwargs["config"], config)
        self.assertEqual(run.call_args.kwargs["options"].artist, "A")

    def test_no_command_imports_another_command_and_utilities_do_not_import_commands(self):
        for path in COMMANDS.glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn("commands", node.module or "", path.name)
        for path in (REPO / "src/oksg_buddy").glob("*.py"):
            if path.name == "cli.py":
                continue
            self.assertNotIn(".commands", path.read_text(), path.name)

    def test_root_python_bridges_are_absent(self):
        self.assertFalse((REPO / "oksg.py").exists())
        self.assertFalse((REPO / "setup.py").exists())
        self.assertFalse((REPO / "src/oksg_buddy/workflows.py").exists())

    def test_doctor_reports_missing_and_malformed_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(doctor.run(path=path), 1)
            self.assertIn("Configuration not found", output.getvalue())
            path.write_text("[broken\n")
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(doctor.run(path=path), 1)
            self.assertIn("Invalid TOML", output.getvalue())

    def test_configure_recovers_from_malformed_config(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            shared = base / "shared"
            backup = base / "backup"
            root.mkdir()
            shared.mkdir()
            path = base / "config.toml"
            path.write_text("[bad\n")
            with (
                mock.patch.object(
                    configure, "prompt_path", side_effect=[str(root), str(shared), str(backup)]
                ),
                mock.patch("builtins.input", side_effect=["OKSG", "Creator", "", "", "y", "y"]),
            ):
                self.assertEqual(configure.run(path=path), 0)
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_posix_and_windows_shims_target_console_entrypoints_with_spaces(self):
        repo = PurePosixPath("/tmp/Repo With Spaces")
        posix = install_shim.shim_content(repo, windows=False)
        windows = install_shim.shim_content(repo, windows=True)
        self.assertIn(".venv/bin/oksg", posix)
        self.assertNotIn("python", posix)
        self.assertIn('"/tmp/Repo With Spaces\\.venv\\Scripts\\oksg.exe"', windows)
        self.assertNotIn("oksg.py", windows)

    @unittest.skipIf(os.name == "nt", "POSIX launcher execution is not supported on Windows")
    def test_posix_shim_installs_and_executes_console_entrypoint(self):
        with (
            tempfile.TemporaryDirectory(prefix="oksg repo ") as repo_dir,
            tempfile.TemporaryDirectory() as home_dir,
        ):
            repo = Path(repo_dir)
            entrypoint = repo / ".venv/bin/oksg"
            entrypoint.parent.mkdir(parents=True)
            entrypoint.write_text("#!/bin/sh\nprintf 'entrypoint:%s\\n' \"$1\"\n", encoding="utf-8")
            entrypoint.chmod(0o755)
            with mock.patch("builtins.input", return_value="y"):
                self.assertEqual(install_shim.run(repo=repo, home=Path(home_dir), windows=False), 0)
            shim = Path(home_dir) / ".local/bin/oksg"
            result = subprocess.run(
                [shim, "hello world"], text=True, capture_output=True, check=True
            )
            self.assertEqual(result.stdout, "entrypoint:hello world\n")

    def test_setup_scripts_invoke_package_commands(self):
        for name in ("setup.sh", "setup.ps1"):
            text = (REPO / name).read_text()
            self.assertIn("uv run oksg configure", text)
            self.assertIn("uv run oksg install-shim", text)
            self.assertNotIn("setup.py", text)

    def test_three_help_entrypoints_are_equivalent(self):
        env = {**os.environ, "UV_CACHE_DIR": "/tmp/oksg-uv-cache"}
        commands = [
            ["uv", "run", "oksg", "--help"],
            ["uv", "run", "python", "-m", "oksg_buddy", "--help"],
        ]
        if os.name != "nt":
            commands.append([str(REPO / "oksg"), "--help"])
        outputs = [
            subprocess.run(c, cwd=REPO, env=env, text=True, capture_output=True, check=True).stdout
            for c in commands
        ]
        self.assertEqual(outputs[0], outputs[1])
        if os.name != "nt":
            self.assertEqual(outputs[0], outputs[2])


if __name__ == "__main__":
    unittest.main()
