from __future__ import annotations

import unittest
import zipfile
from pathlib import Path
from unittest import mock

from oksg_buddy import shared as shared_services
from oksg_buddy.commands import normalize_shared, repair_shared_zips
from tests.support import temporary_project


class SharedRepairIntegrationTests(unittest.TestCase):
    def test_repair_zip_extracts_embedded_mp4_and_removes_extra_member(self):
        with temporary_project() as project:
            final_name = "OKSG-0001 - Band - Song"
            zip_path = project.shared / f"{final_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{final_name}.cdg", b"cdg")
                archive.writestr(f"{final_name}.mp3", b"mp3")
                archive.writestr("export.mp4", b"video")

            options = repair_shared_zips.RepairSharedZipsOptions(str(project.shared))
            repair_shared_zips.run(config=project.config, options=options)

            with zipfile.ZipFile(zip_path) as archive:
                self.assertEqual(
                    sorted(archive.namelist()), [f"{final_name}.cdg", f"{final_name}.mp3"]
                )
            self.assertEqual((project.shared / f"{final_name}.mp4").read_bytes(), b"video")

    def test_repair_aborts_without_rewriting_zip_when_video_preservation_fails(self):
        with temporary_project() as project:
            final_name = "OKSG-0001 - Band - Song"
            zip_path = project.shared / f"{final_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{final_name}.cdg", b"cdg")
                archive.writestr(f"{final_name}.mp3", b"mp3")
                archive.writestr("export.mp4", b"video")
            original_zip = zip_path.read_bytes()

            options = repair_shared_zips.RepairSharedZipsOptions(str(project.shared))
            with mock.patch.object(
                shared_services,
                "restore_shared_mp4_from_zip_member",
                side_effect=OSError("drive unavailable"),
            ):
                with self.assertRaisesRegex(OSError, "drive unavailable"):
                    repair_shared_zips.run(config=project.config, options=options)

            self.assertEqual(zip_path.read_bytes(), original_zip)
            self.assertFalse((project.shared / f"{final_name}.mp4").exists())

    def test_repair_streams_embedded_mp4_to_staging_file_before_publishing(self):
        """The final sibling path must never be the ZIP extraction write target."""
        with temporary_project() as project:
            final_name = "OKSG-0001 - Band - Song"
            zip_path = project.shared / f"{final_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{final_name}.cdg", b"cdg")
                archive.writestr(f"{final_name}.mp3", b"mp3")
                archive.writestr("export.mp4", b"video")

            options = repair_shared_zips.RepairSharedZipsOptions(str(project.shared))
            with mock.patch.object(
                Path, "write_bytes", side_effect=AssertionError("direct Path.write_bytes is unsafe")
            ):
                repair_shared_zips.run(config=project.config, options=options)

            sibling = project.shared / f"{final_name}.mp4"
            self.assertEqual(sibling.read_bytes(), b"video")
            with zipfile.ZipFile(zip_path) as archive:
                self.assertEqual(
                    sorted(archive.namelist()), [f"{final_name}.cdg", f"{final_name}.mp3"]
                )

    def test_repair_cleans_staging_after_video_stream_failure(self):
        with temporary_project() as project:
            final_name = "OKSG-0001 - Band - Song"
            zip_path = project.shared / f"{final_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{final_name}.cdg", b"cdg")
                archive.writestr(f"{final_name}.mp3", b"mp3")
                archive.writestr("export.mp4", b"video")
            original_zip = zip_path.read_bytes()

            options = repair_shared_zips.RepairSharedZipsOptions(str(project.shared))
            with mock.patch.object(
                shared_services.shutil, "copyfileobj", side_effect=OSError("stream failed")
            ):
                with self.assertRaisesRegex(OSError, "stream failed"):
                    repair_shared_zips.run(config=project.config, options=options)

            self.assertEqual(zip_path.read_bytes(), original_zip)
            self.assertFalse((project.shared / f"{final_name}.mp4").exists())
            self.assertFalse(list(project.shared.glob(f".{final_name}.*")))

    def test_repair_cleans_staging_when_publish_fails(self):
        with temporary_project() as project:
            final_name = "OKSG-0001 - Band - Song"
            zip_path = project.shared / f"{final_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{final_name}.cdg", b"cdg")
                archive.writestr(f"{final_name}.mp3", b"mp3")
                archive.writestr("export.mp4", b"video")
            original_zip = zip_path.read_bytes()

            options = repair_shared_zips.RepairSharedZipsOptions(str(project.shared))
            with mock.patch.object(
                shared_services, "publish_new_shared_file", side_effect=OSError("rename failed")
            ):
                with self.assertRaisesRegex(OSError, "rename failed"):
                    repair_shared_zips.run(config=project.config, options=options)

            self.assertEqual(zip_path.read_bytes(), original_zip)
            self.assertFalse((project.shared / f"{final_name}.mp4").exists())
            self.assertFalse(list(project.shared.glob(f".{final_name}.*")))

    def test_repair_reports_unavailable_hard_links_without_rewriting_zip(self):
        with temporary_project() as project:
            final_name = "OKSG-0001 - Band - Song"
            zip_path = project.shared / f"{final_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{final_name}.cdg", b"cdg")
                archive.writestr(f"{final_name}.mp3", b"mp3")
                archive.writestr("export.mp4", b"video")
            original_zip = zip_path.read_bytes()

            options = repair_shared_zips.RepairSharedZipsOptions(str(project.shared))
            with mock.patch.object(
                shared_services.os, "link", side_effect=OSError("operation not supported")
            ):
                with self.assertRaisesRegex(SystemExit, "hard links are unavailable"):
                    repair_shared_zips.run(config=project.config, options=options)

            self.assertEqual(zip_path.read_bytes(), original_zip)
            self.assertFalse((project.shared / f"{final_name}.mp4").exists())
            self.assertFalse(list(project.shared.glob(f".{final_name}.*")))

    def test_repair_refuses_destination_that_appears_during_staging(self):
        with temporary_project() as project:
            final_name = "OKSG-0001 - Band - Song"
            zip_path = project.shared / f"{final_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{final_name}.cdg", b"cdg")
                archive.writestr(f"{final_name}.mp3", b"mp3")
                archive.writestr("export.mp4", b"video")
            original_zip = zip_path.read_bytes()
            sibling = project.shared / f"{final_name}.mp4"

            def stage_and_race(source, destination):
                destination.write(source.read())
                sibling.write_bytes(b"raced video")

            options = repair_shared_zips.RepairSharedZipsOptions(str(project.shared))
            original_copy = shared_services.shutil.copyfileobj

            def stage_zip_member_and_race(source, destination):
                if isinstance(source, zipfile.ZipExtFile):
                    return stage_and_race(source, destination)
                return original_copy(source, destination)

            with mock.patch.object(
                shared_services.shutil, "copyfileobj", side_effect=stage_zip_member_and_race
            ):
                with self.assertRaisesRegex(SystemExit, "Refusing to overwrite"):
                    repair_shared_zips.run(config=project.config, options=options)

            self.assertEqual(zip_path.read_bytes(), original_zip)
            self.assertEqual(sibling.read_bytes(), b"raced video")
            self.assertFalse(list(project.shared.glob(f".{final_name}.*.tmp")))

    def test_repair_cleans_source_and_output_staging_after_mov_conversion_failure(self):
        with temporary_project() as project:
            final_name = "OKSG-0001 - Band - Song"
            zip_path = project.shared / f"{final_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{final_name}.cdg", b"cdg")
                archive.writestr(f"{final_name}.mp3", b"mp3")
                archive.writestr("export.mov", b"mov")
            original_zip = zip_path.read_bytes()

            options = repair_shared_zips.RepairSharedZipsOptions(str(project.shared))
            with mock.patch.object(
                shared_services,
                "convert_video_to_shared_mp4",
                side_effect=OSError("conversion failed"),
            ):
                with self.assertRaisesRegex(OSError, "conversion failed"):
                    repair_shared_zips.run(config=project.config, options=options)

            self.assertEqual(zip_path.read_bytes(), original_zip)
            self.assertFalse((project.shared / f"{final_name}.mp4").exists())
            self.assertFalse(list(project.shared.glob(f".{final_name}.*")))

    def test_repair_converts_embedded_mov_into_published_sibling(self):
        with temporary_project() as project:
            final_name = "OKSG-0001 - Band - Song"
            zip_path = project.shared / f"{final_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{final_name}.cdg", b"cdg")
                archive.writestr(f"{final_name}.mp3", b"mp3")
                archive.writestr("export.mov", b"mov")

            def fake_convert(source, destination):
                self.assertTrue(source.name.endswith(".mov"))
                self.assertNotEqual(destination, project.shared / f"{final_name}.mp4")
                destination.write_bytes(b"converted video")

            options = repair_shared_zips.RepairSharedZipsOptions(str(project.shared))
            with mock.patch.object(
                shared_services, "convert_video_to_shared_mp4", side_effect=fake_convert
            ):
                repair_shared_zips.run(config=project.config, options=options)

            self.assertEqual(
                (project.shared / f"{final_name}.mp4").read_bytes(), b"converted video"
            )
            self.assertFalse(list(project.shared.glob(f".{final_name}.*")))

    def test_repair_preserves_an_existing_sibling_mp4_while_rewriting_zip(self):
        with temporary_project() as project:
            final_name = "OKSG-0001 - Band - Song"
            zip_path = project.shared / f"{final_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{final_name}.cdg", b"cdg")
                archive.writestr(f"{final_name}.mp3", b"mp3")
                archive.writestr("old-export.mp4", b"embedded video")
            sibling = project.shared / f"{final_name}.mp4"
            sibling.write_bytes(b"existing release video")

            options = repair_shared_zips.RepairSharedZipsOptions(str(project.shared))
            repair_shared_zips.run(config=project.config, options=options)

            self.assertEqual(sibling.read_bytes(), b"existing release video")
            with zipfile.ZipFile(zip_path) as archive:
                self.assertEqual(
                    sorted(archive.namelist()), [f"{final_name}.cdg", f"{final_name}.mp3"]
                )

    def test_repair_refuses_multiple_embedded_videos_without_changing_zip(self):
        with temporary_project() as project:
            final_name = "OKSG-0001 - Band - Song"
            zip_path = project.shared / f"{final_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{final_name}.cdg", b"cdg")
                archive.writestr(f"{final_name}.mp3", b"mp3")
                archive.writestr("export.mp4", b"video one")
                archive.writestr("alternate.mov", b"video two")
            original_zip = zip_path.read_bytes()

            options = repair_shared_zips.RepairSharedZipsOptions(str(project.shared))
            with self.assertRaisesRegex(SystemExit, "multiple embedded videos"):
                repair_shared_zips.run(config=project.config, options=options)

            self.assertEqual(zip_path.read_bytes(), original_zip)
            self.assertFalse((project.shared / f"{final_name}.mp4").exists())

    def test_repair_refuses_unexpected_archive_paths_without_changing_zip(self):
        unexpected_members = [
            "X.yx",
            "__MACOSX/metadata",
            "nested/OKSG-0001 - Band - Song.mp3",
            "../escape.mp3",
        ]
        for unexpected_member in unexpected_members:
            with self.subTest(unexpected_member=unexpected_member), temporary_project() as project:
                final_name = "OKSG-0001 - Band - Song"
                zip_path = project.shared / f"{final_name}.zip"
                with zipfile.ZipFile(zip_path, "w") as archive:
                    archive.writestr(f"{final_name}.cdg", b"cdg")
                    archive.writestr(f"{final_name}.mp3", b"mp3")
                    archive.writestr(unexpected_member, b"unexpected")
                original_zip = zip_path.read_bytes()

                options = repair_shared_zips.RepairSharedZipsOptions(str(project.shared))
                failed_loudly = False
                try:
                    repair_shared_zips.run(config=project.config, options=options)
                except SystemExit:
                    failed_loudly = True

                self.assertEqual(zip_path.read_bytes(), original_zip)
                self.assertTrue(failed_loudly, "unexpected ZIP members must be rejected")

    def test_normalize_refuses_hidden_archive_metadata_without_changing_zip(self):
        with temporary_project() as project:
            old_name = "OKSG-012 - The Hotelier - song title"
            zip_path = project.shared / f"{old_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{old_name}.cdg", b"cdg")
                archive.writestr(f"{old_name}.mp3", b"mp3")
                archive.writestr("__MACOSX/metadata", b"metadata")
            original_zip = zip_path.read_bytes()

            options = normalize_shared.NormalizeSharedOptions(str(project.shared))
            failed_loudly = False
            try:
                normalize_shared.run(config=project.config, options=options)
            except SystemExit:
                failed_loudly = True

            self.assertTrue(zip_path.exists(), "original archive must remain at its source path")
            self.assertEqual(zip_path.read_bytes(), original_zip)
            self.assertTrue(failed_loudly, "archive metadata must not be silently discarded")

    def test_normalize_shared_names_renames_zip_mp4_and_zip_members_together(self):
        with temporary_project() as project:
            old_name = "OKSG-012 - The Hotelier - song title"
            new_name = "OKSG-0012 - Hotelier - Song Title"
            zip_path = project.shared / f"{old_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{old_name}.cdg", b"cdg")
                archive.writestr(f"{old_name}.mp3", b"mp3")
            (project.shared / f"{old_name}.mp4").write_bytes(b"video")

            options = normalize_shared.NormalizeSharedOptions(str(project.shared))
            normalize_shared.run(config=project.config, options=options)

            renamed_zip = project.shared / f"{new_name}.zip"
            self.assertTrue(renamed_zip.exists())
            self.assertTrue((project.shared / f"{new_name}.mp4").exists())
            with zipfile.ZipFile(renamed_zip) as archive:
                self.assertEqual(sorted(archive.namelist()), [f"{new_name}.cdg", f"{new_name}.mp3"])

    def test_normalize_shared_names_refuses_two_sources_with_one_destination(self):
        with temporary_project() as project:
            stems = [
                "OKSG-012 - The Band - The Song",
                "OKSG-0012 - Band - The   Song",
            ]
            for index, stem in enumerate(stems):
                with zipfile.ZipFile(project.shared / f"{stem}.zip", "w") as archive:
                    archive.writestr(f"{stem}.cdg", f"cdg-{index}".encode())
                    archive.writestr(f"{stem}.mp3", f"mp3-{index}".encode())

            options = normalize_shared.NormalizeSharedOptions(str(project.shared))
            with self.assertRaisesRegex(SystemExit, "Multiple shared files would normalize"):
                normalize_shared.run(config=project.config, options=options)
            self.assertEqual(
                sorted(path.name for path in project.shared.glob("*.zip")),
                sorted(f"{stem}.zip" for stem in stems),
            )

    def test_repair_shared_zips_dry_run_preserves_zip_and_does_not_extract_video(self):
        with temporary_project() as project:
            final_name = "OKSG-0001 - Band - Song"
            zip_path = project.shared / f"{final_name}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"{final_name}.cdg", b"cdg")
                archive.writestr(f"{final_name}.mp3", b"mp3")
                archive.writestr("export.mp4", b"video")
            original = zip_path.read_bytes()

            options = repair_shared_zips.RepairSharedZipsOptions(str(project.shared), True)
            repair_shared_zips.run(config=project.config, options=options)

            self.assertEqual(zip_path.read_bytes(), original)
            self.assertFalse((project.shared / f"{final_name}.mp4").exists())
