"""Orchestrazione della conversione: valida → estrai → assembla → scrivi."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pymupdf

from pdf2md_pro.core.provenance import build_provenance, sha256_file
from pdf2md_pro.engines.native import NativeEngine
from pdf2md_pro.output.writer import render_frontmatter, write_output

import json


class ConversionError(Exception):
    """Input non convertibile o output che verrebbe sovrascritto."""


@dataclass(frozen=True)
class ConversionResult:
    markdown_path: Path
    provenance_path: Path
    image_dir: Path
    blocks: tuple[dict, ...]


def convert(
    pdf_path: Path,
    out_dir: Path,
    force: bool = False,
    pages: list[int] | None = None,
    extract_images: bool = True,
) -> ConversionResult:
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    if not pdf_path.is_file():
        raise ConversionError(f"file non trovato: {pdf_path}")

    try:
        with pymupdf.open(pdf_path) as doc:
            if doc.needs_pass:
                raise ConversionError(f"PDF cifrato, password richiesta: {pdf_path.name}")
            page_count = doc.page_count
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"PDF non leggibile: {pdf_path.name} ({exc})") from exc

    stem = pdf_path.stem
    markdown_path = out_dir / f"{stem}.md"
    provenance_path = out_dir / f"{stem}.provenance.json"
    image_dir = out_dir / "assets"
    for existing in (markdown_path, provenance_path):
        if existing.exists() and not force:
            raise ConversionError(f"output esistente (usa --force): {existing}")

    out_dir.mkdir(parents=True, exist_ok=True)
    engine = NativeEngine()
    results = engine.convert(
        pdf_path, image_dir=image_dir if extract_images else None, pages=pages
    )

    digest = sha256_file(pdf_path)
    frontmatter = {
        "title": stem,
        "source": pdf_path.name,
        "sha256": digest,
        "pages": page_count,
        "engine": f"{engine.name} {engine.version}",
        "converted": date.today().isoformat(),
    }

    # link immagini relativi: pymupdf4llm scrive percorsi assoluti
    body_parts = [
        r.markdown.replace(str(image_dir) + "/", "assets/") for r in results
    ]

    line = render_frontmatter(frontmatter).count("\n") + 1
    blocks = []
    for result, part in zip(results, body_parts):
        n_lines = part.count("\n") + (0 if part.endswith("\n") else 1)
        blocks.append(
            {
                "page": result.page_number,
                "engine": engine.name,
                "confidence": result.confidence,
                "md_start_line": line,
                "md_end_line": line + max(n_lines - 1, 0),
            }
        )
        line += n_lines + 1  # +1 per la riga vuota di separazione

    write_output("\n".join(body_parts), frontmatter, markdown_path)
    provenance = build_provenance(
        pdf_path, digest, page_count, engine.name, engine.version, blocks
    )
    provenance_path.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return ConversionResult(markdown_path, provenance_path, image_dir, tuple(blocks))
