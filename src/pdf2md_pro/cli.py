"""CLI: pdf2md INPUT.pdf [-o OUTDIR] [--pages 1-3,5] [--force] [--no-images]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pdf2md_pro.core.pipeline import ConversionError, convert


def parse_pages(spec: str | None) -> list[int] | None:
    """"1-3,5" → [1, 2, 3, 5]. Pagine 1-based, range crescenti."""
    if spec is None:
        return None
    pages: list[int] = []
    for token in spec.split(","):
        token = token.strip()
        if "-" in token:
            start_s, end_s = token.split("-", 1)
            start, end = int(start_s), int(end_s)
            if start < 1 or end < start:
                raise ValueError(f"range pagine non valido: {token}")
            pages.extend(range(start, end + 1))
        else:
            page = int(token)
            if page < 1:
                raise ValueError(f"numero pagina non valido: {token}")
            pages.append(page)
    return pages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdf2md", description="Converte PDF in Markdown con provenienza."
    )
    parser.add_argument("input", help="file PDF da convertire")
    parser.add_argument("-o", "--out-dir", default=".", help="cartella di output")
    parser.add_argument("--pages", help="pagine da convertire, es. 1-3,5")
    parser.add_argument("--force", action="store_true", help="sovrascrive output esistente")
    parser.add_argument("--no-images", action="store_true", help="non estrarre immagini")
    args = parser.parse_args(argv)

    try:
        pages = parse_pages(args.pages)
    except ValueError as exc:
        print(f"errore: {exc}", file=sys.stderr)
        return 2

    try:
        result = convert(
            Path(args.input),
            Path(args.out_dir),
            force=args.force,
            pages=pages,
            extract_images=not args.no_images,
        )
    except ConversionError as exc:
        print(f"errore: {exc}", file=sys.stderr)
        return 2

    print(f"scritto {result.markdown_path}")
    print(f"provenienza {result.provenance_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
