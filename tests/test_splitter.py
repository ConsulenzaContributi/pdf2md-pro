import pymupdf
import pytest

from pdf2md_pro.core.splitter import needs_split, split_pdf


@pytest.fixture
def six_pages(tmp_path):
    doc = pymupdf.open()
    for i in range(1, 7):
        page = doc.new_page()
        page.insert_text(pymupdf.Point(72, 72), f"PAGINA {i}", fontsize=14)
    path = tmp_path / "sei.pdf"
    doc.save(path)
    doc.close()
    return path


def _pages_text(path):
    with pymupdf.open(path) as doc:
        return [page.get_text().strip() for page in doc]


def test_needs_split(six_pages):
    assert needs_split(six_pages, max_pages=5, max_mb=None)
    assert not needs_split(six_pages, max_pages=6, max_mb=None)
    assert needs_split(six_pages, max_pages=None, max_mb=0.000001)
    assert not needs_split(six_pages, max_pages=None, max_mb=100)


def test_split_by_pages(six_pages, tmp_path):
    out = tmp_path / "parti"
    parts = split_pdf(six_pages, out, max_pages=2, max_mb=None)

    assert [p.name for p in parts] == [
        "sei_part01.pdf",
        "sei_part02.pdf",
        "sei_part03.pdf",
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
    assert [_pages_text(p)[0] for p in parts] == [f"PAGINA {i}" for i in range(1, 7)]


def test_no_split_needed_returns_original(six_pages, tmp_path):
    parts = split_pdf(six_pages, tmp_path / "p", max_pages=10, max_mb=None)
    assert parts == [six_pages]
