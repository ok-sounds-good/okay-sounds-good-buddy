from __future__ import annotations

import unittest
import zipfile

from oksg_buddy.commands import finish_song
from tests.support import temporary_project


class FinishSongIntegrationTests(unittest.TestCase):
    def test_mp4_only_stages_video_writes_youtube_notes_and_copies_to_shared(self):
        with temporary_project() as project:
            folder = project.root / "La Dispute - Woman (Reading)"
            folder.mkdir()
            source = folder / "MidiCo Export.mp4"
            source.write_bytes(b"video data")

            options = finish_song.FinishSongOptions(
                str(folder), "La Dispute", "Woman (Reading)", 25, mp4_only=True
            )
            finish_song.run(config=project.config, options=options)

            final_name = "OKSG-0025 - La Dispute - Woman (Reading)"
            local_mp4 = folder / f"{final_name}.mp4"
            self.assertEqual(local_mp4.read_bytes(), b"video data")
            self.assertEqual((project.shared / local_mp4.name).read_bytes(), b"video data")
            youtube = (folder / "YOUTUBE.md").read_text(encoding="utf-8")
            self.assertIn(str(local_mp4), youtube)
            self.assertIn(final_name, youtube)

    def test_mp4_only_requires_a_video_input(self):
        with temporary_project() as project:
            folder = project.root / "Band - Song"
            folder.mkdir()
            options = finish_song.FinishSongOptions(str(folder), "Band", "Song", 1, mp4_only=True)
            with self.assertRaisesRegex(SystemExit, "MP4-only"):
                finish_song.run(config=project.config, options=options)
            self.assertFalse((folder / "YOUTUBE.md").exists())

    def test_dry_run_does_not_create_release_files(self):
        with temporary_project() as project:
            folder = project.root / "Band - Song"
            folder.mkdir()
            (folder / "export.mp4").write_bytes(b"video")
            options = finish_song.FinishSongOptions(
                str(folder), "Band", "Song", 1, mp4_only=True, dry_run=True
            )
            finish_song.run(config=project.config, options=options)
            self.assertEqual([path.name for path in folder.glob("*.mp4")], ["export.mp4"])
            self.assertFalse((folder / "YOUTUBE.md").exists())
            self.assertFalse(list(project.shared.iterdir()))

    def test_cdg_release_packages_matching_zip_and_copies_it_to_shared(self):
        with temporary_project() as project:
            folder = project.root / "Band - Song"
            folder.mkdir()
            (folder / "instrumental.mp3").write_bytes(b"mp3")
            (folder / "graphics.cdg").write_bytes(b"cdg")
            options = finish_song.FinishSongOptions(str(folder), "Band", "Song", 2)
            finish_song.run(config=project.config, options=options)

            final_name = "OKSG-0002 - Band - Song"
            zip_path = folder / final_name / f"{final_name}.zip"
            with zipfile.ZipFile(zip_path) as archive:
                self.assertEqual(
                    sorted(archive.namelist()), [f"{final_name}.cdg", f"{final_name}.mp3"]
                )
            self.assertTrue((project.shared / zip_path.name).exists())
