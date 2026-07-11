"""Creator-neutral release and shared-media naming helpers."""

import re
from pathlib import Path

from .models import SharedName, SongInfo

TRAILING_NOISE_RE = re.compile(
    r"\s*(?:\(|\[)?\s*(official|audio|video|lyrics?|lyric video|hd|hq|"
    r"remaster(?:ed)?|full album|visualizer|music video).*$",
    re.IGNORECASE,
)


def release_name(info: SongInfo, number: int, code: str) -> str:
    return f"{code}-{number:04d} - {harley_artist(info.artist)} - {harley_song(info.song)}"


def code_regex(code: str) -> re.Pattern[str]:
    escaped = re.escape(code.upper())
    return re.compile(rf"{escaped}[- ]?(\d{{3,4}})(?!\d)", re.IGNORECASE)


def shared_stem_regex(code: str) -> re.Pattern[str]:
    escaped = re.escape(code.upper())
    return re.compile(rf"^{escaped}[- ]?(\d{{3,4}})(?:\s*-\s*|\s+)(.+)$", re.IGNORECASE)


def next_release_number(root: Path, code: str) -> int:
    highest = 0
    matcher = code_regex(code)
    for path in root.rglob("*"):
        match = matcher.search(path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def clean_piece(value: str) -> str:
    value = value.replace("_", " ").strip()
    value = TRAILING_NOISE_RE.sub("", value).strip()
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -_")


def parse_artist_song(title: str) -> SongInfo | None:
    title = clean_piece(title)
    for separator in [" - ", " – ", " — ", " -- "]:
        if separator in title:
            artist, song = title.split(separator, 1)
            artist = clean_piece(artist)
            song = clean_piece(song)
            if artist and song:
                return SongInfo(artist=artist, song=song)
    return None


def normalize_stem(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def parse_shared_stem(stem: str, code: str) -> SharedName | None:
    match = shared_stem_regex(code).match(stem)
    if not match:
        return None
    number = int(match.group(1))
    rest = match.group(2).strip()
    if " - " in rest:
        artist, song = rest.split(" - ", 1)
    elif "-" in rest:
        artist, song = rest.split("-", 1)
    else:
        return None
    artist = clean_piece(artist)
    song = clean_piece(song)
    if not artist or not song:
        return None
    return SharedName(number, artist, song, code.upper())


def replace_word(value: str, pattern: str, replacement: str) -> str:
    return re.sub(pattern, replacement, value, flags=re.IGNORECASE)


def strip_non_the_commas(value: str) -> str:
    value = value.replace(", The", "<<<COMMA_THE>>>")
    value = value.replace(",", "")
    return value.replace("<<<COMMA_THE>>>", ", The")


def normalize_joiners(value: str) -> str:
    value = replace_word(value, r"\bfeat(?:uring)?\.?\b", "&")
    value = replace_word(value, r"\band\b", "&")
    value = re.sub(r"\s*&\s*", " & ", value)
    return re.sub(r"\s+", " ", value).strip()


def titlecase_simple(value: str) -> str:
    cased: list[str] = []
    for word in value.split(" "):
        if not word or word == "&":
            cased.append(word)
        elif word.startswith("(") and len(word) > 1:
            cased.append("(" + titlecase_simple(word[1:]))
        elif word.endswith(")") and len(word) > 1:
            cased.append(titlecase_simple(word[:-1]) + ")")
        elif any(ch.islower() for ch in word) and any(ch.isupper() for ch in word[1:]):
            cased.append(word)
        elif word.isupper() and len(word) > 1:
            cased.append(word)
        else:
            lowered = word.lower()
            cased.append(lowered[:1].upper() + lowered[1:])
    return " ".join(cased)


def harley_artist(artist: str) -> str:
    artist = normalize_joiners(artist)
    if artist.casefold() not in {"the who", "the the"}:
        artist = re.sub(r"^the\s+", "", artist, flags=re.IGNORECASE)
    artist = strip_non_the_commas(artist)
    return re.sub(r"\s+", " ", artist).strip()


def harley_song(song: str) -> str:
    song = strip_non_the_commas(normalize_joiners(song))
    words = song.split()
    if len(words) > 2 and words[0].casefold() == "the":
        song = " ".join(words[1:]) + ", The"
    song = titlecase_simple(re.sub(r"\s+", " ", song).strip())
    return song.replace(", the", ", The")


def harley_name_for(stem: str, code: str) -> str | None:
    parsed = parse_shared_stem(stem, code)
    if not parsed:
        return None
    return SharedName(
        parsed.number, harley_artist(parsed.artist), harley_song(parsed.song), parsed.code
    ).stem
