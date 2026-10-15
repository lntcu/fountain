from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .classify import classify_page
from .extract import ProgressCallback, extract_pdf
from .model import ConversionResult, ConversionStats, ConversionWarning, Element
from .titlepage import extract_title_page


@dataclass(frozen=True)
class ConversionOptions:
    ocr: str = "auto"
    ocr_language: str = "eng"
    page_breaks: bool = True
    keep_revision_marks: bool = False


def _escape_action(text: str) -> str:
    # Prevent uppercase action from being parsed as a character cue.
    letters = [char for char in text if char.isalpha()]
    if letters and all(char.isupper() for char in letters) and "\n" not in text:
        return "!" + text
    return text


def _render(elements: list[Element]) -> str:
    output = ""
    previous_kind: str | None = None
    for element in elements:
        if element.kind == "scene":
            text = element.text
            if not text.upper().startswith(("INT.", "EXT.", "INT/EXT.", "I/E.", "EST.")):
                text = "." + text
        elif element.kind == "transition":
            text = ">" + element.text
        elif element.kind == "character":
            text = element.text + (" ^" if element.dual else "")
        elif element.kind == "action":
            text = _escape_action(element.text)
        elif element.kind == "centered":
            text = f">{element.text}<"
        else:
            text = element.text
        if not text.strip():
            continue
        # Fountain dialogue is contiguous: a blank line between the cue,
        # parenthetical, and speech would turn it back into ordinary action.
        if element.kind == "character":
            if output and previous_kind not in {"character", "parenthetical"}:
                output = output.rstrip() + "\n\n"
            output += text + "\n"
        elif element.kind == "parenthetical":
            if output and previous_kind in {"character", "dialogue", "parenthetical"}:
                output = output.rstrip() + "\n"
            elif output:
                output = output.rstrip() + "\n\n"
            output += text + "\n"
        elif element.kind == "dialogue":
            output += text + "\n\n"
        else:
            output = output.rstrip() + ("\n\n" if output else "") + text + "\n\n"
        previous_kind = element.kind
    return output.rstrip()


def _validate(elements: list[Element], pages: int) -> tuple[ConversionStats, list[ConversionWarning]]:
    warnings: list[ConversionWarning] = []
    confidences = [element.confidence for element in elements]
    stats = ConversionStats(
        pages=pages,
        scenes=sum(element.kind == "scene" for element in elements),
        dialogue_blocks=sum(element.kind == "dialogue" for element in elements),
        action_blocks=sum(element.kind == "action" for element in elements),
        transitions=sum(element.kind == "transition" for element in elements),
        words=sum(len(element.text.split()) for element in elements),
        confidence=sum(confidences) / len(confidences) if confidences else 0.0,
    )
    for index, element in enumerate(elements):
        if element.kind == "character":
            next_kind = elements[index + 1].kind if index + 1 < len(elements) else None
            if next_kind not in {"dialogue", "parenthetical"}:
                warnings.append(ConversionWarning(
                    "orphan-character", f"Character cue has no dialogue: {element.text}", element.page
                ))
    if stats.scenes == 0 and pages > 1:
        warnings.append(ConversionWarning("no-scenes", "No scene headings were confidently detected."))
    if stats.dialogue_blocks == 0 and pages > 1:
        warnings.append(ConversionWarning("no-dialogue", "No dialogue was confidently detected."))
    return stats, warnings


def convert_pdf(
    input_path: str | Path,
    options: ConversionOptions | None = None,
    progress: ProgressCallback | None = None,
) -> ConversionResult:
    path = Path(input_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Input PDF does not exist: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Input must have a .pdf extension: {path}")
    options = options or ConversionOptions()
    pages, warnings, metadata = extract_pdf(
        path, ocr=options.ocr, ocr_language=options.ocr_language, progress=progress
    )
    if not pages:
        raise ValueError("PDF contains no pages.")

    title, consumed_first = extract_title_page(pages[0], metadata)
    all_elements: list[Element] = []
    rendered_pages: list[str] = []
    body_pages = pages[1:] if consumed_first else pages
    for index, page in enumerate(body_pages):
        if progress:
            progress("Analyzing", index, len(body_pages))
        elements, page_warnings = classify_page(page, keep_revision_marks=options.keep_revision_marks)
        all_elements.extend(elements)
        warnings.extend(page_warnings)
        rendered = _render(elements)
        if rendered:
            rendered_pages.append(rendered)
    if progress:
        progress("Analyzing", len(body_pages), len(body_pages))

    separator = "\n\n===\n\n" if options.page_breaks else "\n\n"
    body = separator.join(rendered_pages)
    fountain = ((title + "\n\n") if title else "") + body
    fountain = fountain.rstrip() + "\n"
    stats, validation_warnings = _validate(all_elements, len(pages))
    stats.ocr_pages = sum(page.used_ocr for page in pages)
    warnings.extend(validation_warnings)
    severe = sum(warning.code in {"low-text-page", "ocr-unavailable"} for warning in warnings)
    orphaned = sum(warning.code == "orphan-character" for warning in warnings)
    ocr_penalty = 0.15 * stats.ocr_pages / max(stats.pages, 1)
    stats.confidence = max(
        0.0, stats.confidence - min(0.50, severe * 0.08 + orphaned * 0.01 + ocr_penalty)
    )
    return ConversionResult(path, fountain, stats, warnings)

