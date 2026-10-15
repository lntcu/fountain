from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from pathlib import Path

import pymupdf

from .model import ConversionWarning, Line, PageData

ProgressCallback = Callable[[str, int, int], None]

_LIGATURES = str.maketrans({
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "\u00ad": "", "\u2011": "-", "\u2013": "-", "\u2014": "-",
})


class PdfExtractionError(RuntimeError):
    pass


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text.translate(_LIGATURES))
    text = text.replace("\x00", "").replace("\r", " ").replace("\n", " ")
    return re.sub(r"[ \t]+", " ", text).strip()


def _extract_lines(page: pymupdf.Page, textpage: pymupdf.TextPage | None = None) -> list[Line]:
    data = page.get_text("dict", textpage=textpage, sort=True)
    found: list[Line] = []
    seen: set[tuple[int, int, int, int, str]] = set()
    for block in data.get("blocks", []):
        for raw_line in block.get("lines", []):
            spans = raw_line.get("spans", [])
            text = clean_text("".join(span.get("text", "") for span in spans))
            if not text:
                continue
            x0, y0, x1, y1 = map(float, raw_line["bbox"])
            key = (round(x0 * 2), round(y0 * 2), round(x1 * 2), round(y1 * 2), text)
            # Some PDFs contain two identical text layers. Keeping both corrupts dialogue.
            if key in seen:
                continue
            seen.add(key)
            sizes = [float(span.get("size", 12.0)) for span in spans if span.get("text", "").strip()]
            found.append(Line(page.number + 1, x0, y0, x1, y1, text, max(sizes, default=12.0)))
    return sorted(found, key=lambda line: (round(line.y0, 1), line.x0))


def _coalesce_ocr_lines(lines: list[Line]) -> list[Line]:
    """Rejoin word boxes that Tesseract exposes as separate PDF lines."""
    rows: list[list[Line]] = []
    for line in lines:
        row = next((candidate for candidate in reversed(rows) if abs(candidate[0].y0 - line.y0) < 2.5), None)
        if row is None:
            rows.append([line])
        else:
            row.append(line)
    result: list[Line] = []
    for row in rows:
        row.sort(key=lambda item: item.x0)
        clusters: list[list[Line]] = [[row[0]]]
        for line in row[1:]:
            previous = clusters[-1][-1]
            if line.x0 - previous.x1 > max(36.0, previous.size * 4.0):
                clusters.append([line])
            else:
                clusters[-1].append(line)
        for cluster in clusters:
            first, last = cluster[0], cluster[-1]
            result.append(Line(
                first.page, first.x0, min(item.y0 for item in cluster), last.x1,
                max(item.y1 for item in cluster), " ".join(item.text for item in cluster),
                max(item.size for item in cluster),
            ))
    return sorted(result, key=lambda line: (round(line.y0, 1), line.x0))


def extract_pdf(
    path: Path,
    *,
    ocr: str = "auto",
    ocr_language: str = "eng",
    progress: ProgressCallback | None = None,
) -> tuple[list[PageData], list[ConversionWarning], dict[str, str]]:
    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise PdfExtractionError(f"Cannot open PDF: {exc}") from exc
    if document.needs_pass:
        document.close()
        raise PdfExtractionError("The PDF is encrypted. Supply an unencrypted copy.")
    if not document.is_pdf:
        document.close()
        raise PdfExtractionError("Input is not a valid PDF.")

    warnings: list[ConversionWarning] = []
    pages: list[PageData] = []
    total = len(document)
    try:
        for index, page in enumerate(document):
            if progress:
                progress("Extracting", index, total)
            lines = _extract_lines(page)
            word_count = sum(len(line.text.split()) for line in lines)
            used_ocr = False
            if ocr == "always" or (ocr == "auto" and word_count < 8):
                try:
                    textpage = page.get_textpage_ocr(language=ocr_language, dpi=300, full=True)
                    ocr_lines = _extract_lines(page, textpage)
                    if len(ocr_lines) > len(lines):
                        lines, used_ocr = _coalesce_ocr_lines(ocr_lines), True
                except Exception as exc:
                    if ocr == "always" or word_count < 8:
                        warnings.append(ConversionWarning(
                            "ocr-unavailable",
                            f"OCR was needed but failed ({type(exc).__name__}). Install Tesseract language data for '{ocr_language}'.",
                            index + 1,
                        ))
            if sum(len(line.text.split()) for line in lines) < 8:
                warnings.append(ConversionWarning(
                    "low-text-page", "Very little text was recoverable from this page.", index + 1
                ))
            if used_ocr:
                warnings.append(ConversionWarning(
                    "ocr-used", "This page was reconstructed with OCR and should receive visual review.", index + 1
                ))
            pages.append(PageData(index + 1, page.rect.width, page.rect.height, lines, used_ocr))
        if progress:
            progress("Extracting", total, total)
        metadata = {key: clean_text(str(value)) for key, value in document.metadata.items() if value}
        return pages, warnings, metadata
    finally:
        document.close()

