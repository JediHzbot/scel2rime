"""Reader for Sogou `.scel` dictionary containers.

The format is undocumented by Sogou; everything here was observed from files
produced by Sogou's own dictionary builder. Two container generations exist and
both are handled:

    new (header_len 0x1540)   fixed header + syllable table + indexed entries
    old (header_len 0x0040)   fixed header + plain-text pinyin entries

Only the observed DCS and legacy entry layouts are supported. System engine
files and ECS entry layouts are out of scope. A container marker does not
establish the origin or ownership of its contents.

Layout of the new container, as observed:

    0x0000  u32   header length (0x1540)
    0x0004  char  magic "DCS\\x01"
    0x0008  u32   container version (1)
    0x000C  byte  digest[16]  observed field; not validated
    0x001C  utf16 dictionary id, NUL padded
    0x0130  utf16 dictionary name, 520-byte field
    0x0338  utf16 category,       520-byte field
    0x0540  utf16 description,   4096-byte field
    0x1540  u32   syllable count
            [u16 index, u16 byte_length, utf16 syllable] * count
            entry stream

Entry stream:

    u16  syllable count
    u16  pinyin byte length (== syllable count * 2)
    u16  syllable index * syllable count
    u16  word byte length
    char word[word_byte_length]   UTF-16LE
    u16  extension length (10)
    byte extension[extension_length]   u16 frequency, then reserved zero bytes
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

NEW_HEADER_LEN = 0x1540
OLD_HEADER_LEN = 0x0040
NEW_MAGIC = b"DCS\x01"

NAME_OFFSET, NAME_LEN = 0x0130, 520
CATEGORY_OFFSET, CATEGORY_LEN = 0x0338, 520
DESCRIPTION_OFFSET, DESCRIPTION_LEN = 0x0540, 4096

# The extension block is a fixed small record in every file observed so far.
EXTENSION_LEN = 10


class ScelError(ValueError):
    """Raised when a file is not a readable .scel container."""


@dataclass(frozen=True)
class WordEntry:
    """One dictionary entry: a word, its syllable chain, and a frequency."""

    word: str
    syllables: tuple[str, ...]
    frequency: int
    flags: int = 0

    @property
    def pinyin(self) -> str:
        return " ".join(self.syllables)


@dataclass
class ScelDictionary:
    """A parsed .scel file."""

    path: Path
    name: str = ""
    category: str = ""
    description: str = ""
    entries: list[WordEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    format_generation: str = "new"
    complete: bool = True

    @property
    def syllable_count(self) -> int:
        return len({s for entry in self.entries for s in entry.syllables})


def _read_utf16_field(data: bytes, offset: int, length: int) -> str:
    raw = data[offset:offset + length]
    text = raw.decode("utf-16-le", "replace")
    return text.split("\x00", 1)[0].strip()


def _decode_utf16(data: bytes, offset: int, byte_length: int) -> str:
    if byte_length <= 0 or byte_length % 2:
        raise ScelError(f"invalid UTF-16 length {byte_length} at 0x{offset:x}")
    raw = data[offset:offset + byte_length]
    if len(raw) != byte_length:
        raise ScelError(f"truncated UTF-16 text at 0x{offset:x}")
    try:
        text = raw.decode("utf-16-le")
    except UnicodeDecodeError as error:
        raise ScelError(f"invalid UTF-16 text at 0x{offset:x}") from error
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ScelError(f"control character in text at 0x{offset:x}")
    return text


# Bundled dictionaries shipped inside the input method use the same 0x1540
# header with an `ECS` magic and a different entry region. The unsupported
# layout is recognised and refused rather than half-parsed.
BUNDLED_MAGIC = b"ECS\x01"
MAGIC_PREFIXES = (NEW_MAGIC, BUNDLED_MAGIC)


def is_scel(data: bytes) -> bool:
    return len(data) >= 8 and data[4:8] in MAGIC_PREFIXES


def parse(data: bytes, path: Path | str = "<memory>") -> ScelDictionary:
    """Parse a .scel container from bytes.

    Generation is identified by header length. For the new generation the
    marker must be DCS; ECS and unknown markers are refused explicitly.
    """
    path = Path(path)
    if len(data) < OLD_HEADER_LEN:
        raise ScelError("file is smaller than the smallest .scel header")

    header_len = struct.unpack_from("<I", data, 0)[0]
    magic = data[4:8]

    if header_len == NEW_HEADER_LEN:
        if magic == BUNDLED_MAGIC:
            raise ScelError(
                "ECS container detected; "
                "this container variant is not supported by scel2rime"
            )
        if magic != NEW_MAGIC:
            raise ScelError(f"unrecognised DCS magic {magic!r}")
        return _parse_new(data, path)
    if header_len == OLD_HEADER_LEN:
        return _parse_old(data, path)
    raise ScelError(f"unrecognised header length 0x{header_len:x}")


def parse_file(path: Path | str) -> ScelDictionary:
    path = Path(path)
    return parse(path.read_bytes(), path)


def _parse_new(data: bytes, path: Path) -> ScelDictionary:
    dictionary = ScelDictionary(path=path, format_generation="new")
    dictionary.name = _read_utf16_field(data, NAME_OFFSET, NAME_LEN)
    dictionary.category = _read_utf16_field(data, CATEGORY_OFFSET, CATEGORY_LEN)
    dictionary.description = _read_utf16_field(data, DESCRIPTION_OFFSET, DESCRIPTION_LEN)

    cursor = NEW_HEADER_LEN
    if cursor + 4 > len(data):
        raise ScelError("truncated syllable table header")
    syllable_total = struct.unpack_from("<I", data, cursor)[0]
    cursor += 4
    if syllable_total > 4096:
        raise ScelError(f"implausible syllable count {syllable_total}")

    syllables: dict[int, str] = {}
    for _ in range(syllable_total):
        if cursor + 4 > len(data):
            raise ScelError("truncated syllable table")
        index, byte_length = struct.unpack_from("<HH", data, cursor)
        cursor += 4
        if index in syllables:
            raise ScelError(f"duplicate syllable index {index}")
        syllables[index] = _decode_utf16(data, cursor, byte_length)
        if any(char.isspace() for char in syllables[index]):
            raise ScelError(f"whitespace inside syllable {index}")
        cursor += byte_length

    dictionary.entries = _parse_indexed_entries(data, cursor, syllables, dictionary.warnings)
    dictionary.complete = not dictionary.warnings
    return dictionary


def _parse_indexed_entries(
    data: bytes,
    cursor: int,
    syllables: dict[int, str],
    warnings: list[str],
) -> list[WordEntry]:
    entries: list[WordEntry] = []
    total = len(data)

    while cursor < total:
        start = cursor
        try:
            flags, pinyin_bytes = struct.unpack_from("<HH", data, cursor)
            cursor += 4
            if pinyin_bytes == 0 or pinyin_bytes % 2 or pinyin_bytes > 512:
                raise ScelError(f"invalid pinyin byte length {pinyin_bytes}")
            syllable_count = pinyin_bytes // 2
            indices = struct.unpack_from(f"<{syllable_count}H", data, cursor)
            cursor += pinyin_bytes
            word_bytes = struct.unpack_from("<H", data, cursor)[0]
            cursor += 2
            word = _decode_utf16(data, cursor, word_bytes)
            cursor += word_bytes
            extension_len = struct.unpack_from("<H", data, cursor)[0]
            cursor += 2
            if not 2 <= extension_len <= 64 or cursor + extension_len > total:
                raise ScelError(f"unexpected extension length {extension_len}")
            frequency = struct.unpack_from("<H", data, cursor)[0]
            cursor += extension_len
        except (struct.error, ScelError) as error:
            warnings.append(f"stopped at 0x{start:x}: {error}")
            break

        chain = tuple(syllables.get(index, "") for index in indices)
        if any(not part for part in chain):
            warnings.append(f"skipped 0x{start:x}: unknown syllable index in {word!r}")
            continue
        if _is_han(word) and syllable_count != len(word):
            warnings.append(f"skipped 0x{start:x}: {syllable_count} syllables for {len(word)} characters")
            continue
        entries.append(WordEntry(word=word, syllables=chain, frequency=frequency, flags=flags))

    return entries


def _is_han(text: str) -> bool:
    return bool(text) and all("\u3400" <= character <= "\u9fff" for character in text)


def _syllable_indices(data: bytes, entry_start: int, syllable_count: int) -> tuple[int, ...]:
    """Re-read the syllable index array of one entry (already validated by the caller)."""
    offset = entry_start + 4  # syllable count + pinyin byte length
    return tuple(struct.unpack_from(f"<{syllable_count}H", data, offset))


def _parse_old(data: bytes, path: Path) -> ScelDictionary:
    """Old container: fixed header, then plain-text pinyin entries until EOF.

    Only the entry stream is decoded. The old header's metadata fields are not
    laid out consistently between builders, and guessing them produced garbage
    across the whole header, so the file name is used for the dictionary name
    and the limitation is reported instead.
    """
    dictionary = ScelDictionary(path=path, format_generation="old")
    dictionary.warnings.append(
        "old-generation container: metadata not decoded, dictionary name comes from the file name"
    )

    cursor = OLD_HEADER_LEN
    total = len(data)
    while cursor < total:
        start = cursor
        try:
            pinyin_bytes = struct.unpack_from("<H", data, cursor)[0]
            cursor += 2
            if pinyin_bytes == 0 or pinyin_bytes % 2 or pinyin_bytes > 256:
                raise ScelError(f"invalid pinyin length {pinyin_bytes}")
            pinyin = _decode_utf16(data, cursor, pinyin_bytes)
            cursor += pinyin_bytes
            word_bytes = struct.unpack_from("<H", data, cursor)[0]
            cursor += 2
            if word_bytes == 0 or word_bytes > 256:
                raise ScelError(f"invalid word length {word_bytes}")
            word = _decode_utf16(data, cursor, word_bytes)
            cursor += word_bytes
            syllables = tuple(pinyin.replace("'", " ").split())
            if not syllables:
                raise ScelError("empty syllable chain")
        except (struct.error, ScelError) as error:
            dictionary.warnings.append(f"stopped at 0x{start:x}: {error}")
            dictionary.complete = False
            break
        dictionary.entries.append(WordEntry(word=word, syllables=syllables, frequency=1))
    return dictionary
