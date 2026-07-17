from pathlib import Path

from pdf2md_pro.gui.server import _clean_path


def test_clean_path_strips_shell_escaped_spaces():
    assert _clean_path("/Volumes/Crucial\\ X9/manuali\\ architettura") == Path(
        "/Volumes/Crucial X9/manuali architettura"
    )


def test_clean_path_strips_surrounding_quotes():
    assert _clean_path("'/percorso/con spazi'") == Path("/percorso/con spazi")
    assert _clean_path('"/altro/percorso"') == Path("/altro/percorso")


def test_clean_path_plain_path_unchanged():
    assert _clean_path("/percorso/semplice") == Path("/percorso/semplice")
