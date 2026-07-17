"""Genera il corpus sintetico di valutazione in eval/corpus/.

Ogni PDF ha un file .expected.txt con il testo che la conversione deve
recuperare. Deterministico: rilanciarlo produce sempre lo stesso corpus.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

CORPUS_DIR = Path(__file__).parent / "corpus"

A4 = pymupdf.paper_rect("a4")
MARGIN = 50
BODY = (
    "La conversione da PDF a Markdown richiede la ricostruzione della "
    "struttura logica del documento. Titoli, paragrafi, tabelle ed elenchi "
    "devono essere riconosciuti a partire dalla sola geometria della pagina."
)


def _page(doc: pymupdf.Document) -> pymupdf.Page:
    return doc.new_page(width=A4.width, height=A4.height)


def make_simple() -> tuple[pymupdf.Document, str]:
    doc = pymupdf.open()
    page = _page(doc)
    y = MARGIN
    parts = []
    for text, size in [
        ("Documento di prova", 24),
        (BODY, 11),
        ("Sezione uno", 16),
        (BODY, 11),
        ("Sezione due", 16),
        (BODY, 11),
    ]:
        rect = pymupdf.Rect(MARGIN, y, A4.width - MARGIN, y + (size * 5))
        page.insert_textbox(rect, text, fontsize=size, fontname="helv")
        y += size * 5 + 10
        parts.append(text)
    return doc, "\n".join(parts)


def make_tables() -> tuple[pymupdf.Document, str]:
    doc = pymupdf.open()
    page = _page(doc)
    page.insert_textbox(
        pymupdf.Rect(MARGIN, MARGIN, A4.width - MARGIN, MARGIN + 40),
        "Report vendite", fontsize=20, fontname="helv",
    )
    headers = ["Prodotto", "Quantita", "Prezzo", "Totale"]
    rows = [
        ["Mele", "10", "2", "20"],
        ["Pere", "5", "3", "15"],
        ["Uva", "8", "4", "32"],
    ]
    x0, y0, cw, ch = MARGIN, 120, 100, 24
    for r, row in enumerate([headers] + rows):
        for c, cell in enumerate(row):
            rect = pymupdf.Rect(x0 + c * cw, y0 + r * ch, x0 + (c + 1) * cw, y0 + (r + 1) * ch)
            page.draw_rect(rect, color=(0, 0, 0), width=0.5)
            page.insert_textbox(
                rect + (4, 4, -4, -4), cell, fontsize=10, fontname="helv"
            )
    words = ["Report vendite"] + headers + [c for row in rows for c in row]
    return doc, "\n".join(words)


def make_twocol() -> tuple[pymupdf.Document, str]:
    doc = pymupdf.open()
    page = _page(doc)
    page.insert_textbox(
        pymupdf.Rect(MARGIN, MARGIN, A4.width - MARGIN, MARGIN + 40),
        "Articolo a due colonne", fontsize=20, fontname="helv",
    )
    left = "Colonna sinistra primo blocco. " + BODY
    right = "Colonna destra secondo blocco. " + BODY
    mid = A4.width / 2
    page.insert_textbox(
        pymupdf.Rect(MARGIN, 120, mid - 10, 500), left, fontsize=11, fontname="helv"
    )
    page.insert_textbox(
        pymupdf.Rect(mid + 10, 120, A4.width - MARGIN, 500), right, fontsize=11, fontname="helv"
    )
    return doc, "\n".join(["Articolo a due colonne", left, right])


def make_images() -> tuple[pymupdf.Document, str]:
    doc = pymupdf.open()
    page = _page(doc)
    page.insert_textbox(
        pymupdf.Rect(MARGIN, MARGIN, A4.width - MARGIN, MARGIN + 40),
        "Documento con figura", fontsize=20, fontname="helv",
    )
    # ponytail: pixmap rosso pieno basta come "figura"; immagini reali in Fase 4
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 60))
    pix.clear_with(0)
    pix.set_rect(pix.irect, (255, 40, 40))
    page.insert_image(pymupdf.Rect(MARGIN, 120, MARGIN + 200, 240), pixmap=pix)
    caption = "Figura 1: area di prova rossa"
    page.insert_textbox(
        pymupdf.Rect(MARGIN, 250, A4.width - MARGIN, 280), caption, fontsize=10, fontname="helv"
    )
    return doc, "\n".join(["Documento con figura", caption])


GENERATORS = {
    "simple": make_simple,
    "tables": make_tables,
    "twocol": make_twocol,
    "images": make_images,
}


def main() -> None:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    for name, gen in GENERATORS.items():
        doc, expected = gen()
        pdf_path = CORPUS_DIR / f"{name}.pdf"
        doc.save(pdf_path)
        doc.close()
        (CORPUS_DIR / f"{name}.expected.txt").write_text(expected + "\n", encoding="utf-8")
        print(f"scritto {pdf_path.name}")


if __name__ == "__main__":
    main()
