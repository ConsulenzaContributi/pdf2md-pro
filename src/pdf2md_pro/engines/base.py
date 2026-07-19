"""Interfaccia comune dei motori di conversione."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageResult:
    """Risultato della conversione di una singola pagina (1-based)."""

    page_number: int
    markdown: str
    images: tuple[str, ...] = ()
    confidence: float = 1.0
    engine: str = "native"
    tokens_in: int = 0
    tokens_out: int = 0
