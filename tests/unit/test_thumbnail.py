from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oksg_buddy import thumbnails
from oksg_buddy.commands import thumbnail
from oksg_buddy.models import OksgConfig, SongInfo


class ThumbnailTests(unittest.TestCase):
    def test_unbroken_text_wraps_to_width(self):
        image = thumbnails.Image.new("RGB", (200, 100))
        draw = thumbnails.ImageDraw.Draw(image)
        font = thumbnails.load_font(20, display_fallback=True)
        lines = thumbnails.wrap_text(draw, "a" * 200, font, 120)
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(draw.textlength(line, font=font) <= 120 for line in lines))

    def test_unknown_explicit_font_is_a_clear_error(self):
        with self.assertRaisesRegex(SystemExit, "Could not find or load font"):
            thumbnails.load_font(24, "Definitely Not An Installed Font")

    def test_missing_style_font_uses_portable_fallback(self):
        info = SongInfo("Band", "Song")
        with tempfile.TemporaryDirectory() as directory:
            outputs = []
            with (
                mock.patch.object(thumbnails, "resolve_font_path", return_value=None),
                mock.patch.dict(
                    thumbnails.PORTABLE_FONT_CANDIDATES,
                    {
                        thumbnails.PORTABLE_SANS: ("missing-sans.ttf",),
                        thumbnails.PORTABLE_MONO: ("missing-mono.ttf",),
                    },
                ),
            ):
                for style in thumbnails.THUMBNAIL_STYLES:
                    output = Path(directory) / f"{style}.png"
                    thumbnails.make_thumbnail(info, output, style)
                    outputs.append(output.read_bytes())
            self.assertEqual(len(set(outputs)), len(outputs))

    def test_explicit_font_path_precedes_discovery_and_resolution_is_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            explicit = Path(directory) / "Explicit.ttf"
            explicit.write_bytes(b"font")
            thumbnails.resolve_font_path.cache_clear()
            self.assertEqual(
                thumbnails.resolve_font_path(str(explicit), (Path(directory),)), explicit
            )
            before = thumbnails.resolve_font_path.cache_info()
            self.assertEqual(
                thumbnails.resolve_font_path(str(explicit), (Path(directory),)), explicit
            )
            after = thumbnails.resolve_font_path.cache_info()
            self.assertEqual(after.hits, before.hits + 1)

    def test_all_styles_render_distinct_1280_by_720_images(self):
        info = SongInfo("Band", "Song")
        with tempfile.TemporaryDirectory() as directory:
            outputs = []
            for style in thumbnails.THUMBNAIL_STYLES:
                output = Path(directory) / f"{style}.png"
                thumbnails.make_thumbnail(info, output, style)
                with thumbnails.Image.open(output) as image:
                    self.assertEqual(image.size, (1280, 720))
                outputs.append(output.read_bytes())
        self.assertEqual(len(set(outputs)), len(outputs))

    def test_thumbnail_command_generates_all_named_style_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = OksgConfig(root, root, root.parent, "OKSG", "Creator", None, ())
            thumbnail.run(
                config=config, options=thumbnail.ThumbnailOptions("Band", "Song", folder=directory)
            )
            self.assertEqual(
                {path.name for path in Path(directory).glob("*.png")},
                {
                    "Band - Song - retro.png",
                    "Band - Song - classic.png",
                    "Band - Song - typewriter.png",
                },
            )

    def test_output_requires_an_explicit_style_when_generating_all(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = OksgConfig(root, root, root.parent, "OKSG", "Creator", None, ())
            options = thumbnail.ThumbnailOptions("Band", "Song", output="one.png")
            with self.assertRaisesRegex(SystemExit, "--output requires --style"):
                thumbnail.run(config=config, options=options)
