from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from oksg_buddy import cli, naming
from oksg_buddy.commands import finish_song, new_song, repair_shared_videos, thumbnail
from oksg_buddy.models import SongInfo, ThumbnailFonts
from tests.support import temporary_project


class MetadataAndNamingTests(unittest.TestCase):
    def test_clean_piece_removes_common_youtube_noise(self):
        self.assertEqual(
            naming.clean_piece("Band_Name - Song (Official Lyric Video)"), "Band Name - Song"
        )
        self.assertEqual(naming.clean_piece("  Song__HD  "), "Song")

    def test_parse_artist_song_supports_common_dash_variants(self):
        self.assertEqual(naming.parse_artist_song("Band - Song"), SongInfo("Band", "Song"))
        self.assertEqual(naming.parse_artist_song("Band – Song"), SongInfo("Band", "Song"))
        self.assertIsNone(naming.parse_artist_song("A title without a separator"))

    def test_resolve_song_info_does_not_contact_youtube_when_names_are_explicit(self):
        options = new_song.NewSongOptions("https://example.invalid/video", "Band", "Song")
        info, metadata = new_song.resolve_song_info(options)
        self.assertEqual(info, SongInfo("Band", "Song"))
        self.assertEqual(metadata["webpage_url"], options.url)

    def test_harley_normalization_handles_articles_joiners_and_mixed_case(self):
        self.assertEqual(
            naming.harley_artist("The Hotelier and Friend, Jr."), "Hotelier & Friend Jr."
        )
        self.assertEqual(naming.harley_artist("The Who"), "The Who")
        self.assertEqual(naming.harley_song("the best of AND worst"), "Best Of & Worst, The")
        self.assertEqual(naming.harley_artist("mewithoutYou"), "mewithoutYou")

    def test_harley_guide_keeps_two_word_the_titles_unchanged(self):
        self.assertEqual(naming.harley_song("The Song"), "The Song")

    def test_shared_stem_parser_and_normalizer_reject_invalid_names(self):
        self.assertIsNone(naming.parse_shared_stem("Artist - Song", "OKSG"))
        self.assertIsNone(naming.harley_name_for("OKSG-not-a-number - Band - Song", "OKSG"))
        self.assertEqual(
            naming.harley_name_for("OKSG-012 - The Hotelier - song title", "OKSG"),
            "OKSG-0012 - Hotelier - Song Title",
        )

    def test_youtube_markdown_deduplicates_identical_tags(self):
        text = finish_song.youtube_markdown(
            SongInfo("Karaoke", "Karaoke"), "OKSG-0001 - Karaoke - Karaoke", None, None
        )
        tags = text.split("## Tags\n\n", 1)[1].split("\n\n## Files", 1)[0].split(", ")
        self.assertEqual(tags.count("Karaoke"), 1)

    def test_next_release_number_uses_highest_nested_valid_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "archive").mkdir()
            (root / "OKSG-0999 - Band - Song.mp4").write_bytes(b"video")
            (root / "archive" / "OKSG-123 - Other - Song.zip").write_bytes(b"zip")
            (root / "OKSG-99999 - ignored.txt").write_bytes(b"not a valid code")
            self.assertEqual(naming.next_release_number(root, "OKSG"), 1000)

    def test_next_release_number_supports_non_oksg_creator_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AB12-0042 - Band - Song.mp4").write_bytes(b"video")
            (root / "OKSG-9999 - Other - Song.mp4").write_bytes(b"video")
            self.assertEqual(naming.next_release_number(root, "AB12"), 43)

    def test_release_code_regex_requires_three_or_four_digits(self):
        cases = {
            "OKSG-001": "001",
            "OKSG-0001": "0001",
            "OKSG 0001": "0001",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(naming.code_regex("OKSG").search(value).group(1), expected)
        for value in ["OKSG-12", "OKSG-00001", "OKSG 12345"]:
            with self.subTest(value=value):
                self.assertIsNone(naming.code_regex("OKSG").search(value))

    def test_video_candidates_ignore_five_digit_incidental_codes(self):
        with temporary_project() as project:
            incidental = project.root / "archive" / "OKSG-00123 - incidental.mp4"
            wanted = project.root / "other" / "OKSG-0012 - wanted.mp4"
            incidental.parent.mkdir()
            wanted.parent.mkdir()
            incidental.write_bytes(b"incidental")
            wanted.write_bytes(b"wanted")

            self.assertEqual(
                repair_shared_videos.video_candidates_for("OKSG-0012 - Band - Song", project.root),
                [wanted],
            )


class ParserHelpTests(unittest.TestCase):
    def test_finish_song_help_explains_mp4_only_workflow(self):
        parser = cli.build_parser()
        subparsers = next(action for action in parser._actions if getattr(action, "choices", None))
        help_text = subparsers.choices["finish-song"].format_help()
        self.assertIn("Song working folder", help_text)
        self.assertIn("Skip CDG/MP3 ZIP packaging", help_text)
        self.assertIn("MP4-only example", help_text)

    def test_thumbnail_font_precedence(self):
        args = cli.build_parser().parse_args(
            [
                "thumbnail",
                "--artist",
                "Band",
                "--song",
                "Song",
                "--font",
                "Base",
                "--font.release",
                "Release",
                "--font.band",
                "Band Font",
            ]
        )
        self.assertEqual(
            thumbnail.thumbnail_fonts_from_options(
                thumbnail.ThumbnailOptions(
                    **{
                        key: value
                        for key, value in vars(args).items()
                        if key not in {"command", "config"}
                    }
                )
            ),
            ThumbnailFonts(band="Band Font", song="Release", banner="Base"),
        )
