import pymupdf
import pytest

from pdf2md_pro.core.batch import BatchConfig, run_batch


def _make_pdf(path, title, pages=1):
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_textbox(
            pymupdf.Rect(50, 50, 550, 200),
            f"# {title}\nContenuto pagina {i + 1} del documento.",
            fontsize=12,
            fontname="helv",
        )
        page.insert_textbox(
            pymupdf.Rect(50, 40, 550, 70), title, fontsize=22, fontname="helv"
        )
    doc.save(path)
    doc.close()


@pytest.fixture
def folders(tmp_path):
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    _make_pdf(src / "a.pdf", "Termodinamica Applicata")
    _make_pdf(src / "b.pdf", "Analisi Matematica")
    return src, dest


def test_batch_keeps_original_pdf_name_by_default(folders):
    src, dest = folders
    events = []
    summary = run_batch(
        BatchConfig(source_dir=src, dest_dir=dest, extract_images=False),
        progress=events.append,
    )

    assert summary["converted"] == 2
    assert summary["errors"] == []
    md_files = sorted(p.name for p in dest.glob("*.md"))
    # il md tiene lo stesso nome del pdf originale
    assert md_files == ["a.md", "b.md"]
    assert {p.name for p in dest.glob("*.provenance.json")} == {
        "a.provenance.json",
        "b.provenance.json",
    }

    statuses = [e["status"] for e in events]
    assert statuses.count("start") == 2
    assert statuses.count("done") == 2


def test_batch_rename_by_topic_when_enabled(folders):
    src, dest = folders
    run_batch(
        BatchConfig(
            source_dir=src, dest_dir=dest, extract_images=False, rename_by_topic=True
        )
    )
    md_files = sorted(p.name for p in dest.glob("*.md"))
    assert md_files != ["a.md", "b.md"]  # rinominati per argomento
    for name in md_files:
        assert len(name.removesuffix(".md")) <= 10


def test_batch_respects_max_files(folders):
    src, dest = folders
    summary = run_batch(
        BatchConfig(source_dir=src, dest_dir=dest, max_files=1, extract_images=False)
    )
    assert summary["converted"] == 1
    assert len(list(dest.glob("*.md"))) == 1


def test_batch_autosplit_produces_parts(tmp_path):
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    _make_pdf(src / "grande.pdf", "Meccanica Quantistica", pages=4)

    summary = run_batch(
        BatchConfig(
            source_dir=src,
            dest_dir=dest,
            auto_split=True,
            split_pages=2,
            split_mb=None,
            extract_images=False,
        )
    )
    # 4 pagine, limite 2: due parti, due md distinti
    assert summary["converted"] == 2
    assert len(list(dest.glob("*.md"))) == 2


def test_batch_continues_after_broken_file(folders):
    src, dest = folders
    (src / "rotto.pdf").write_bytes(b"non sono un pdf")

    summary = run_batch(
        BatchConfig(source_dir=src, dest_dir=dest, extract_images=False)
    )
    assert summary["converted"] == 2
    assert len(summary["errors"]) == 1
    assert "rotto.pdf" in summary["errors"][0]


def test_batch_stop_aborts_remaining_files(tmp_path):
    from pdf2md_pro.core.batch import JobControl

    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    for i in range(4):
        _make_pdf(src / f"doc{i}.pdf", f"Documento {i}")

    control = JobControl()
    # ferma dopo il primo file convertito
    def on_progress(event):
        if event.get("status") == "done":
            control.stop()

    summary = run_batch(
        BatchConfig(source_dir=src, dest_dir=dest, extract_images=False),
        progress=on_progress,
        control=control,
    )
    assert summary["stopped"] is True
    assert summary["converted"] == 1  # solo il primo, poi stop


def test_jobcontrol_pause_resume():
    from pdf2md_pro.core.batch import JobControl

    control = JobControl()
    assert not control.stopped
    control.pause()
    assert control.paused
    control.resume()
    assert not control.paused
    control.stop()
    assert control.stopped
