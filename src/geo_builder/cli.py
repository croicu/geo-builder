from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from .builder import Builder
from .errors import GeoError
from .persistence import load_catalog, save_catalog
from .settings import Settings


@dataclass
class CliArguments:
    tasks_path: Path
    in_directory: Path | None
    out_directory: Path


def parse_args(argv: list[str]) -> CliArguments:
    parser = argparse.ArgumentParser(
        prog="geo-builder",
        usage="geo-builder <tasks_path> [--in <in_directory>] [--out <out_directory>]",
    )

    parser.add_argument(
        "tasks_path",
        type=Path,
    )

    parser.add_argument(
        "--in",
        dest="in_directory",
        type=Path,
        default=None,
    )

    parser.add_argument(
        "--out",
        dest="out_directory",
        type=Path,
        default=Path("./"),
    )

    args = parser.parse_args(argv)

    return CliArguments(
        tasks_path=args.tasks_path,
        in_directory=args.in_directory,
        out_directory=args.out_directory,
    )


def main() -> int:
    arguments = parse_args(sys.argv[1:])

    try:
        settings = Settings.load(arguments.tasks_path)
    except GeoError as error:
        print(f"geo-builder: error: {error}", file=sys.stderr)
        return 1

    try:
        if arguments.in_directory is not None:
            catalog = load_catalog(arguments.in_directory)
            executor = Builder(catalog)
        else:
            executor = Builder()

        result = executor.run()

        if executor.errors:
            for error in executor.errors:
                print(f"geo-builder: error: {error}", file=sys.stderr)
            return 1

        save_catalog(result.catalog, arguments.out_directory)
        return 0
    except GeoError as error:
        if settings.debug:
            raise
        print(f"geo-builder: error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
