"""Nomi file per argomento: slug ASCII, massimo 10 caratteri."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

TOPIC_MAX_LEN = 10
FALLBACK = "doc"

_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def _ascii_words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", text.lower())


def slugify_topic(text: str, max_len: int = TOPIC_MAX_LEN) -> str:
    MIN_TAIL = 3  # una coda troncata sotto 3 caratteri è rumore, non significato
    out = ""
    for word in _ascii_words(text):
        if not out:
            out = word[:max_len]
        else:
            space = max_len - len(out)
            if space < MIN_TAIL:
                break
            out += word[:space]
        if len(out) >= max_len:
            break
    return out or FALLBACK


def derive_topic(markdown: str, max_len: int = TOPIC_MAX_LEN) -> str:
    body = _FRONTMATTER.sub("", markdown)
    heading = _HEADING.search(body)
    if heading:
        return slugify_topic(heading.group(1), max_len)
    for line in body.splitlines():
        if line.strip():
            return slugify_topic(line, max_len)
    return FALLBACK


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    candidate = directory / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate
