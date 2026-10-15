from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal


ElementKind = Literal[
    "scene", "action", "character", "dialogue", "parenthetical", "transition", "centered"
]


@dataclass(frozen=True)
class Line:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    size: float = 12.0


@dataclass
class Element:
    kind: ElementKind
    text: str
    page: int
    confidence: float = 1.0
    dual: bool = False


@dataclass
class PageData:
    number: int
    width: float
    height: float
    lines: list[Line]
    used_ocr: bool = False


@dataclass
class ConversionWarning:
    code: str
    message: str
    page: int | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ConversionStats:
    pages: int = 0
    ocr_pages: int = 0
    scenes: int = 0
    dialogue_blocks: int = 0
    action_blocks: int = 0
    transitions: int = 0
    words: int = 0
    confidence: float = 1.0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ConversionResult:
    input_path: Path
    fountain: str
    stats: ConversionStats
    warnings: list[ConversionWarning] = field(default_factory=list)

    def report(self) -> dict[str, object]:
        return {
            "input": str(self.input_path),
            "stats": self.stats.as_dict(),
            "warnings": [warning.as_dict() for warning in self.warnings],
        }

