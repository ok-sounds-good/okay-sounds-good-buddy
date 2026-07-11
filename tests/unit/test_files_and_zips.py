from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from oksg_buddy import archives, media
from oksg_buddy.commands import finish_song
from oksg_buddy.models import OksgConfig
from tests.support import temporary_project


class FileSelectionTests(unittest.TestCase):
    def test_youtube_metadata_preserves_yt_dlp_arguments(self):
        completed = mock.Mock(stdout='{"title": "Band - Song"}')
        with (
            mock.patch.object(media, "require_tool") as require,
            mock.patch.object(media, "run", return_value=completed) as run,
        ):
            self.assertEqual(
                media.youtube_metadata("https://example.invalid/video")["title"], "Band - Song"
            )
        require.assert_called_once_with("yt-dlp")
        run.assert_called_once_with(
            ["yt-dlp", "--dump-single-json", "--skip-download", "https://example.invalid/video"],
            capture=True,
        )

    def test_download_audio_preserves_downloader_arguments_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            downloaded = folder / "Band - Song.webm"

            def fake_run(args, cwd=media.REPOSITORY_ROOT, capture=False):
                downloaded.write_bytes(b"audio")
                return mock.Mock()

            with (
                mock.patch.object(media, "require_tool"),
                mock.patch.object(media, "run", side_effect=fake_run) as run,
                mock.patch.object(
                    media, "create_midico_mp3", return_value=folder / "Band - Song.mp3"
                ),
            ):
                self.assertEqual(
                    media.download_audio(
                        "https://example.invalid/video", folder, media.SongInfo("Band", "Song")
                    )[0],
                    downloaded,
                )
            self.assertEqual(
                run.call_args.args[0],
                [
                    "yt-dlp",
                    "-f",
                    "bestaudio/best",
                    "-o",
                    str(folder / "Band - Song.%(ext)s"),
                    "https://example.invalid/video",
                ],
            )

    def test_choose_file_requires_disambiguation(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "a.mp3").write_bytes(b"a")
            (folder / "b.mp3").write_bytes(b"b")
            with self.assertRaisesRegex(SystemExit, "Pass --mp3 to choose one"):
                finish_song.choose_file("mp3", None, folder, ".mp3", required=True)

    def test_choose_existing_mp4_prefers_exact_release_name(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            final_name = "OKSG-0025 - Band - Song"
            wanted = folder / f"{final_name}.mp4"
            wanted.write_bytes(b"final")
            (folder / "other.mp4").write_bytes(b"other")
            self.assertEqual(media.preferred_existing_mp4(folder, final_name)[0], wanted)

    def test_explicit_media_paths_must_match_the_requested_file_type(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            wrong_audio = folder / "audio.wav"
            wrong_video = folder / "video.mov"
            wrong_audio.write_bytes(b"audio")
            wrong_video.write_bytes(b"video")
            with self.assertRaisesRegex(SystemExit, "mp3"):
                media.validate_explicit_file("mp3", str(wrong_audio), folder, ".mp3")
            with self.assertRaisesRegex(SystemExit, "mp4"):
                media.validate_explicit_file("mp4", str(wrong_video), folder, ".mp4")

    def test_stage_mp4_refuses_to_replace_existing_release(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "export.mp4"
            source.write_bytes(b"new")
            (folder / "OKSG-0001 - Band - Song.mp4").write_bytes(b"old")
            with self.assertRaisesRegex(SystemExit, "Refusing to overwrite"):
                media.stage_mp4_for_final_name(source, "OKSG-0001 - Band - Song", folder)

    def test_unique_annotated_mp3_path_skips_distinct_existing_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            candidate = folder / "candidate.mp3"
            candidate.write_bytes(b"new")
            (folder / "Band - Song - converted.mp3").write_bytes(b"old")
            (folder / "Band - Song - converted-2.mp3").write_bytes(b"older")
            self.assertEqual(
                media.unique_annotated_mp3_path(folder, "Band - Song", "converted", candidate),
                folder / "Band - Song - converted-3.mp3",
            )

    def test_mov_conversion_cleans_partial_output_and_propagates_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source, output = folder / "video.mov", folder / "video.mp4"
            source.write_bytes(b"mov")

            def fail(args, cwd=media.REPOSITORY_ROOT, capture=False):
                output.write_bytes(b"partial")
                raise OSError("conversion failed")

            with (
                mock.patch.object(media, "require_tool"),
                mock.patch.object(media, "run", side_effect=fail),
            ):
                with self.assertRaisesRegex(OSError, "conversion failed"):
                    media.convert_mov_to_mp4(source, output)
            self.assertFalse(output.exists())

    def test_mov_conversion_preserves_ffmpeg_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "video.mov", Path(directory) / "video.mp4"
            source.write_bytes(b"mov")
            with mock.patch.object(media, "require_tool"), mock.patch.object(media, "run") as run:
                media.convert_mov_to_mp4(source, output)
            self.assertEqual(run.call_args.args[0][0:3], ["ffmpeg", "-i", str(source)])
            self.assertEqual(run.call_args.args[0][-1], str(output))

    def test_copy_to_shared_cleans_partial_temp_file_on_failure(self):
        with temporary_project() as project:
            source = project.root / "video.mp4"
            source.write_bytes(b"video")
            with mock.patch.object(finish_song.shutil, "copy2", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    finish_song.copy_to_shared(source, "mp4", project.config)
            self.assertFalse(list(project.shared.glob(".*.tmp")))
            self.assertFalse((project.shared / source.name).exists())

    def test_copy_to_shared_refuses_different_existing_mp4(self):
        with temporary_project() as project:
            source = project.root / "video.mp4"
            source.write_bytes(b"new video")
            destination = project.shared / source.name
            destination.write_bytes(b"old video")
            with self.assertRaisesRegex(SystemExit, "already exists"):
                finish_song.copy_to_shared(source, "mp4", project.config)
            self.assertEqual(destination.read_bytes(), b"old video")

    def test_copy_to_missing_shared_folder_fails_instead_of_skipping(self):
        with temporary_project() as project:
            project.shared.rmdir()
            source = project.root / "video.mp4"
            source.write_bytes(b"video")
            with self.assertRaisesRegex(SystemExit, "Shared folder not found"):
                finish_song.copy_to_shared(source, "mp4", project.config)


class ZipValidationTests(unittest.TestCase):
    def test_source_itself_cannot_serve_as_verified_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("release.cdg", b"cdg")
                archive.writestr("release.mp3", b"mp3")
            original = path.read_bytes()
            receipt = archives.VerifiedBackup(path, path, archives.sha256sum(path))

            with self.assertRaisesRegex(SystemExit, "verified backup is required"):
                archives.rewrite_zip_member_names(path, "renamed", receipt)

            self.assertEqual(path.read_bytes(), original)

    def test_backup_verification_failure_removes_created_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "release.zip"
            path.write_bytes(b"source")
            backup_dir = root / "backups"
            backup_dir.mkdir()
            config = OksgConfig(root, root, backup_dir, "OKSG", "OKSG", None, ())

            with mock.patch.object(
                archives, "sha256sum", side_effect=["source-hash", "different-hash"]
            ):
                with self.assertRaisesRegex(SystemExit, "Backup verification failed"):
                    archives.backup_zip_for_repair(path, config)

            self.assertEqual(list(backup_dir.iterdir()), [])

    def test_zip_audit_reports_missing_and_extra_members(self):
        statuses = archives.zip_member_audit_statuses(
            ["release.cdg", "notes.txt"],
            "release",
        )
        self.assertIn(("notes.txt", ["EXTRA FILE"]), statuses)
        self.assertIn(("release.mp3", ["MISSING MP3"]), statuses)

    def test_inspect_zip_rejects_mismatched_cdg_and_audio_stems(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("one.cdg", b"cdg")
                archive.writestr("two.mp3", b"mp3")
            with self.assertRaisesRegex(SystemExit, "base names do not match"):
                archives.inspect_cdg_zip_members(path)

    def test_rewrite_zip_member_names_keeps_only_named_cdg_and_mp3(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "release.zip"
            backup_dir = root / "backups"
            backup_dir.mkdir()
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("old.cdg", b"cdg")
                archive.writestr("old.mp3", b"mp3")
            config = OksgConfig(root, root, backup_dir, "OKSG", "OKSG", None, ())
            backup = archives.backup_zip_for_repair(path, config)
            archives.rewrite_zip_member_names(path, "OKSG-0001 - Band - Song", backup)
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(
                    sorted(archive.namelist()),
                    ["OKSG-0001 - Band - Song.cdg", "OKSG-0001 - Band - Song.mp3"],
                )
