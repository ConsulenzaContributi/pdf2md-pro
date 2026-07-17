"""CLI pdf2md.

  pdf2md convert INPUT.pdf [-o OUTDIR] [--pages 1-3,5] [--force] [--no-images]
  pdf2md batch SRC DEST [--max-files N] [--mode native|hybrid|llm] [--model M]
                        [--auto-split] [--split-pages N] [--split-mb M] [--no-images]
  pdf2md split INPUT.pdf [-o OUTDIR] [--max-pages N] [--max-mb M]
  pdf2md gui [--port PORT]

Retrocompatibilità: `pdf2md file.pdf ...` equivale a `pdf2md convert file.pdf ...`.
La chiave OpenRouter si passa via variabile d'ambiente OPENROUTER_API_KEY.
"""

from __future__ import annotations

import argparse
import os
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


def _cmd_convert(args) -> int:
    try:
        pages = parse_pages(args.pages)
        result = convert(
            Path(args.input),
            Path(args.out_dir),
            force=args.force,
            pages=pages,
            extract_images=not args.no_images,
        )
    except (ValueError, ConversionError) as exc:
        print(f"errore: {exc}", file=sys.stderr)
        return 2
    print(f"scritto {result.markdown_path}")
    print(f"provenienza {result.provenance_path}")
    return 0


def _cmd_batch(args) -> int:
    from pdf2md_pro.core.batch import BatchConfig, run_batch

    def show(event: dict) -> None:
        status = event.get("status")
        if status == "start":
            print(f"[{event['index']}/{event['total']}] {event['file']} ...")
        elif status == "done":
            print(f"  → {', '.join(event['outputs'])}")
        elif status == "split":
            print(f"  partizionato in {event['parts']} parti")
        elif status == "error":
            print(f"  ERRORE {event['file']}: {event['error']}", file=sys.stderr)

    config = BatchConfig(
        source_dir=Path(args.source),
        dest_dir=Path(args.dest),
        max_files=args.max_files,
        mode=args.mode,
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        model=args.model,
        auto_split=args.auto_split,
        split_pages=args.split_pages,
        split_mb=args.split_mb,
        extract_images=not args.no_images,
    )
    try:
        summary = run_batch(config, progress=show)
    except ConversionError as exc:
        print(f"errore: {exc}", file=sys.stderr)
        return 2
    print(f"convertiti {summary['converted']} file, errori {len(summary['errors'])}")
    return 0 if not summary["errors"] else 1


def _cmd_split(args) -> int:
    from pdf2md_pro.core.splitter import split_pdf

    if args.max_pages is None and args.max_mb is None:
        print("errore: indicare --max-pages e/o --max-mb", file=sys.stderr)
        return 2
    try:
        parts = split_pdf(
            Path(args.input), Path(args.out_dir), args.max_pages, args.max_mb
        )
    except Exception as exc:
        print(f"errore: {exc}", file=sys.stderr)
        return 2
    if parts == [Path(args.input)]:
        print("già nei limiti: nessuna partizione necessaria")
    else:
        for part in parts:
            print(f"scritto {part}")
    return 0


def _cmd_gui(args) -> int:
    from pdf2md_pro.gui.server import serve

    serve(port=args.port)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf2md", description="Converte PDF in Markdown con provenienza."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_convert = sub.add_parser("convert", help="converte un singolo PDF")
    p_convert.add_argument("input")
    p_convert.add_argument("-o", "--out-dir", default=".")
    p_convert.add_argument("--pages")
    p_convert.add_argument("--force", action="store_true")
    p_convert.add_argument("--no-images", action="store_true")
    p_convert.set_defaults(fn=_cmd_convert)

    p_batch = sub.add_parser("batch", help="converte una cartella di PDF")
    p_batch.add_argument("source")
    p_batch.add_argument("dest")
    p_batch.add_argument("--max-files", type=int)
    p_batch.add_argument("--mode", choices=["native", "hybrid", "llm"], default="native")
    p_batch.add_argument("--model", default="z-ai/glm-4.5v")
    p_batch.add_argument("--auto-split", action="store_true")
    p_batch.add_argument("--split-pages", type=int, default=100)
    p_batch.add_argument("--split-mb", type=float, default=10.0)
    p_batch.add_argument("--no-images", action="store_true")
    p_batch.set_defaults(fn=_cmd_batch)

    p_split = sub.add_parser("split", help="partiziona un PDF oltre i limiti")
    p_split.add_argument("input")
    p_split.add_argument("-o", "--out-dir", default=".")
    p_split.add_argument("--max-pages", type=int)
    p_split.add_argument("--max-mb", type=float)
    p_split.set_defaults(fn=_cmd_split)

    p_gui = sub.add_parser("gui", help="avvia l'interfaccia web locale")
    p_gui.add_argument("--port", type=int, default=8347)
    p_gui.set_defaults(fn=_cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0].lower().endswith(".pdf"):
        argv.insert(0, "convert")
    args = _build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
