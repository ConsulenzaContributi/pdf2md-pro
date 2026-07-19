"""Orchestrazione della conversione: valida → estrai → assembla → scrivi."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pymupdf

from pdf2md_pro.core.classifier import NATIVE, classify_pdf
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


def _run_engines(
    pdf_path: Path,
    image_dir: Path | None,
    pages: list[int] | None,
    llm_engine,
    mode: str,
    margins: tuple[float, float, float, float] | None = None,
    table_strategy: str = "lines_strict",
    use_ocr: bool = False,
    force_ocr: bool = False,
    dpi: int | None = None,
    ignore_images: bool = False,
    image_size_limit: float | None = None,
    graphics_limit: int | None = None,
):
    """Ritorna (risultati ordinati per pagina, etichetta motore complessivo)."""
    native = NativeEngine()
    if mode == "native" or llm_engine is None:
        return native.convert(
            pdf_path,
            image_dir=image_dir,
            pages=pages,
            margins=margins,
            table_strategy=table_strategy,
            use_ocr=use_ocr,
            force_ocr=force_ocr,
            dpi=dpi,
            ignore_images=ignore_images,
            image_size_limit=image_size_limit,
            graphics_limit=graphics_limit,
        ), native.name
    if mode == "llm":
        return llm_engine.convert(pdf_path, pages=pages), llm_engine.name

    # hybrid: parser nativo dove c'è testo, LLM su scansioni/pagine complesse
    classes = classify_pdf(pdf_path, pages)
    native_pages = [n for n, c in classes.items() if c == NATIVE]
    llm_pages = [n for n, c in classes.items() if c != NATIVE]
    results = []
    if native_pages:
        results.extend(native.convert(
            pdf_path, image_dir=image_dir, pages=native_pages,
            margins=margins, table_strategy=table_strategy,
            use_ocr=use_ocr, force_ocr=force_ocr, dpi=dpi,
            ignore_images=ignore_images, image_size_limit=image_size_limit,
            graphics_limit=graphics_limit,
        ))
    if llm_pages:
        results.extend(llm_engine.convert(pdf_path, pages=llm_pages))
    results.sort(key=lambda r: r.page_number)
    return results, f"hybrid({native.name}+{llm_engine.name})"


def convert(
    pdf_path: Path,
    out_dir: Path,
    force: bool = False,
    pages: list[int] | None = None,
    extract_images: bool = True,
    llm_engine=None,
    mode: str = "native",
    margins: tuple[float, float, float, float] | None = None,
    table_strategy: str = "lines_strict",
    use_ocr: bool = False,
    force_ocr: bool = False,
    dpi: int | None = None,
    ignore_images: bool = False,
    image_size_limit: float | None = None,
    graphics_limit: int | None = None,
    brain_optimize: bool = False,
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
    results, engine_label = _run_engines(
        pdf_path,
        image_dir if extract_images else None,
        pages,
        llm_engine,
        mode,
        margins=margins,
        table_strategy=table_strategy,
        use_ocr=use_ocr,
        force_ocr=force_ocr,
        dpi=dpi,
        ignore_images=ignore_images,
        image_size_limit=image_size_limit,
        graphics_limit=graphics_limit,
    )

    digest = sha256_file(pdf_path)
    frontmatter = {
        "title": stem,
        "source": pdf_path.name,
        "sha256": digest,
        "pages": page_count,
        "engine": engine_label,
        "converted": date.today().isoformat(),
    }

    # link immagini relativi: pymupdf4llm scrive percorsi assoluti
    body_parts = [
        r.markdown.replace(str(image_dir) + "/", "assets/") for r in results
    ]

    if brain_optimize:
        from pdf2md_pro.core.brain import brain_frontmatter, optimize_parts

        body_parts = optimize_parts(body_parts, stem)
        frontmatter = brain_frontmatter(frontmatter, "\n".join(body_parts))

    line = render_frontmatter(frontmatter).count("\n") + 1
    blocks = []
    for result, part in zip(results, body_parts):
        n_lines = part.count("\n") + (0 if part.endswith("\n") else 1)
        blocks.append(
            {
                "page": result.page_number,
                "engine": result.engine,
                "confidence": result.confidence,
                "md_start_line": line,
                "md_end_line": line + max(n_lines - 1, 0),
            }
        )
        # il join con "\n" crea la riga vuota solo se la parte finisce già con \n
        line += n_lines + (1 if part.endswith("\n") else 0)

    write_output("\n".join(body_parts), frontmatter, markdown_path)
    provenance = build_provenance(
        pdf_path, digest, page_count, engine_label, NativeEngine.version, blocks
    )
    provenance_path.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return ConversionResult(markdown_path, provenance_path, image_dir, tuple(blocks))
