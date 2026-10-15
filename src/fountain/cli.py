from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn

from . import __version__
from .converter import ConversionOptions, convert_pdf


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fountain",
        description="Convert a screenplay PDF into editable Fountain markup.",
    )
    parser.add_argument("input", type=Path, help="source screenplay PDF")
    parser.add_argument("-o", "--output", type=Path, help="destination .fountain file (default: beside input)")
    parser.add_argument("--force", action="store_true", help="replace an existing output file")
    parser.add_argument("--report", type=Path, help="write a JSON conversion-quality report")
    parser.add_argument("--strict", action="store_true", help="fail if confidence is below --min-confidence")
    parser.add_argument("--min-confidence", type=float, default=0.88, metavar="N")
    parser.add_argument("--ocr", choices=("auto", "never", "always"), default="auto")
    parser.add_argument("--ocr-language", default="eng", metavar="LANG")
    parser.add_argument("--no-page-breaks", action="store_true", help="do not preserve PDF page boundaries")
    parser.add_argument("--keep-revision-marks", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress progress and summary")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _atomic_write(path: Path, content: str, *, force: bool) -> None:
    path = path.expanduser().resolve()
    if path.exists() and not force:
        raise FileExistsError(f"Output already exists (use --force): {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    console = Console(stderr=True)
    output = (args.output or args.input.with_suffix(".fountain")).expanduser().resolve()
    if not 0 <= args.min_confidence <= 1:
        console.print("[red]error:[/] --min-confidence must be between 0 and 1")
        return 2
    if output == args.input.expanduser().resolve():
        console.print("[red]error:[/] input and output paths must differ")
        return 2
    targets = [output]
    if args.report:
        report = args.report.expanduser().resolve()
        if report in {args.input.expanduser().resolve(), output}:
            console.print("[red]error:[/] report, input, and output paths must differ")
            return 2
        targets.append(report)
    existing = [path for path in targets if path.exists()]
    if existing and not args.force:
        console.print(f"[red]error:[/] output already exists (use --force): {existing[0]}")
        return 1

    progress = None
    task_ids: dict[str, int] = {}
    if not args.quiet:
        progress = Progress(
            SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
            TaskProgressColumn(), TimeElapsedColumn(), console=console,
        )
        progress.start()

    def update(stage: str, completed: int, total: int) -> None:
        if progress is None:
            return
        if stage not in task_ids:
            task_ids[stage] = progress.add_task(stage, total=max(total, 1))
        progress.update(task_ids[stage], completed=completed, total=max(total, 1))

    try:
        result = convert_pdf(args.input, ConversionOptions(
            ocr=args.ocr,
            ocr_language=args.ocr_language,
            page_breaks=not args.no_page_breaks,
            keep_revision_marks=args.keep_revision_marks,
        ), progress=update)
        if progress:
            progress.stop()
            progress = None
        if args.strict and result.stats.confidence < args.min_confidence:
            console.print(
                f"[red]quality gate failed:[/] confidence {result.stats.confidence:.1%} "
                f"is below {args.min_confidence:.1%}; no Fountain file was written"
            )
            if args.report:
                _atomic_write(args.report, json.dumps(result.report(), indent=2) + "\n", force=args.force)
            return 3
        _atomic_write(output, result.fountain, force=args.force)
        if args.report:
            _atomic_write(args.report, json.dumps(result.report(), indent=2) + "\n", force=args.force)
        if not args.quiet:
            stats = result.stats
            console.print(
                f"[green]Converted[/] {stats.pages} pages -> [bold]{output}[/]\n"
                f"{stats.scenes} scenes, {stats.dialogue_blocks} dialogue blocks, "
                f"{stats.words:,} words, confidence {stats.confidence:.1%}"
            )
            if result.warnings:
                console.print(f"[yellow]{len(result.warnings)} warning(s)[/] (use --report for details)")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        if progress:
            progress.stop()
        console.print(f"[red]error:[/] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

