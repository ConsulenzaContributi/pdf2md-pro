"""Ottimizzazione Second Brain: heading, reflow, dedup, attribution, verifica."""

import pymupdf

from pdf2md_pro.core.brain import brain_frontmatter, check_markdown, optimize_parts
from pdf2md_pro.core.pipeline import convert


def test_heading_h1_unico_e_livelli_senza_salti():
    # Arrange: H1 nel corpo + salto H2→H5
    parts = [
        "# Capitolo Uno\n\ntesto.\n\n##### Sottosezione profonda\n\naltro testo.",
        "## Capitolo Due\n\ntesto due.",
    ]

    # Act
    out = optimize_parts(parts, "Titolo Documento")
    joined = "\n".join(out)

    # Assert
    h1 = [l for l in joined.splitlines() if l.startswith("# ") and not l.startswith("## ")]
    assert h1 == ["# Titolo Documento"]
    assert "## Capitolo Uno" in joined
    assert "### Sottosezione profonda" in joined  # H5 → max last+1
    assert "#####" not in joined


def test_reflow_sillabazione_tra_pagine():
    parts = ["Testo che finisce con la paro-", "la spezzata e continua."]

    out = optimize_parts(parts, "T")

    assert "parola" in "\n".join(out)
    assert "paro-" not in "\n".join(out)


def test_dedup_header_ripetuto():
    header = "RIVISTA TECNICA MENSILE"
    parts = [f"{header}\n\nContenuto pagina {i}.\n\n{i}" for i in range(1, 6)]

    out = optimize_parts(parts, "T")
    joined = "\n".join(out)

    assert header not in joined
    assert "Contenuto pagina 3." in joined


def test_attribution_aggiunta_da_convert(tmp_path):
    # l'attribution (strumento, motore, tempo, config) la aggiunge
    # pipeline.convert() per tutti i file, non optimize_parts
    pdf = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Contenuto di prova.")
    doc.save(pdf)
    doc.close()

    result = convert(pdf, tmp_path / "out", extract_images=False, brain_optimize=True)
    md = result.markdown_path.read_text(encoding="utf-8")

    assert "pdf2md-pro" in md
    assert "second brain" in md


def test_frontmatter_arricchito():
    fm = brain_frontmatter({"title": "doc-prova"}, "# Titolo\n\ntesto sul bilancio.")

    assert fm["optimized"] == "second-brain"
    assert fm["type"] == "pdf-import"
    assert "pdf-import" in fm["tags"]
    assert fm["aliases"] == ["doc-prova"]
    assert "pdf2md-pro v" in fm["processed_with"]


def test_check_su_file_ottimizzato_e_non(tmp_path):
    # Arrange: conversione reale con e senza ottimizzazione
    pdf = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Contenuto di prova per il second brain.")
    doc.save(pdf)
    doc.close()

    plain = convert(pdf, tmp_path / "plain", extract_images=False)
    brain = convert(pdf, tmp_path / "brain", extract_images=False, brain_optimize=True)

    # Act
    plain_report = check_markdown(plain.markdown_path.read_text(encoding="utf-8"))
    brain_report = check_markdown(brain.markdown_path.read_text(encoding="utf-8"))

    # Assert
    assert plain_report["optimized"] is False
    assert brain_report["optimized"] is True, brain_report["checks"]


def test_wikilink_seed_nel_file_ottimizzato():
    out = optimize_parts(["# Bilancio\n\nAnalisi del bilancio aziendale."], "doc-prova")
    joined = "\n".join(out)

    assert "[[" in joined and "]]" in joined
    assert "*Argomenti:" in joined


def test_check_folder_orfani_e_duplicati(tmp_path):
    from pdf2md_pro.core.brain import check_folder

    # due fonti con lo stesso H1, nessun index.md
    (tmp_path / "uno.md").write_text("# Stesso Titolo\n\ntesto uno.", encoding="utf-8")
    (tmp_path / "due.md").write_text("# Stesso Titolo\n\ntesto due.", encoding="utf-8")
    (tmp_path / "pdf2md-report_x.md").write_text("# Report", encoding="utf-8")  # ignorato

    report = check_folder(tmp_path)

    assert report["total"] == 2
    assert report["has_index"] is False
    assert sorted(report["orphans"]) == ["due.md", "uno.md"]
    assert report["duplicate_titles"] == {"Stesso Titolo": ["due.md", "uno.md"]}


def test_check_folder_index_completo(tmp_path):
    from pdf2md_pro.core.brain import check_folder

    (tmp_path / "uno.md").write_text("# Uno\n\ntesto.", encoding="utf-8")
    (tmp_path / "index.md").write_text("# Indice\n\n- [uno](uno.md) — testo.", encoding="utf-8")

    report = check_folder(tmp_path)

    assert report["orphans"] == []
    assert report["duplicate_titles"] == {}
    assert report["has_index"] is True


def test_provenance_coerente_dopo_ottimizzazione(tmp_path):
    import json

    pdf = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_text((72, 72), "Testo pagina.")
    doc.save(pdf)
    doc.close()

    result = convert(pdf, tmp_path / "out", extract_images=False, brain_optimize=True)
    md_lines = result.markdown_path.read_text(encoding="utf-8").splitlines()
    prov = json.loads(result.provenance_path.read_text(encoding="utf-8"))

    for block in prov["blocks"]:
        assert 1 <= block["md_start_line"] <= block["md_end_line"] <= len(md_lines)
