# fountain

`fountain` converts screenplay PDFs into editable [Fountain](https://fountain.io/) markup.

## Install

Python 3.10 or newer is required.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

For scanned scripts, install Tesseract and the language data you need. Text-based PDFs need no system PDF utilities.

## Use

```bash
fountain screenplay.pdf
fountain screenplay.pdf -o screenplay.fountain --report screenplay.report.json
fountain screenplay.pdf --strict --min-confidence 0.90
```

The default output is `screenplay.fountain` beside the input. Existing files are never replaced unless `--force` is supplied.

Useful options:

```text
--ocr auto|never|always       OCR behavior (default: auto)
--ocr-language LANG           Tesseract language, such as eng or eng+fra
--no-page-breaks              omit Fountain === page separators
--keep-revision-marks         retain margin revision symbols
--report PATH                 write machine-readable quality diagnostics
--strict                      write no Fountain file below the quality threshold
-q, --quiet                   suppress progress and summary
```


## Python API

```python
from fountain import ConversionOptions, convert_pdf

result = convert_pdf("screenplay.pdf", ConversionOptions(ocr="auto"))
print(result.fountain)
print(result.stats.confidence)
```

## Development

```bash
python -m pip install -e .
pytest
```

