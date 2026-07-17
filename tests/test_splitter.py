import pymupdf
import pytest

from pdf2md_pro.core.splitter import needs_split, split_folder, split_pdf


def _make_pdf(path, pages):
    doc = pymupdf.open()
    for i in range(1, pages + 1):
        page = doc.new_page()
        page.insert_text(pymupdf.Point(72, 72), f"PAGINA {i}", fontsize=14)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def six_pages(tmp_path):
    return _make_pdf(tmp_path / "sei.pdf", 6)


def _pages_text(path):
    with pymupdf.open(path) as doc:
        return [page.get_text().strip() for page in doc]


def test_needs_split(six_pages):
    assert needs_split(six_pages, max_pages=5, max_mb=None)
    assert not needs_split(six_pages, max_pages=6, max_mb=None)
    assert needs_split(six_pages, max_pages=None, max_mb=0.000001)
    assert not needs_split(six_pages, max_pages=None, max_mb=100)
    # limiti congiunti: basta superarne uno
    assert needs_split(six_pages, max_pages=100, max_mb=0.000001)
    assert needs_split(six_pages, max_pages=2, max_mb=100)


def test_split_by_pages_names_total_and_sequence(six_pages, tmp_path):
    out = tmp_path / "parti"
    parts = split_pdf(six_pages, out, max_pages=2, max_mb=None)

    assert [p.name for p in parts] == [
        "sei 03 01.pdf",
        "sei 03 02.pdf",
        "sei 03 03.pdf",
    ]
    collected = []
    for part in parts:
        text = _pages_text(part)
        assert len(text) == 2
        collected.extend(text)
    assert collected == [f"PAGINA {i}" for i in range(1, 7)]


def test_split_by_size_forces_single_pages(six_pages, tmp_path):
    parts = split_pdf(six_pages, tmp_path / "p", max_pages=None, max_mb=0.000001)
    # nessuna pagina rientra nel limite: bisezione fino a pagine singole
    assert len(parts) == 6
    assert parts[0].name == "sei 06 01.pdf"
    assert [_pages_text(p)[0] for p in parts] == [f"PAGINA {i}" for i in range(1, 7)]


def test_no_split_needed_returns_original(six_pages, tmp_path):
    parts = split_pdf(six_pages, tmp_path / "p", max_pages=10, max_mb=None)
    assert parts == [six_pages]


def test_split_folder_selects_only_oversized(tmp_path):
    src = tmp_path / "src"
    out = tmp_path / "out"
    src.mkdir()
    _make_pdf(src / "grande.pdf", 5)
    _make_pdf(src / "piccolo.pdf", 2)
    (src / "rotto.pdf").write_bytes(b"non-pdf")

    events = []
    summary = split_folder(src, out, max_pages=2, max_mb=None, progress=events.append)

    assert summary["split"]["grande.pdf"] == [
        "grande 03 01.pdf",
        "grande 03 02.pdf",
        "grande 03 03.pdf",
    ]
    assert summary["skipped"] == ["piccolo.pdf"]
    assert len(summary["errors"]) == 1 and "rotto.pdf" in summary["errors"][0]
    assert (out / "grande 03 01.pdf").is_file()
    assert not (out / "piccolo 01 01.pdf").exists()

    statuses = [e["status"] for e in events]
    assert "split" in statuses and "skip" in statuses and "error" in statuses


def test_split_folder_joint_limits(tmp_path):
    """Un file oltre le pagine, uno oltre i MB: entrambi selezionati."""
    src = tmp_path / "src"
    src.mkdir()
    _make_pdf(src / "tante_pagine.pdf", 4)
    big = _make_pdf(src / "pesante.pdf", 2)
    size_mb = big.stat().st_size / (1024 * 1024)

    summary = split_folder(
        src, tmp_path / "out", max_pages=3, max_mb=size_mb * 0.9
    )
    assert set(summary["split"]) == {"tante_pagine.pdf", "pesante.pdf"}
