import json
import re

import pymupdf
import pytest

from pdf2md_pro.core.pipeline import ConversionError, convert


@pytest.fixture
def simple_pdf(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(
        pymupdf.Rect(50, 50, 550, 120), "Titolo Prova", fontsize=24, fontname="helv"
    )
    page.insert_textbox(
        pymupdf.Rect(50, 130, 550, 300),
        "Paragrafo di contenuto per la conversione.",
        fontsize=11,
        fontname="helv",
    )
    path = tmp_path / "doc.pdf"
    doc.save(path)
    doc.close()
    return path


def test_convert_simple_pdf(simple_pdf, tmp_path):
    out_dir = tmp_path / "out"

    result = convert(simple_pdf, out_dir)

    md_text = result.markdown_path.read_text(encoding="utf-8")
    assert "Titolo Prova" in md_text
    assert "Paragrafo di contenuto" in md_text

    prov = json.loads(result.provenance_path.read_text(encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{64}", prov["source"]["sha256"])
    assert prov["source"]["pages"] == 1
    assert prov["blocks"][0]["page"] == 1
    assert prov["blocks"][0]["engine"] == "native"


def test_frontmatter_riporta_strumento_motore_tempo_config(simple_pdf, tmp_path):
    result = convert(simple_pdf, tmp_path / "out")
    md_text = result.markdown_path.read_text(encoding="utf-8")

    assert 'tool: "pdf2md-pro v' in md_text
    assert "duration_s:" in md_text
    assert 'config: "motore=native' in md_text
    assert result.engine == "native"
    assert result.pages == 1
    assert result.duration_s >= 0


def test_footer_nel_corpo_riporta_strumento_motore_tempo_config(simple_pdf, tmp_path):
    result = convert(simple_pdf, tmp_path / "out")
    md_text = result.markdown_path.read_text(encoding="utf-8")

    assert "Estratto con [pdf2md-pro]" in md_text
    assert "Motore: native" in md_text
    assert "Tempo di elaborazione:" in md_text
    assert "Configurazione: motore=native" in md_text
    assert "second brain" not in md_text  # solo con brain_optimize=True


def test_config_summary_riporta_opzioni_avanzate_attive(simple_pdf, tmp_path):
    result = convert(simple_pdf, tmp_path / "out", dpi=300, force_ocr=True)
    md_text = result.markdown_path.read_text(encoding="utf-8")

    assert "ocr=forzato" in md_text
    assert "dpi=300" in md_text


def test_no_silent_overwrite(simple_pdf, tmp_path):
    out_dir = tmp_path / "out"
    convert(simple_pdf, out_dir)

    with pytest.raises(ConversionError):
        convert(simple_pdf, out_dir)

    convert(simple_pdf, out_dir, force=True)


def test_encrypted_pdf_rejected(tmp_path):
    doc = pymupdf.open()
    doc.new_page()
    path = tmp_path / "locked.pdf"
    doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="segreto")
    doc.close()

    with pytest.raises(ConversionError):
        convert(path, tmp_path / "out")
