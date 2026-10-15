from __future__ import annotations

import re

from .model import ConversionWarning, Element, Line, PageData

_SCENE_PREFIX = re.compile(
    r"^(?:(?:\d+[A-Z]*\s+)?(?:INT\.?|EXT\.?|INT\.?/EXT\.?|EXT\.?/INT\.?|I/E\.?|EST\.?)(?:\s|$))",
    re.IGNORECASE,
)
_TRANSITION = re.compile(
    r"^(?:FADE (?:IN|OUT|TO BLACK)(?: ON)?|CUT TO|SMASH CUT TO|MATCH CUT TO|DISSOLVE TO|WIPE TO|BACK TO|TIME CUT|INTERCUT(?: WITH)?|TO WHITE)(?::|\.)?$",
    re.IGNORECASE,
)
_PAGE_NUMBER = re.compile(r"^(?:\d+|[ivxlcdm]+)\.?$", re.IGNORECASE)
_SCENE_NUMBER = re.compile(r"^\d+[A-Za-z]*(?:[-.]?\d+[A-Za-z]*)?$|^\d+[A-Za-z]+[A-Za-z0-9]*$")
_CONTINUATION = re.compile(r"^\((?:CONTINUED|MORE)\)$", re.IGNORECASE)
_CHARACTER = re.compile(r"^[“\"']?[A-Z0-9][A-Z0-9 .,'’\-/#&]*[”\"']?$")


def _is_upper(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    return bool(letters) and all(char.isupper() for char in letters)


def _cue_core(text: str) -> str:
    return re.sub(r"(?:\s*\([^)]*\))+\s*$", "", text).strip()


def _join_wrapped(parts: list[str]) -> str:
    result = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not result:
            result = part
        elif result.endswith("-") and not result.endswith("--") and part[0].islower():
            result += part
        else:
            result += " " + part
    return result


def _strip_noise(page: PageData, keep_revision_marks: bool) -> list[Line]:
    useful: list[Line] = []
    for line in page.lines:
        text = line.text.strip()
        if line.y0 < 58 and (_PAGE_NUMBER.fullmatch(text) or "Rev." in text or "Revision" in text):
            continue
        if line.y0 > page.height - 42 and _PAGE_NUMBER.fullmatch(text):
            continue
        if line.x0 < page.width * 0.14 and _SCENE_NUMBER.fullmatch(text):
            continue
        if line.x0 > page.width * 0.82 and _SCENE_NUMBER.fullmatch(text):
            continue
        if not keep_revision_marks:
            if line.x0 > page.width * 0.88 and text in {"*", "#"}:
                continue
            text = re.sub(r"\s+[*#]+$", "", text).rstrip()
            if text != line.text:
                line = Line(line.page, line.x0, line.y0, line.x1, line.y1, text, line.size)
        if _CONTINUATION.fullmatch(text):
            continue
        useful.append(line)

    # Final Draft sometimes stores (CONT'D) as a distinct span/line beside
    # the cue. Recombine it before classification so the following speech is
    # not mistaken for action.
    combined: list[Line] = []
    for line in useful:
        if (
            combined
            and abs(line.y0 - combined[-1].y0) < 2
            and bool(re.fullmatch(r"\((?:CONT['’]?D|MORE)\)", line.text, re.IGNORECASE))
            and _character_line(combined[-1], page.width)
        ):
            previous = combined[-1]
            combined[-1] = Line(
                previous.page, previous.x0, previous.y0, max(previous.x1, line.x1),
                max(previous.y1, line.y1), f"{previous.text} {line.text}", max(previous.size, line.size)
            )
        else:
            combined.append(line)
    return combined


def _character_line(line: Line, width: float) -> bool:
    # Qualifiers such as (O.S.), (V.O.), and (cont’d) may legitimately use
    # lowercase even though the actual cue is uppercase.
    cue = _cue_core(line.text)
    return (
        width * 0.30 <= line.x0 <= width * 0.72
        and len(line.text) <= 55
        and bool(_CHARACTER.fullmatch(cue))
        and not _TRANSITION.fullmatch(line.text)
    )


def _left_dual_cue(line: Line, width: float) -> bool:
    core = _cue_core(line.text)
    return (
        width * 0.16 <= line.x0 < width * 0.38
        and len(line.text) <= 55
        and bool(_CHARACTER.fullmatch(core))
    )


def _dual_at(lines: list[Line], index: int, width: float) -> tuple[list[Element], int] | None:
    first = lines[index]
    peers = [
        (j, line) for j, line in enumerate(lines[index + 1 :], index + 1)
        if abs(line.y0 - first.y0) < 2.0
    ]
    if not _left_dual_cue(first, width):
        return None
    def is_translation_label(candidate: Line) -> bool:
        text = candidate.text
        return (
            candidate.x0 > width * 0.55
            and text.startswith("(") and text.endswith(")")
            and _is_upper(text[1:-1])
        )

    right = next((
        pair for pair in peers
        if pair[1].x0 > width * 0.55
        and (_character_line(pair[1], width) or is_translation_label(pair[1]))
    ), None)
    if first.x0 >= width * 0.38 or right is None:
        return None
    right_index, right_cue = right
    end_y = first.y0 + 13
    scan = right_index + 1
    last_y = first.y0
    while scan < len(lines):
        candidate = lines[scan]
        if candidate.y0 - last_y >= 22 and candidate.x0 < width * 0.25:
            break
        if (_character_line(candidate, width) or _left_dual_cue(candidate, width)) and candidate.y0 > first.y0 + 2:
            break
        end_y = max(end_y, candidate.y0 + 1)
        last_y = max(last_y, candidate.y0)
        scan += 1
    region = [line for line in lines[index:scan] if line.y0 <= end_y]
    left_text = [line.text for line in region if line.y0 > first.y0 + 2 and line.x0 < width * 0.49]
    right_text = [line.text for line in region if line.y0 > first.y0 + 2 and line.x0 >= width * 0.49]
    elements = [Element("character", first.text, first.page, 0.98)]
    if left_text:
        elements.append(Element("dialogue", _join_wrapped(left_text), first.page, 0.92))
    right_cue_text = right_cue.text[1:-1] if is_translation_label(right_cue) else right_cue.text
    elements.append(Element("character", right_cue_text, first.page, 0.98, dual=True))
    if right_text:
        elements.append(Element("dialogue", _join_wrapped(right_text), first.page, 0.92))
    return elements, scan


def classify_page(page: PageData, *, keep_revision_marks: bool = False) -> tuple[list[Element], list[ConversionWarning]]:
    lines = _strip_noise(page, keep_revision_marks)
    warnings: list[ConversionWarning] = []
    elements: list[Element] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        dual = _dual_at(lines, i, page.width)
        if dual:
            dual_elements, i = dual
            elements.extend(dual_elements)
            continue
        text = line.text
        gap_before = line.y0 - lines[i - 1].y1 if i else 99.0

        if _TRANSITION.fullmatch(text):
            elements.append(Element("transition", text, page.number, 0.99))
            i += 1
            continue
        if _is_upper(text) and line.x0 > page.width * 0.60 and (text.endswith(":") or text in {"END", "THE END."}):
            elements.append(Element("transition", text, page.number, 0.92))
            i += 1
            continue
        if _SCENE_PREFIX.match(text):
            elements.append(Element("scene", text, page.number, 0.99))
            i += 1
            continue

        if text.startswith("(") and text.endswith(")") and page.width * 0.25 < line.x0 < page.width * 0.48:
            elements.append(Element("parenthetical", text, page.number, 0.98))
            i += 1
            continue
        if _character_line(line, page.width):
            elements.append(Element("character", text, page.number, 0.97))
            i += 1
            continue

        previous_kind = elements[-1].kind if elements else None
        if previous_kind in {"character", "dialogue", "parenthetical"} and page.width * 0.20 <= line.x0 < page.width * 0.50:
            parts = [text]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt.y0 - lines[i - 1].y1 > 5.0 or not (page.width * 0.20 <= nxt.x0 < page.width * 0.50):
                    break
                if _character_line(nxt, page.width) or (nxt.text.startswith("(") and nxt.text.endswith(")")):
                    break
                parts.append(nxt.text)
                i += 1
            elements.append(Element("dialogue", _join_wrapped(parts), page.number, 0.97))
            continue

        if len(lines) <= 3 and line.x0 > page.width * 0.30:
            elements.append(Element("centered", text, page.number, 0.88))
            i += 1
            continue

        # All-caps headings with scene numbers removed from their margins are nonstandard sluglines.
        has_margin_number = any(
            abs(other.y0 - line.y0) < 2 and _SCENE_NUMBER.fullmatch(other.text)
            and (other.x0 < page.width * 0.14 or other.x0 > page.width * 0.82)
            for other in page.lines
        )
        if line.x0 < page.width * 0.24 and _is_upper(text) and has_margin_number:
            elements.append(Element("scene", text, page.number, 0.96))
            i += 1
            continue

        parts = [text]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            vertical_gap = nxt.y0 - lines[i - 1].y1
            if vertical_gap > 5.5 or abs(nxt.x0 - line.x0) > 10:
                break
            if _SCENE_PREFIX.match(nxt.text) or _TRANSITION.fullmatch(nxt.text) or _character_line(nxt, page.width):
                break
            parts.append(nxt.text)
            i += 1
        confidence = 0.94 if line.x0 < page.width * 0.24 else 0.72
        elements.append(Element("action", _join_wrapped(parts), page.number, confidence))
        if confidence < 0.8 and gap_before > 10:
            warnings.append(ConversionWarning(
                "ambiguous-indentation", f"Treated unusually indented text as action: {text[:60]}", page.number
            ))
    return elements, warnings
