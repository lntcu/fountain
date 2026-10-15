from __future__ import annotations

import re

from .model import PageData

_CREDIT = re.compile(r"^(?:written|screenplay|story|teleplay|adaptation)\s+by$|^by$", re.IGNORECASE)
_SOURCE = re.compile(r"^(?:based on|adapted from|inspired by)", re.IGNORECASE)
_DRAFT = re.compile(r"(?:draft|revision|revisions|shooting script|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b)", re.IGNORECASE)


def _despace_title(text: str) -> str:
    # Spaced display lettering cannot be de-spaced reliably after PDF text
    # extraction (the larger gaps between words may be lost), so preserve it.
    return text


def extract_title_page(page: PageData, metadata: dict[str, str]) -> tuple[str, bool]:
    lines = [line for line in page.lines if 60 < line.y0 < page.height - 45 and line.text.strip()]
    if not lines:
        return "", False
    # A title page is sparse, centered, and contains no conventional scene heading.
    mean_center_offset = sum(abs((line.x0 + line.x1) / 2 - page.width / 2) for line in lines) / len(lines)
    if (
        len(lines) > 35
        or mean_center_offset > page.width * 0.10
        or any(re.match(r"^(?:INT\.?|EXT\.?)\s", line.text, re.I) for line in lines)
    ):
        return "", False

    groups: list[tuple[float, str, float]] = []
    for line in lines:
        groups.append((line.y0, line.text.strip(), line.size))
    groups.sort()
    largest = max(size for _, _, size in groups)
    title_candidates = [item for item in groups if item[2] >= largest - 0.5]
    title = _despace_title(title_candidates[0][1] if title_candidates else groups[0][1])
    title_y = title_candidates[0][0] if title_candidates else groups[0][0]

    credit_parts: list[str] = []
    authors: list[str] = []
    sources: list[str] = []
    drafts: list[str] = []
    notes: list[str] = []
    expecting_author = False
    for y, text, _ in groups:
        if y == title_y and text == title_candidates[0][1]:
            continue
        if _CREDIT.fullmatch(text):
            credit_parts.append(text)
            expecting_author = True
        elif _SOURCE.match(text):
            sources.append(text)
            expecting_author = False
        elif _DRAFT.search(text):
            drafts.append(text)
            expecting_author = False
        elif text.lower() in {"and", "&"} and expecting_author:
            continue
        elif expecting_author and not text.endswith(":"):
            authors.append(re.sub(r"^(?:and|&)\s+", "", text, flags=re.IGNORECASE))
        elif text != title:
            notes.append(text)

    if not title and metadata.get("title"):
        title = metadata["title"]
    fields: list[tuple[str, list[str]]] = [("Title", [title])]
    if credit_parts:
        fields.append(("Credit", [" & ".join(dict.fromkeys(credit_parts))]))
    if authors:
        fields.append(("Author", list(dict.fromkeys(authors))))
    if sources:
        fields.append(("Source", sources))
    if drafts:
        fields.append(("Draft date", drafts))
    if notes:
        fields.append(("Notes", notes))

    output: list[str] = []
    for key, values in fields:
        output.append(f"{key}: {values[0]}")
        output.extend(f"    {value}" for value in values[1:])
    return "\n".join(output), True

