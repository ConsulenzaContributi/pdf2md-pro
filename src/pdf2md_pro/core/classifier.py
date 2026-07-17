"""Classificazione pagine: dove basta il parser nativo e dove serve altro."""

from __future__ import annotations

from pathlib import Path

import pymupdf

# ponytail: soglia testo minimo; euristica su layout/tabelle in Fase 3
MIN_NATIVE_CHARS = 30

NATIVE = "native"
COMPLEX = "complex"


def classify_page(page: pymupdf.Page) -> str:
    """`native` se la pagina ha testo estraibile, `complex` se è una scansione
    o quasi vuota di testo (probabile contenuto solo grafico)."""
    text = page.get_text().strip()
    return NATIVE if len(text) >= MIN_NATIVE_CHARS else COMPLEX


def classify_pdf(path: Path, pages: list[int] | None = None) -> dict[int, str]:
    """Mappa numero pagina (1-based) → classe."""
    with pymupdf.open(path) as doc:
        numbers = pages or list(range(1, doc.page_count + 1))
        return {n: classify_page(doc[n - 1]) for n in numbers}
