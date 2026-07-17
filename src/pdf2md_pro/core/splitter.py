"""Partizionamento PDF oltre limiti di pagine e/o dimensione.

Molti LLM accettano al massimo N pagine o M MB per richiesta: questo modulo
spezza il PDF in parti conformi. Prima chunk per numero di pagine, poi
bisezione ricorsiva delle parti che superano il limite in byte. Una singola
pagina sopra il limite non è ulteriormente divisibile: viene tenuta com'è.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

MB = 1024 * 1024


def needs_split(path: Path, max_pages: int | None, max_mb: float | None) -> bool:
    path = Path(path)
    if max_mb is not None and path.stat().st_size > max_mb * MB:
        return True
    if max_pages is not None:
        with pymupdf.open(path) as doc:
            if doc.page_count > max_pages:
                return True
    return False


def _extract(doc: pymupdf.Document, start: int, end: int) -> bytes:
    part = pymupdf.open()
    part.insert_pdf(doc, from_page=start, to_page=end)
    data = part.tobytes(deflate=True, garbage=3)
    part.close()
    return data


def _fit_ranges(
    doc: pymupdf.Document, start: int, end: int, max_bytes: float | None
) -> list[tuple[int, int, bytes]]:
    data = _extract(doc, start, end)
    if max_bytes is None or len(data) <= max_bytes or start == end:
        return [(start, end, data)]
    mid = (start + end) // 2
    return _fit_ranges(doc, start, mid, max_bytes) + _fit_ranges(
        doc, mid + 1, end, max_bytes
    )


def split_pdf(
    path: Path,
    out_dir: Path,
    max_pages: int | None = None,
    max_mb: float | None = None,
) -> list[Path]:
    """Ritorna i percorsi delle parti; `[path]` invariato se già nei limiti."""
    path = Path(path)
    if not needs_split(path, max_pages, max_mb):
        return [path]

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = max_mb * MB if max_mb is not None else None

    parts: list[Path] = []
    with pymupdf.open(path) as doc:
        step = max_pages or doc.page_count
        pieces: list[tuple[int, int, bytes]] = []
        for start in range(0, doc.page_count, step):
            end = min(start + step - 1, doc.page_count - 1)
            pieces.extend(_fit_ranges(doc, start, end, max_bytes))

        for index, (_, _, data) in enumerate(pieces, start=1):
            part_path = out_dir / f"{path.stem}_part{index:02d}.pdf"
            part_path.write_bytes(data)
            parts.append(part_path)
    return parts
