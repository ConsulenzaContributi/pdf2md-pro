"""Motore nativo: estrazione deterministica via pymupdf4llm."""

from __future__ import annotations

from pathlib import Path

import pymupdf4llm

from pdf2md_pro.engines.base import PageResult

FAILED_PAGE_TEMPLATE = "> ⚠️ Pagina {page} non convertita: {error}\n"
FAILED_OCR_TEMPLATE = (
    "> ⚠️ Pagina {page} non convertita (OCR): {error} — "
    "serve Tesseract installato (brew install tesseract tesseract-lang)\n"
)
OCR_CONFIDENCE = 0.7  # testo da riconoscimento ottico: mai confidence piena


class NativeEngine:
    name = "native"
    version = pymupdf4llm.version

    def convert(
        self,
        pdf_path: Path,
        image_dir: Path | None = None,
        pages: list[int] | None = None,
        margins: tuple[float, float, float, float] | None = None,
        table_strategy: str = "lines_strict",
        use_ocr: bool = False,
        force_ocr: bool = False,
        dpi: int | None = None,
        ignore_images: bool = False,
        image_size_limit: float | None = None,
        graphics_limit: int | None = None,
    ) -> list[PageResult]:
        """Converte il PDF; `pages` è 1-based. Una pagina che fallisce non
        blocca il documento: produce un blocco segnaposto con confidence 0."""
        if use_ocr or force_ocr:
            return self._convert_with_ocr(
                pdf_path, image_dir=image_dir, pages=pages, margins=margins,
                table_strategy=table_strategy, force_ocr=force_ocr, dpi=dpi,
                ignore_images=ignore_images, image_size_limit=image_size_limit,
                graphics_limit=graphics_limit,
            )
        kwargs: dict = {"page_chunks": True}
        if pages is not None:
            kwargs["pages"] = [p - 1 for p in pages]
        if image_dir is not None:
            image_dir.mkdir(parents=True, exist_ok=True)
            kwargs.update(write_images=True, image_path=str(image_dir))

        # Opzioni avanzate (ispirate a pymupdf4llm-gui)
        kwargs["table_strategy"] = None if table_strategy == "none" else table_strategy
        if dpi:
            kwargs["dpi"] = dpi
        if ignore_images:
            kwargs["ignore_images"] = True
        if image_size_limit is not None:
            kwargs["image_size_limit"] = image_size_limit
        if graphics_limit is not None:
            kwargs["graphics_limit"] = graphics_limit

        try:
            if margins:
                return self._convert_with_cropbox(pdf_path, kwargs, margins)
            else:
                chunks = pymupdf4llm.to_markdown(str(pdf_path), **kwargs)
                return [self._chunk_to_result(i, c) for i, c in enumerate(chunks)]
        except Exception:
            return self._convert_page_by_page(pdf_path, kwargs, pages, margins)

    def _convert_with_ocr(
        self,
        pdf_path: Path,
        image_dir: Path | None,
        pages: list[int] | None,
        margins: tuple[float, float, float, float] | None,
        table_strategy: str,
        force_ocr: bool,
        dpi: int | None,
        ignore_images: bool,
        image_size_limit: float | None,
        graphics_limit: int | None,
    ) -> list[PageResult]:
        """OCR Tesseract via PyMuPDF (`get_textpage_ocr`). Con `force_ocr` tutte
        le pagine passano dall'OCR; altrimenti solo quelle senza testo
        estraibile, le restanti seguono il flusso nativo. I margini non si
        applicano alle pagine OCR (riconoscimento a pagina intera)."""
        import pymupdf

        with pymupdf.open(pdf_path) as doc:
            numbers = pages or list(range(1, doc.page_count + 1))
            if force_ocr:
                ocr_numbers = list(numbers)
            else:
                ocr_numbers = [n for n in numbers if not doc[n - 1].get_text().strip()]

        native_numbers = [n for n in numbers if n not in set(ocr_numbers)]
        results: list[PageResult] = []
        if native_numbers:
            results.extend(self.convert(
                pdf_path, image_dir=image_dir, pages=native_numbers,
                margins=margins, table_strategy=table_strategy,
                use_ocr=False, force_ocr=False, dpi=dpi,
                ignore_images=ignore_images, image_size_limit=image_size_limit,
                graphics_limit=graphics_limit,
            ))

        if ocr_numbers:
            with pymupdf.open(pdf_path) as doc:
                for number in ocr_numbers:
                    results.append(self._ocr_page(doc, number, dpi))
        results.sort(key=lambda r: r.page_number)
        return results

    @staticmethod
    def _ocr_page(doc, number: int, dpi: int | None) -> PageResult:
        page = doc[number - 1]
        # ponytail: ita+eng poi fallback eng; lingua configurabile se servirà
        for language in ("ita+eng", "eng"):
            try:
                textpage = page.get_textpage_ocr(dpi=dpi or 300, full=True, language=language)
                text = page.get_text(textpage=textpage).strip()
                return PageResult(
                    page_number=number,
                    markdown=text + "\n" if text else "",
                    confidence=OCR_CONFIDENCE if text else 0.0,
                    engine="native:ocr",
                )
            except Exception as exc:
                error = exc
        return PageResult(
            page_number=number,
            markdown=FAILED_OCR_TEMPLATE.format(page=number, error=error),
            confidence=0.0,
            engine="native:ocr",
        )

    def _convert_with_cropbox(
        self, pdf_path: Path, kwargs: dict, margins: tuple[float, float, float, float]
    ) -> list[PageResult]:
        import pymupdf
        left, top, right, bottom = margins
        doc = pymupdf.open(str(pdf_path))
        try:
            for page in doc:
                r = page.rect
                new_rect = pymupdf.Rect(
                    r.x0 + left,
                    r.y0 + top,
                    r.x1 - right,
                    r.y1 - bottom,
                )
                if new_rect.width > 0 and new_rect.height > 0:
                    try:
                        page.set_cropbox(new_rect)
                    except Exception:
                        pass
            chunks = pymupdf4llm.to_markdown(doc, **kwargs)
            return [self._chunk_to_result(i, c) for i, c in enumerate(chunks)]
        finally:
            doc.close()

    def _convert_page_by_page(
        self, 
        pdf_path: Path, 
        kwargs: dict, 
        pages: list[int] | None,
        margins: tuple[float, float, float, float] | None = None
    ) -> list[PageResult]:
        import pymupdf

        with pymupdf.open(pdf_path) as doc:
            page_numbers = pages or list(range(1, doc.page_count + 1))
            
            if margins:
                left, top, right, bottom = margins
                for page in doc:
                    r = page.rect
                    new_rect = pymupdf.Rect(r.x0 + left, r.y0 + top, r.x1 - right, r.y1 - bottom)
                    if new_rect.width > 0 and new_rect.height > 0:
                        try:
                            page.set_cropbox(new_rect)
                        except Exception:
                            pass

        results = []
        for page in page_numbers:
            single = dict(kwargs, pages=[page - 1])
            try:
                if margins:
                    # Passiamo il document ricaricato o il path. 
                    # Siccome pymupdf4llm accetta doc, potremmo ripassare doc aperto, 
                    # ma siccome to_markdown chiude i path e doc lo lasciamo gestire qui...
                    # In realtà pymupdf4llm.to_markdown accetta str o doc. 
                    # Se ricarichiamo doc:
                    with pymupdf.open(pdf_path) as doc2:
                        left, top, right, bottom = margins
                        for p in doc2:
                            r = p.rect
                            new_rect = pymupdf.Rect(r.x0 + left, r.y0 + top, r.x1 - right, r.y1 - bottom)
                            if new_rect.width > 0 and new_rect.height > 0:
                                try:
                                    p.set_cropbox(new_rect)
                                except Exception:
                                    pass
                        chunks = pymupdf4llm.to_markdown(doc2, **single)
                else:
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
