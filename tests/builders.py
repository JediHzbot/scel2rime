"""Builders that produce synthetic `.scel` files for tests.

They are the inverse of `scel.py` and exist so the parser can be exercised on
edge cases (empty dictionaries, umlaut syllables, long entries, truncation)
without shipping anyone else's dictionary in the repository.
"""

from __future__ import annotations

import hashlib
import struct

NEW_HEADER_LEN = 0x1540
OLD_HEADER_LEN = 0x0040
MAGIC = b"DCS\x01"


def _pad_utf16(text: str, size: int) -> bytes:
    raw = text.encode("utf-16-le")
    if len(raw) > size:
        raise ValueError(f"field text too long for {size} bytes: {text!r}")
    return raw + b"\x00" * (size - len(raw))


def build_new(
    entries: list[tuple[str, list[str], int]],
    *,
    name: str = "",
    category: str = "",
    description: str = "",
    dictionary_id: str = "37121",
    magic: bytes = MAGIC,
) -> bytes:
    """Assemble a new-generation container from (word, syllables, grade) rows.

    `magic` is `DCS\\x01` for user dictionaries and `ECS\\x01` for the bundled
    variant, which uses the same header but a different entry region.
    """
    syllables = sorted({syllable for _word, chain, _grade in entries for syllable in chain})
    index_of = {syllable: position for position, syllable in enumerate(syllables)}

    header = bytearray(NEW_HEADER_LEN)
    struct.pack_into("<I", header, 0x00, NEW_HEADER_LEN)
    header[0x04:0x08] = magic
    struct.pack_into("<I", header, 0x08, 1)
    header[0x0C:0x1C] = hashlib.md5(b"".join(w.encode("utf-8") for w, _c, _g in entries)).digest()
    header[0x1C:0x1C + len(dictionary_id.encode("utf-16-le"))] = dictionary_id.encode("utf-16-le")
    header[0x0130:0x0338] = _pad_utf16(name, 520)
    header[0x0338:0x0540] = _pad_utf16(category, 520)
    header[0x0540:0x1540] = _pad_utf16(description, 4096)

    body = bytearray()
    body += struct.pack("<I", len(syllables))
    for position, syllable in enumerate(syllables):
        raw = syllable.encode("utf-16-le")
        body += struct.pack("<HH", position, len(raw))
        body += raw

    for word, chain, grade in entries:
        raw_word = word.encode("utf-16-le")
        indices = [index_of[syllable] for syllable in chain]
        body += struct.pack("<H", 1)  # flags: constant 1 in every observed file
        body += struct.pack("<H", len(indices) * 2)
        body += struct.pack(f"<{len(indices)}H", *indices)
        body += struct.pack("<H", len(raw_word))
        body += raw_word
        body += struct.pack("<H", 10)
        body += struct.pack("<H", grade) + b"\x00" * 8

    return bytes(header) + bytes(body)


def build_old(
    entries: list[tuple[str, list[str], int]],
) -> bytes:
    """Assemble an old-generation container with plain-text pinyin rows.

    Only the entry stream is meaningful here: the old header's metadata layout
    varies between builders, and the parser deliberately ignores it.
    """
    header = bytearray(OLD_HEADER_LEN)
    struct.pack_into("<I", header, 0x00, OLD_HEADER_LEN)

    body = bytearray()
    for word, chain, _grade in entries:
        pinyin = " ".join(chain).encode("utf-16-le")
        raw_word = word.encode("utf-16-le")
        body += struct.pack("<H", len(pinyin)) + pinyin
        body += struct.pack("<H", len(raw_word)) + raw_word

    return bytes(header) + bytes(body)
