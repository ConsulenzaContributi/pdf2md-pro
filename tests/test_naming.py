from pdf2md_pro.core.naming import derive_topic, slugify_topic, unique_path


def test_topic_from_heading():
    md = "---\ntitle: x\n---\n\n# Analisi Spettrale Avanzata\n\ntesto"
    assert derive_topic(md) == "analisispe"
    assert len(derive_topic(md)) <= 10


def test_topic_from_first_line_when_no_heading():
    assert derive_topic("Relazione tecnica 2026\naltro") == "relazione"


def test_topic_word_longer_than_limit_is_truncated():
    assert derive_topic("# Elettroencefalogramma") == "elettroenc"


def test_topic_fallback():
    assert derive_topic("") == "doc"
    assert derive_topic("---\na: 1\n---\n") == "doc"


def test_topic_strips_accents_and_symbols():
    assert derive_topic("# Città & Località!") == "cittalocal"


def test_slugify_topic_sanitizes_llm_output():
    assert slugify_topic("  Fisica Quantistica  ") == "fisicaquan"
    assert slugify_topic("π-mesone") == "mesone"
    assert slugify_topic("!!!") == "doc"


def test_unique_path(tmp_path):
    first = unique_path(tmp_path, "tema", ".md")
    assert first.name == "tema.md"
    first.write_text("x")
    second = unique_path(tmp_path, "tema", ".md")
    assert second.name == "tema-2.md"
    second.write_text("x")
    assert unique_path(tmp_path, "tema", ".md").name == "tema-3.md"
