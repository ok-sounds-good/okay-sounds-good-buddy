"""Reusable thumbnail rendering and font-resolution utilities."""

from __future__ import annotations

import functools
import re
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import OksgConfig, SongInfo, ThumbnailFonts, ThumbnailStyle

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}
PORTABLE_SANS = "__oksg_portable_sans__"
PORTABLE_MONO = "__oksg_portable_mono__"
PORTABLE_FONT_CANDIDATES = {
    PORTABLE_SANS: ("Helvetica.ttc", "Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"),
    PORTABLE_MONO: (
        "Courier New.ttf",
        "DejaVuSansMono.ttf",
        "LiberationMono-Regular.ttf",
    ),
}


def default_font_candidates(display: bool, font_dirs: tuple[Path, ...] = ()) -> list[Path]:
    user_fonts = Path.home() / "Library/Fonts"
    platform_fonts = [
        Path.home() / ".local/share/fonts",
        Path.home() / ".fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
    ]
    configured_fonts = sorted(
        (
            font
            for directory in font_dirs
            if directory.is_dir()
            for font in directory.rglob("*")
            if font.suffix.lower() in FONT_EXTENSIONS
        ),
        key=lambda path: str(path).casefold(),
    )
    if display:
        return configured_fonts + [
            REPOSITORY_ROOT / "fonts/Press_Start_2P/PressStart2P-Regular.ttf",
            user_fonts / "PressStart2P-Regular.ttf",
            REPOSITORY_ROOT / "Pixeled.ttf",
            REPOSITORY_ROOT / "Pixellari.ttf",
            REPOSITORY_ROOT / "PressStart2P.ttf",
            *platform_fonts,
            Path("/System/Library/Fonts/Supplemental/Courier New Bold.ttf"),
            Path("/System/Library/Fonts/Supplemental/AmericanTypewriter.ttc"),
            Path("/System/Library/Fonts/Monaco.ttf"),
            Path("/System/Library/Fonts/Menlo.ttc"),
        ]
    return configured_fonts + [
        *platform_fonts,
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
    ]


def normalized_font_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold()).removesuffix("regular")


@functools.lru_cache(maxsize=None)
def resolve_font_path(font_name: str, font_dirs: tuple[Path, ...] = ()) -> Path | None:
    requested = Path(font_name).expanduser()
    for path in [requested, REPOSITORY_ROOT / requested]:
        if path.is_file():
            return path
    wanted = normalized_font_name(font_name)
    for directory in [
        *font_dirs,
        Path.home() / "Library/Fonts",
        Path.home() / ".local/share/fonts",
        Path.home() / ".fonts",
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
    ]:
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.suffix.lower() not in FONT_EXTENSIONS:
                continue
            name = normalized_font_name(path.stem)
            if name == wanted or name.removeprefix("bold") == wanted or wanted in name:
                return path
    return None


def load_font(
    size: int,
    font_name: str | None = None,
    *,
    display_fallback: bool = False,
    font_dirs: tuple[Path, ...] = (),
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if font_name in PORTABLE_FONT_CANDIDATES:
        candidates = [Path(name) for name in PORTABLE_FONT_CANDIDATES[font_name]]
    elif font_name:
        candidates = [resolve_font_path(font_name, font_dirs), Path(font_name)]
    else:
        candidates = default_font_candidates(display_fallback, font_dirs)
    for path in candidates:
        if path:
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    if font_name == PORTABLE_SANS:
        return ImageFont.load_default(size=size)
    if font_name == PORTABLE_MONO:
        return ImageFont.load_default(size=max(1, size - 2))
    if font_name and font_name not in PORTABLE_FONT_CANDIDATES:
        raise SystemExit(f"Could not find or load font: {font_name}")
    return ImageFont.load_default()


def style_font_name(
    explicit_name: str | None, default_name: str | None, font_dirs: tuple[Path, ...]
) -> str | None:
    """Keep explicit font requests strict while allowing portable style fallbacks."""
    if explicit_name:
        return explicit_name
    if default_name and resolve_font_path(default_name, font_dirs):
        return default_name
    if not default_name:
        return None
    normalized = normalized_font_name(default_name)
    if "courier" in normalized or "typewriter" in normalized or "mono" in normalized:
        return PORTABLE_MONO
    return PORTABLE_SANS


def wrap_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = ""
            for character in word:
                trial = current + character
                if current and draw.textlength(trial, font=font) > max_width:
                    lines.append(current)
                    current = character
                else:
                    current = trial
    if current:
        lines.append(current)
    return lines


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    start_size: int,
    min_size: int = 20,
    font_name: str | None = None,
    display_fallback: bool = False,
    font_dirs: tuple[Path, ...] = (),
) -> tuple[ImageFont.ImageFont, list[str], int]:
    for size in range(start_size, min_size - 1, -1):
        font = load_font(size, font_name, display_fallback=display_fallback, font_dirs=font_dirs)
        lines = wrap_text(draw, text, font, max_width)
        line_height = int(size * 1.12)
        if line_height * len(lines) <= max_height and all(
            draw.textbbox((0, 0), line, font=font)[2] <= max_width for line in lines
        ):
            return font, lines, line_height
    font = load_font(min_size, font_name, display_fallback=display_fallback, font_dirs=font_dirs)
    return font, wrap_text(draw, text, font, max_width), int(min_size * 1.08)


def draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.ImageFont,
    y: int,
    line_height: int,
    fill: tuple[int, int, int],
    width: int = 1280,
) -> int:
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, y), line, font=font, fill=fill)
        y += line_height
    return y


def find_logo_base(config: OksgConfig | None = None) -> Path | None:
    if config is not None:
        return config.logo_path
    for name in ["Thumbnail-no-text.png", "banner.png", "Thumbnail.png"]:
        path = REPOSITORY_ROOT / name
        if path.exists():
            return path
    return None


def crop_visible_logo(logo: Image.Image) -> Image.Image:
    rgba = logo.convert("RGBA")
    pix = rgba.load()
    min_x, min_y, max_x, max_y, found = rgba.width, rgba.height, 0, 0, False
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, a = pix[x, y]
            if a > 8 and max(r, g, b) > 35:
                min_x, min_y, max_x, max_y, found = (
                    min(min_x, x),
                    min(min_y, y),
                    max(max_x, x),
                    max(max_y, y),
                    True,
                )
    if not found:
        return rgba
    pad = 18
    return rgba.crop(
        (
            max(0, min_x - pad),
            max(0, min_y - pad),
            min(rgba.width, max_x + pad),
            min(rgba.height, max_y + pad),
        )
    )


def remove_edge_connected_dark_background(logo: Image.Image) -> Image.Image:
    rgba = logo.convert("RGBA")
    pixels = rgba.load()
    queue: deque[tuple[int, int]] = deque()
    seen: set[tuple[int, int]] = set()
    for x in range(rgba.width):
        queue.extend(((x, 0), (x, rgba.height - 1)))
    for y in range(1, rgba.height - 1):
        queue.extend(((0, y), (rgba.width - 1, y)))
    while queue:
        x, y = queue.popleft()
        if (x, y) in seen:
            continue
        seen.add((x, y))
        r, g, b, a = pixels[x, y]
        if a == 0 or max(r, g, b) > 35:
            continue
        pixels[x, y] = (r, g, b, 0)
        for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= next_x < rgba.width and 0 <= next_y < rgba.height:
                queue.append((next_x, next_y))
    return rgba


THUMBNAIL_STYLES = {
    "retro": ThumbnailStyle(
        (0, 0, 0),
        (255, 205, 35),
        (220, 0, 20),
        (220, 0, 20),
        (1160, 250, 118),
        (1140, 178, 102),
        42,
        14,
        388,
        (860, 250),
        612,
        True,
        None,
        None,
        None,
    ),
    "classic": ThumbnailStyle(
        (0, 0, 0),
        (255, 205, 35),
        (220, 0, 20),
        (220, 0, 20),
        (1160, 250, 118),
        (1140, 178, 102),
        42,
        14,
        388,
        (860, 250),
        612,
        False,
        "Helvetica",
        "Helvetica",
        "Helvetica",
    ),
    "typewriter": ThumbnailStyle(
        (0, 0, 0),
        (255, 205, 35),
        (220, 0, 20),
        (220, 0, 20),
        (1160, 250, 118),
        (1140, 178, 102),
        42,
        14,
        388,
        (860, 250),
        612,
        False,
        "Courier New Bold",
        "Courier New Bold",
        "American Typewriter",
    ),
}


def make_thumbnail(
    info: SongInfo,
    output: Path,
    style: str = "retro",
    fonts: ThumbnailFonts | None = None,
    config: OksgConfig | None = None,
) -> None:
    profile = THUMBNAIL_STYLES[style]
    fonts = fonts or ThumbnailFonts()
    canvas = Image.new("RGB", (1280, 720), profile.background)
    draw = ImageDraw.Draw(canvas)
    font_dirs = config.font_dirs if config else ()
    song_font, song_lines, song_height = fit_text(
        draw,
        info.song,
        *profile.song_box,
        font_name=style_font_name(fonts.song, profile.default_song_font, font_dirs),
        display_fallback=profile.default_song_font is None,
        font_dirs=font_dirs,
    )
    artist_font, artist_lines, artist_height = fit_text(
        draw,
        info.artist,
        *profile.band_box,
        min_size=20,
        font_name=style_font_name(fonts.band, profile.default_band_font, font_dirs),
        display_fallback=profile.default_band_font is None,
        font_dirs=font_dirs,
    )
    y = (
        draw_centered_lines(
            draw, song_lines, song_font, profile.song_y, song_height, profile.song_color
        )
        + profile.band_gap
    )
    draw_centered_lines(draw, artist_lines, artist_font, y, artist_height, profile.band_color)
    logo_path = find_logo_base(config)
    if logo_path:
        logo = Image.open(logo_path).convert("RGBA")
        if logo_path.name == "Thumbnail.png":
            logo = logo.crop((0, 180, logo.width, logo.height))
        logo = crop_visible_logo(logo)
        if profile.background != (0, 0, 0):
            logo = remove_edge_connected_dark_background(logo)
        logo.thumbnail(profile.logo_size, Image.Resampling.LANCZOS)
        canvas.paste(logo, ((1280 - logo.width) // 2, profile.logo_y), logo)
    brand_font, brand_lines, brand_height = fit_text(
        draw,
        config.creator_name if config else "Okay, Sounds Good Karaoke",
        1100,
        76,
        62,
        min_size=20,
        font_name=style_font_name(fonts.banner, profile.default_banner_font, font_dirs),
        font_dirs=font_dirs,
    )
    draw_centered_lines(
        draw, brand_lines, brand_font, profile.banner_y, brand_height, profile.banner_color
    )
    if profile.pixelate:
        canvas = canvas.resize((640, 360), Image.Resampling.BOX).resize(
            (1280, 720), Image.Resampling.NEAREST
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=95)
