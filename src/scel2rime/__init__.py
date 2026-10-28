"""scel2rime — carry your own Sogou dictionaries into Rime.

The package reads `.scel` files (Sogou's user dictionary container) and renders
them as Rime `.dict.yaml`. It never reads Sogou's system dictionaries, never
touches the input method's engine files, and ships no third-party code or word
lists: the only data it converts is the data you already own.
"""

from .rime import DEFAULT_WEIGHT_SCALE, name_for, render, sanitize_name, write
from .scel import ScelDictionary, ScelError, WordEntry, parse, parse_file

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_WEIGHT_SCALE",
    "ScelDictionary",
    "ScelError",
    "WordEntry",
    "name_for",
    "parse",
    "parse_file",
    "render",
    "sanitize_name",
    "write",
    "__version__",
]
