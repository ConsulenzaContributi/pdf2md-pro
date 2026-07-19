"""OCR reale (get_textpage_ocr): routing pagine e comportamento senza Tesseract."""

import shutil

import pymupdf
import pytest

from pdf2md_pro.engines.native import NativeEngine

HAS_TESSERACT = shutil.which("tesseract") is not None


def _text_pdf(tmp_path, text="Hello world, testo nativo di prova."):
    path = tmp_path / "testo.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()
    return path


def _blank_pdf(tmp_path):
    path = tmp_path / "vuoto.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    return path


def test_use_ocr_su_pdf_testuale_resta_nativo(tmp_path):
    # Arrange
    pdf = _text_pdf(tmp_path)

    # Act
    results = NativeEngine().convert(pdf, use_ocr=True)

    # Assert: nessuna pagina passa dall'OCR, testo estratto nativamente
    assert results
    assert all(r.engine == "native" for r in results)
    assert "Hello world" in results[0].markdown


def test_force_ocr_instrada_tutte_le_pagine(tmp_path):
    # Arrange
    pdf = _text_pdf(tmp_path)

    # Act
    results = NativeEngine().convert(pdf, force_ocr=True)

    # Assert: ogni pagina è marcata OCR; senza Tesseract diventa segnaposto
    assert results
    assert all(r.engine == "native:ocr" for r in results)
    if not HAS_TESSERACT:
        assert all(r.confidence == 0.0 for r in results)


def test_use_ocr_pagina_vuota_va_in_ocr(tmp_path):
    # Arrange
    pdf = _blank_pdf(tmp_path)

    # Act
    results = NativeEngine().convert(pdf, use_ocr=True)

    # Assert
    assert len(results) == 1
    assert results[0].engine == "native:ocr"


@pytest.mark.skipif(not HAS_TESSERACT, reason="Tesseract non installato")
def test_force_ocr_legge_il_testo(tmp_path):
    # Arrange
    pdf = _text_pdf(tmp_path, "RICONOSCIMENTO OTTICO PROVA")

    # Act
    results = NativeEngine().convert(pdf, force_ocr=True)

    # Assert
    assert results[0].confidence > 0
    assert "RICONOSCIMENTO" in results[0].markdown.upper()
