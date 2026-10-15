from pathlib import Path

import pymupdf

from fountain import ConversionOptions, convert_pdf


def test_end_to_end_pdf_conversion(tmp_path: Path):
    source = tmp_path / "sample.pdf"
    document = pymupdf.open()
    title = document.new_page(width=612, height=792)
    title.insert_text((270, 280), "TEST FILM", fontsize=16)
    title.insert_text((275, 330), "Written by", fontsize=12)
    title.insert_text((270, 360), "Alex Writer", fontsize=12)
    body = document.new_page(width=612, height=792)
    body.insert_text((108, 84), "INT. LAB - NIGHT", fontsize=12)
    body.insert_text((108, 108), "The machine hums.", fontsize=12)
    body.insert_text((252, 132), "ALEX", fontsize=12)
    body.insert_text((180, 144), "It works.", fontsize=12)
    document.save(source)
    document.close()

    result = convert_pdf(source, ConversionOptions(ocr="never"))
    assert "Title: TEST FILM" in result.fountain
    assert "INT. LAB - NIGHT" in result.fountain
    assert "ALEX\nIt works." in result.fountain
    assert result.stats.scenes == 1
    assert result.stats.dialogue_blocks == 1
