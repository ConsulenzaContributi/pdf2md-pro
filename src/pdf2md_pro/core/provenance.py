"""Sidecar di provenienza: ogni blocco Markdown risale alla sua pagina PDF.

Le righe (md_start_line/md_end_line, 1-based) si riferiscono al file .md
finale, frontmatter incluso. Granularità a livello pagina; bbox per blocco
previsto in fase successiva.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build_provenance(
    source: Path,
    sha256: str,
    pages: int,
    engine: str,
    engine_version: str,
    blocks: list[dict],
) -> dict:
    return {
        "schema": 1,
        "source": {"file": source.name, "sha256": sha256, "pages": pages},
        "engine": {"name": engine, "version": engine_version},
        "blocks": blocks,
    }
