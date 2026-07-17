import json

import pymupdf
import pytest

from pdf2md_pro.core.pipeline import convert
from pdf2md_pro.engines.openrouter import OpenRouterEngine


@pytest.fixture
def mixed_pdf(tmp_path):
    """Pagina 1 con testo, pagina 2 solo immagine (finta scansione)."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(
        pymupdf.Rect(50, 50, 550, 200),
        "Capitolo primo con testo nativo estraibile dalla pagina.",
        fontsize=12,
        fontname="helv",
    )
    scan = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200))
    pix.clear_with(120)
    scan.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pix)
    path = tmp_path / "misto.pdf"
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def engine(monkeypatch):
    eng = OpenRouterEngine(api_key="sk-test", model="z-ai/glm-4.5v")
    monkeypatch.setattr(
        eng, "_chat", lambda content, max_tokens=4096: "# Pagina trascritta dal VLM"
    )
    return eng


def test_engine_convert_renders_pages(engine, mixed_pdf):
    results = engine.convert(mixed_pdf, pages=[2])

    assert len(results) == 1
    assert results[0].page_number == 2
    assert results[0].engine == "openrouter:z-ai/glm-4.5v"
    assert "trascritta dal VLM" in results[0].markdown
    assert 0 < results[0].confidence < 1


def test_engine_chat_failure_gives_placeholder(mixed_pdf, monkeypatch):
    eng = OpenRouterEngine(api_key="sk-test")

    def boom(content, max_tokens=4096):
        raise RuntimeError("rete giù")

    monkeypatch.setattr(eng, "_chat", boom)
    results = eng.convert(mixed_pdf, pages=[1])
    assert results[0].confidence == 0.0
    assert "non convertita" in results[0].markdown


def test_suggest_topic_sanitized(engine, monkeypatch):
    monkeypatch.setattr(
        engine, "_chat", lambda content, max_tokens=4096: "  Fisica Nucleare!  "
    )
    topic = engine.suggest_topic("testo di fisica")
    assert topic == "fisicanucl"
    assert len(topic) <= 10


def test_hybrid_pipeline_routes_scan_pages(engine, mixed_pdf, tmp_path):
    result = convert(
        mixed_pdf, tmp_path / "out", llm_engine=engine, mode="hybrid",
        extract_images=False,
    )

    prov = json.loads(result.provenance_path.read_text(encoding="utf-8"))
    by_page = {b["page"]: b["engine"] for b in prov["blocks"]}
    assert by_page[1] == "native"
    assert by_page[2] == "openrouter:z-ai/glm-4.5v"

    md = result.markdown_path.read_text(encoding="utf-8")
    assert "Capitolo primo" in md
    assert "trascritta dal VLM" in md


def test_llm_mode_uses_llm_for_all_pages(engine, mixed_pdf, tmp_path):
    result = convert(
        mixed_pdf, tmp_path / "out2", llm_engine=engine, mode="llm",
        extract_images=False,
    )
    prov = json.loads(result.provenance_path.read_text(encoding="utf-8"))
    assert all(b["engine"].startswith("openrouter:") for b in prov["blocks"])
