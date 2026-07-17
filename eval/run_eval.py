"""Harness di valutazione: converte il corpus e misura la qualità.

Metriche per documento:
- recall parole: frazione delle parole attese presenti nel Markdown
- similarità: difflib.SequenceMatcher su testo normalizzato

Uso: python eval/run_eval.py
"""

from __future__ import annotations

import contextlib
import difflib
import os
import re
import sys
import tempfile
from pathlib import Path


@contextlib.contextmanager
def silence_stdout():
    """Silenzia anche le scritture C-level (libmupdf) che bypassano sys.stdout."""
    sys.stdout.flush()
    saved_fd = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved_fd, 1)
        os.close(saved_fd)
        os.close(devnull)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pdf2md_pro.core.pipeline import convert  # noqa: E402

CORPUS_DIR = Path(__file__).parent / "corpus"

MD_SYNTAX = re.compile(r"[#*_`>|\[\]()!-]|^---$", re.MULTILINE)


def normalize(text: str) -> str:
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)  # frontmatter
    text = MD_SYNTAX.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def evaluate(pdf_path: Path, expected_path: Path) -> tuple[float, float]:
    with tempfile.TemporaryDirectory() as tmp:
        with silence_stdout():
            result = convert(pdf_path, Path(tmp), extract_images=False)
        got = normalize(result.markdown_path.read_text(encoding="utf-8"))
    expected = normalize(expected_path.read_text(encoding="utf-8"))

    expected_words = expected.split()
    got_words = set(got.split())
    recall = (
        sum(1 for w in expected_words if w in got_words) / len(expected_words)
        if expected_words
        else 0.0
    )
    similarity = difflib.SequenceMatcher(None, expected, got).ratio()
    return recall, similarity


def main() -> int:
    pdfs = sorted(CORPUS_DIR.glob("*.pdf"))
    if not pdfs:
        print("corpus vuoto: eseguire prima eval/make_corpus.py", file=sys.stderr)
        return 1

    print(f"{'documento':<12} {'recall':>7} {'simil.':>7}")
    recalls = []
    for pdf in pdfs:
        recall, similarity = evaluate(pdf, pdf.with_suffix("").with_suffix(".expected.txt"))
        recalls.append(recall)
        print(f"{pdf.stem:<12} {recall:>7.2f} {similarity:>7.2f}")
    print(f"{'MEDIA':<12} {sum(recalls) / len(recalls):>7.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
