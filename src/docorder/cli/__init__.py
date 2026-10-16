"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version
from pathlib import Path

from docorder.cli.status import format_status, inspect_output


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="docorder",
        description="Inspect a job output directory.",
    )
    parser.add_argument("--version", action="version", version=f"docorder {version('docorder')}")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser(
        "status",
        help="Show epochs, whether each is consistent, and how many entities each stage has",
    )
    status.add_argument("output", type=Path, help="Job output directory")
    args = parser.parse_args(argv)
    if args.command == "status":
        _status(args.output)


def _status(output: Path) -> None:
    try:
        report = inspect_output(output)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
    sys.stdout.write(format_status(report))


if __name__ == "__main__":
    main()
