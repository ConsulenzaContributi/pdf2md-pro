import pymupdf
import pytest

from pdf2md_pro.cli import main, parse_pages


@pytest.fixture
def pdf(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(
        pymupdf.Rect(50, 50, 550, 200), "Contenuto CLI", fontsize=14, fontname="helv"
    )
    path = tmp_path / "cli.pdf"
    doc.save(path)
    doc.close()
    return path


def test_cli_converts(pdf, tmp_path):
    out = tmp_path / "out"
    assert main([str(pdf), "-o", str(out)]) == 0

    md = (out / "cli.md").read_text(encoding="utf-8")
    assert md.startswith("---\n")
    assert 'source: "cli.pdf"' in md
    assert "sha256:" in md
    assert "Contenuto CLI" in md
    assert (out / "cli.provenance.json").is_file()


def test_cli_refuses_overwrite_without_force(pdf, tmp_path):
    out = tmp_path / "out"
    assert main([str(pdf), "-o", str(out)]) == 0
    assert main([str(pdf), "-o", str(out)]) == 2
    assert main([str(pdf), "-o", str(out), "--force"]) == 0


def test_cli_missing_file(tmp_path):
    assert main([str(tmp_path / "manca.pdf"), "-o", str(tmp_path)]) == 2


def test_parse_pages():
    assert parse_pages("1-3,5") == [1, 2, 3, 5]
    assert parse_pages("2") == [2]
    assert parse_pages(None) is None
    with pytest.raises(ValueError):
        parse_pages("0")
    with pytest.raises(ValueError):
        parse_pages("3-1")
    with pytest.raises(ValueError):
        parse_pages("abc")
