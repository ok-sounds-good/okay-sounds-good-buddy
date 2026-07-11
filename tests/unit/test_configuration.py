from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from oksg_buddy import archives, config, naming, thumbnails
from oksg_buddy.commands import configure as setup
from oksg_buddy.commands import normalize_shared
from oksg_buddy.models import OksgConfig, SongInfo


class ConfigurationTests(unittest.TestCase):
    def test_load_config_reports_missing_and_invalid_toml(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            with self.assertRaisesRegex(config.ConfigError, "Configuration not found"):
                config.load_config(path)
            path.write_text("[workspace\n", encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError, "Invalid TOML"):
                config.load_config(path)

    def test_validation_aggregates_schema_asset_and_path_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_logo = Path(directory) / "missing-logo.png"
            missing_fonts = Path(directory) / "missing-fonts"
            with self.assertRaises(config.ConfigError) as raised:
                config.validate_config_data(
                    {
                        "workspace": {
                            "karaoke_root": "relative",
                            "shared_folder": "",
                            "repair_backup_dir": "also-relative",
                        },
                        "branding": {"creator_code": "bad!", "creator_name": ""},
                        "assets": {
                            "logo_path": str(missing_logo),
                            "font_dirs": [str(missing_fonts)],
                        },
                    },
                    require_existing=False,
                )
            message = str(raised.exception)
            for expected in (
                "karaoke_root must be absolute",
                "shared_folder must be an absolute path",
                "repair_backup_dir must be absolute",
                "creator_code",
                "creator_name",
                "logo_path",
                "font_dirs",
            ):
                self.assertIn(expected, message)

    def test_writable_backup_probe_succeeds_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "Backups"
            backup.mkdir()
            self.assertTrue(config.probe_writable_directory(backup))
            self.assertEqual(list(backup.iterdir()), [])

    def test_writable_backup_probe_rejects_create_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "Backups"
            backup.mkdir()
            with mock.patch.object(Path, "open", side_effect=OSError("create failed")):
                self.assertFalse(config.probe_writable_directory(backup))
            self.assertEqual(list(backup.iterdir()), [])

    def test_writable_backup_probe_preserves_existing_collision_file(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "Backups"
            backup.mkdir()
            probe = backup / ".oksg-write-probe-fixed"
            probe.write_bytes(b"existing")
            with mock.patch.object(config.uuid, "uuid4", return_value=SimpleNamespace(hex="fixed")):
                self.assertFalse(config.probe_writable_directory(backup))
            self.assertEqual(probe.read_bytes(), b"existing")

    def test_writable_backup_probe_cleans_up_after_write_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "Backups"
            backup.mkdir()

            class FailingFile:
                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def write(self, _data):
                    raise OSError("write failed")

            probe = backup / ".oksg-write-probe-fixed"

            def open_and_fail(*_args, **_kwargs):
                probe.touch()
                return FailingFile()

            with (
                mock.patch.object(config.uuid, "uuid4", return_value=SimpleNamespace(hex="fixed")),
                mock.patch.object(Path, "open", side_effect=open_and_fail),
            ):
                self.assertFalse(config.probe_writable_directory(backup))
            self.assertEqual(list(backup.iterdir()), [])

    def test_writable_backup_probe_cleans_up_after_fsync_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "Backups"
            backup.mkdir()
            file = mock.MagicMock()
            file.__enter__.return_value = file
            file.__exit__.return_value = False
            file.fileno.return_value = 42

            probe = backup / ".oksg-write-probe-fixed"

            def open_and_return(*_args, **_kwargs):
                probe.touch()
                return file

            with (
                mock.patch.object(config.uuid, "uuid4", return_value=SimpleNamespace(hex="fixed")),
                mock.patch.object(Path, "open", side_effect=open_and_return),
                mock.patch.object(config.os, "fsync", side_effect=OSError("fsync failed")),
            ):
                self.assertFalse(config.probe_writable_directory(backup))
            self.assertEqual(list(backup.iterdir()), [])

    def test_writable_backup_probe_cleans_up_after_close_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "Backups"
            backup.mkdir()
            file = mock.MagicMock()
            file.__enter__.return_value = file
            file.__exit__.side_effect = OSError("close failed")
            file.fileno.return_value = 42
            probe = backup / ".oksg-write-probe-fixed"

            def open_and_return(*_args, **_kwargs):
                probe.touch()
                return file

            with (
                mock.patch.object(config.uuid, "uuid4", return_value=SimpleNamespace(hex="fixed")),
                mock.patch.object(Path, "open", side_effect=open_and_return),
            ):
                self.assertFalse(config.probe_writable_directory(backup))
            self.assertEqual(list(backup.iterdir()), [])

    def test_writable_backup_probe_rejects_cleanup_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "Backups"
            backup.mkdir()
            probe = backup / ".oksg-write-probe-fixed"
            with (
                mock.patch.object(config.uuid, "uuid4", return_value=SimpleNamespace(hex="fixed")),
                mock.patch.object(Path, "unlink", side_effect=OSError("delete failed")),
            ):
                self.assertFalse(config.probe_writable_directory(backup))
            self.assertTrue(probe.exists())
            probe.unlink()

    def test_configure_defaults_backup_to_repository_local_directory(self):
        defaults = []

        def fake_prompt(label, default="", **_kwargs):
            defaults.append((label, default))
            return default or "/tmp/oksg-test"

        with (
            mock.patch.object(setup, "prompt_path", side_effect=fake_prompt),
            mock.patch("builtins.input", side_effect=["", "", "", "", "n"]),
        ):
            self.assertEqual(setup.run(path=Path("/tmp/oksg-test-config.toml")), 1)
        self.assertEqual(defaults[2][1], str(config.REPOSITORY_ROOT / ".repair-backups"))

    def test_creator_code_validation_and_release_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Karaoke"
            shared = Path(directory) / "Shared"
            backup = Path(directory) / "Backups"
            root.mkdir()
            shared.mkdir()
            backup.mkdir()
            loaded = config.validate_config_data(
                {
                    "workspace": {
                        "karaoke_root": str(root),
                        "shared_folder": str(shared),
                        "repair_backup_dir": str(backup),
                    },
                    "branding": {"creator_code": "ab12", "creator_name": "Creator"},
                    "assets": {"logo_path": "", "font_dirs": []},
                }
            )
            self.assertEqual(loaded.creator_code, "AB12")
            self.assertEqual(
                naming.release_name(SongInfo("Band", "Song"), 7, loaded.creator_code),
                "AB12-0007 - Band - Song",
            )
            self.assertEqual(
                naming.parse_shared_stem("AB12-007 - Band - Song", loaded.creator_code).number, 7
            )
            self.assertIsNone(
                naming.parse_shared_stem("AB12-00007 - Band - Song", loaded.creator_code)
            )

    def test_backup_directory_must_be_outside_shared_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Karaoke"
            shared = Path(directory) / "Shared"
            root.mkdir()
            shared.mkdir()
            with self.assertRaisesRegex(config.ConfigError, "outside shared_folder"):
                config.validate_config_data(
                    {
                        "workspace": {
                            "karaoke_root": str(root),
                            "shared_folder": str(shared),
                            "repair_backup_dir": str(shared / "backups"),
                        },
                        "branding": {"creator_code": "OKSG", "creator_name": "Creator"},
                    },
                    require_existing=False,
                )

    def test_normalize_backs_up_zip_before_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root, shared, backup = (base / name for name in ("Karaoke", "Shared", "Backups"))
            root.mkdir()
            shared.mkdir()
            backup.mkdir()
            old = "AB12-001 - The Band - the song"
            with zipfile.ZipFile(shared / f"{old}.zip", "w") as archive:
                archive.writestr(f"{old}.cdg", b"cdg")
                archive.writestr(f"{old}.mp3", b"mp3")
            loaded = OksgConfig(root, shared, backup, "AB12", "Creator", None, ())
            options = normalize_shared.NormalizeSharedOptions(dry_run=True)
            with mock.patch.object(archives, "backup_zip_for_repair") as backup_mock:
                # Dry-run intentionally does not create backups.
                normalize_shared.run(config=loaded, options=options)
                backup_mock.assert_not_called()
            options = normalize_shared.NormalizeSharedOptions()
            with mock.patch.object(
                archives, "backup_zip_for_repair", wraps=archives.backup_zip_for_repair
            ) as backup_mock:
                normalize_shared.run(config=loaded, options=options)
                backup_mock.assert_called_once_with(shared / f"{old}.zip", loaded)

    def test_empty_configured_logo_does_not_use_legacy_repository_logo(self):
        with tempfile.TemporaryDirectory() as directory:
            configured = OksgConfig(
                Path(directory),
                Path(directory),
                Path(directory).parent,
                "OKSG",
                "Creator",
                None,
                (),
            )
            self.assertIsNone(thumbnails.find_logo_base(configured))

    def test_configured_font_directory_precedes_platform_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            font = Path(directory) / "Creator.ttf"
            font.write_bytes(b"font")
            candidates = thumbnails.default_font_candidates(False, (Path(directory),))
            self.assertEqual(candidates[0], font)

    def test_setup_rejects_existing_file_as_backup_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "Karaoke"
            shared = base / "Shared"
            backup = base / "backup-file"
            root.mkdir()
            shared.mkdir()
            backup.write_text("not a directory")
            values = {
                "karaoke_root": str(root),
                "shared_folder": str(shared),
                "repair_backup_dir": str(backup),
                "creator_code": "OKSG",
                "creator_name": "Creator",
                "logo_path": "",
                "font_dirs": [],
            }
            with self.assertRaisesRegex(config.ConfigError, "missing or not writable"):
                setup.config_from_values(values, require_existing=True)

    @unittest.skipIf(os.name == "nt", "POSIX permission test")
    def test_setup_rejects_non_writable_backup_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "Karaoke"
            shared = base / "Shared"
            backup = base / "Backups"
            root.mkdir()
            shared.mkdir()
            backup.mkdir()
            backup.chmod(0o500)
            try:
                values = {
                    "karaoke_root": str(root),
                    "shared_folder": str(shared),
                    "repair_backup_dir": str(backup),
                    "creator_code": "OKSG",
                    "creator_name": "Creator",
                    "logo_path": "",
                    "font_dirs": [],
                }
                with mock.patch.object(config, "probe_writable_directory", return_value=False):
                    with self.assertRaisesRegex(config.ConfigError, "missing or not writable"):
                        setup.config_from_values(values, require_existing=True)
            finally:
                backup.chmod(0o700)
