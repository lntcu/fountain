from fountain.classify import _join_wrapped, classify_page
from fountain.model import Line, PageData


def line(y: float, x: float, text: str, x1: float | None = None) -> Line:
    return Line(1, x, y, x1 or x + len(text) * 7, y + 12, text)


def test_classifies_standard_screenplay_geometry():
    page = PageData(1, 612, 792, [
        line(72, 108, "INT. KITCHEN - DAY"),
        line(96, 108, "A kettle starts to sing."),
        line(120, 252, "MAYA"),
        line(132, 206, "(quietly)"),
        line(144, 180, "Not yet."),
        line(168, 464, "CUT TO:"),
    ])
    elements, warnings = classify_page(page)
    assert [element.kind for element in elements] == [
        "scene", "action", "character", "parenthetical", "dialogue", "transition"
    ]
    assert not warnings


def test_removes_headers_scene_numbers_and_revision_marks():
    page = PageData(4, 612, 792, [
        line(35, 240, "Blue Rev. (01/02/2024)"),
        line(35, 508, "3."),
        line(72, 54, "12A"),
        line(72, 108, "EXT. STREET - NIGHT"),
        line(72, 517, "12A"),
        line(72, 551, "*"),
        line(96, 108, "Rain falls."),
    ])
    elements, _ = classify_page(page)
    assert [element.text for element in elements] == ["EXT. STREET - NIGHT", "Rain falls."]


def test_dual_dialogue_is_ordered_and_marked():
    page = PageData(1, 612, 792, [
        line(100, 148, "LEFT"),
        line(100, 415, "RIGHT"),
        line(112, 108, "Hello."),
        line(112, 333, "Goodbye."),
        line(136, 108, "They stare at each other."),
    ])
    elements, _ = classify_page(page)
    assert [(e.kind, e.text, e.dual) for e in elements[:4]] == [
        ("character", "LEFT", False),
        ("dialogue", "Hello.", False),
        ("character", "RIGHT", True),
        ("dialogue", "Goodbye.", False),
    ]


def test_wrap_join_preserves_compound_hyphen_but_not_double_dash():
    assert _join_wrapped(["off-", "load the boat."]) == "off-load the boat."
    assert _join_wrapped(["Wait --", "Now."]) == "Wait -- Now."


def test_recombines_separate_continuation_suffix():
    page = PageData(1, 612, 792, [
        line(72, 252, "JESSICA"),
        line(72, 307, "(CONT'D)"),
        line(84, 180, "More dreams?"),
    ])
    elements, _ = classify_page(page)
    assert [(e.kind, e.text) for e in elements] == [
        ("character", "JESSICA (CONT'D)"),
        ("dialogue", "More dreams?"),
    ]


def test_translation_label_forms_right_side_of_dual_dialogue():
    page = PageData(1, 612, 792, [
        line(72, 187, "STILGAR"),
        line(72, 359, "(CHAKOBSA TRANSLATION)"),
        line(84, 108, "I recognize you."),
        line(84, 333, "Heshiigiishii."),
        line(108, 108, "Paul listens."),
    ])
    elements, _ = classify_page(page)
    assert [(e.kind, e.text, e.dual) for e in elements[:4]] == [
        ("character", "STILGAR", False),
        ("dialogue", "I recognize you.", False),
        ("character", "CHAKOBSA TRANSLATION", True),
        ("dialogue", "Heshiigiishii.", False),
    ]

