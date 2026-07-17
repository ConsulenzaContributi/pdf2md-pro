"""Motore nativo: estrazione deterministica via pymupdf4llm."""

from __future__ import annotations

from pathlib import Path

import pymupdf4llm

from pdf2md_pro.engines.base import PageResult

FAILED_PAGE_TEMPLATE = "> ⚠️ Pagina {page} non convertita: {error}\n"


class NativeEngine:
    name = "native"
    version = pymupdf4llm.version

    def convert(
        self,
        pdf_path: Path,
        image_dir: Path | None = None,
        pages: list[int] | None = None,
    ) -> list[PageResult]:
        """Converte il PDF; `pages` è 1-based. Una pagina che fallisce non
        blocca il documento: produce un blocco segnaposto con confidence 0."""
        kwargs: dict = {"page_chunks": True}
        if pages is not None:
            kwargs["pages"] = [p - 1 for p in pages]
        if image_dir is not None:
            image_dir.mkdir(parents=True, exist_ok=True)
            kwargs.update(write_images=True, image_path=str(image_dir))

        try:
            chunks = pymupdf4llm.to_markdown(str(pdf_path), **kwargs)
            return [self._chunk_to_result(i, c) for i, c in enumerate(chunks)]
        except Exception:
            return self._convert_page_by_page(pdf_path, kwargs, pages)

    def _convert_page_by_page(
        self, pdf_path: Path, kwargs: dict, pages: list[int] | None
    ) -> list[PageResult]:
        import pymupdf

        with pymupdf.open(pdf_path) as doc:
            page_numbers = pages or list(range(1, doc.page_count + 1))
        results = []
        for page in page_numbers:
            single = dict(kwargs, pages=[page - 1])
            try:
                chunks = pymupdf4llm.to_markdown(str(pdf_path), **single)
                results.append(self._chunk_to_result(page - 1, chunks[0]))
            except Exception as exc:  # la pagina rotta diventa segnaposto
                results.append(
                    PageResult(
                        page_number=page,
                        markdown=FAILED_PAGE_TEMPLATE.format(page=page, error=exc),
                        confidence=0.0,
                    )
                )
        return results

    @staticmethod
    def _chunk_to_result(index: int, chunk: dict) -> PageResult:
        metadata = chunk.get("metadata") or {}
        page_number = metadata.get("page") or index + 1
        markdown = chunk.get("text") or chunk.get("md") or ""
        return PageResult(page_number=page_number, markdown=markdown)
