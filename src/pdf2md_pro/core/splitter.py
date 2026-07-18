"""Partizionamento PDF oltre limiti di pagine e/o dimensione.

Molti LLM accettano al massimo N pagine o M MB per richiesta: questo modulo
spezza il PDF in parti conformi. Prima chunk per numero di pagine, poi
bisezione ricorsiva delle parti che superano il limite in byte. Una singola
pagina sopra il limite non è ulteriormente divisibile: viene tenuta com'è.

Le parti sono nominate `<nome> <totale> <numero>.pdf` (es. `relazione 03 01.pdf`):
il primo numero è in quante sezioni è stato diviso il file, il secondo la
posizione della parte.

`split_folder` analizza un'intera cartella e partiziona tutti i file che
superano i limiti, anche in maniera congiunta (basta superare uno dei fattori).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

import pymupdf

from pdf2md_pro.core.naming import unique_path

MB = 1024 * 1024
INTERI_DIR = "interi"  # sottocartella dove finiscono gli originali spezzati


def list_pdfs(folder: Path) -> list[Path]:
    """PDF reali della cartella, ordinati. Esclude i file nascosti e gli
    AppleDouble di macOS (`._nome.pdf`), che non sono documenti veri."""
    return sorted(
        p for p in Path(folder).glob("*.pdf") if not p.name.startswith(".")
    )


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

        total = len(pieces)
        for index, (_, _, data) in enumerate(pieces, start=1):
            part_path = out_dir / f"{path.stem} {total:02d} {index:02d}.pdf"
            part_path.write_bytes(data)
            parts.append(part_path)
    return parts


def analyze_folder(
    source_dir: Path,
    max_pages: int | None = None,
    max_mb: float | None = None,
) -> list[dict]:
    """Analisi preliminare: per ogni PDF pagine, dimensione e limiti superati.

    Non scrive nulla. `needs_split` è vero se almeno un fattore è oltre.
    """
    source = Path(source_dir)
    if not source.is_dir():
        raise ValueError(f"cartella non trovata: {source}")

    report = []
    for pdf in list_pdfs(source):
        entry: dict = {"file": pdf.name}
        try:
            size_mb = pdf.stat().st_size / MB
            with pymupdf.open(pdf) as doc:
                pages = doc.page_count
            over_pages = max_pages is not None and pages > max_pages
            over_mb = max_mb is not None and size_mb > max_mb
            entry.update(
                pages=pages,
                mb=round(size_mb, 2),
                over_pages=over_pages,
                over_mb=over_mb,
                needs_split=over_pages or over_mb,
            )
        except Exception as exc:
            entry["error"] = str(exc)
        report.append(entry)
    return report


def partition_in_place(
    pdf: Path,
    max_pages: int | None = None,
    max_mb: float | None = None,
    interi_dir: Path | None = None,
) -> list[str]:
    """Crea le parti nella stessa cartella del PDF e archivia l'originale.

    L'originale spezzato va in `interi_dir` se indicata, altrimenti nella
    sottocartella `interi/` accanto al file. Ritorna i nomi delle parti;
    presuppone che il file vada spezzato."""
    pdf = Path(pdf)
    folder = pdf.parent
    parts = split_pdf(pdf, folder, max_pages, max_mb)
    interi = Path(interi_dir) if interi_dir else folder / INTERI_DIR
    interi.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pdf), str(unique_path(interi, pdf.stem, pdf.suffix)))
    return [p.name for p in parts]


def split_folder(
    source_dir: Path,
    max_pages: int | None = None,
    max_mb: float | None = None,
    progress: Callable[[dict], None] = lambda e: None,
    interi_dir: Path | None = None,
) -> dict:
    """Partiziona i PDF della cartella oltre i limiti, in loco.

    Le parti restano nella cartella elaborata; ogni originale spezzato viene
    archiviato in `interi_dir` (default: sottocartella `interi/`). I file già
    nei limiti non si toccano. Ritorna `{"split": {nome: [parti]}, "skipped":
    [nomi], "errors": [msg], "interi_dir": percorso}`. Un file rotto non ferma
    gli altri."""
    source = Path(source_dir)
    if not source.is_dir():
        raise ValueError(f"cartella non trovata: {source}")
    interi = Path(interi_dir) if interi_dir else source / INTERI_DIR

    summary: dict = {
        "split": {}, "skipped": [], "errors": [], "interi_dir": str(interi),
    }
    for pdf in list_pdfs(source):  # materializzato: le parti create non rientrano
        try:
            if not needs_split(pdf, max_pages, max_mb):
                summary["skipped"].append(pdf.name)
                progress({"status": "skip", "file": pdf.name})
                continue
            names = partition_in_place(pdf, max_pages, max_mb, interi)
            summary["split"][pdf.name] = names
            progress({"status": "split", "file": pdf.name, "parts": len(names)})
        except Exception as exc:
            summary["errors"].append(f"{pdf.name}: {exc}")
            progress({"status": "error", "file": pdf.name, "error": str(exc)})
    return summary
