from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from .errors import GeoError
from .executor import Executor
from .protocols import Catalog
from .tasks import Tasks


@dataclass
class CliArguments:
    task_path: Path
    in_directory: Path | None
    out_directory: Path
    debug: bool


def parse_args(argv: list[str]) -> CliArguments:
    parser = argparse.ArgumentParser(
        prog="geo-builder",
        usage="geo-builder <task_path> [--in <in_directory>] [--out <out_directory>] [--debug]",
    )

    parser.add_argument(
        "task_path",
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

    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
    )

    args = parser.parse_args(argv)

    return CliArguments(
        task_path=args.task_path,
        in_directory=args.in_directory,
        out_directory=args.out_directory,
        debug=args.debug,
    )


def main() -> int:
    arguments = parse_args(sys.argv[1:])

    try:
        tasks = Tasks.load(arguments.task_path)

        if arguments.in_directory is not None:
            catalog = Catalog.load(arguments.in_directory)
            executor = Executor(catalog)
        else:
            executor = Executor()

        result = executor.execute(tasks, debug=arguments.debug)

        if executor.errors:
            for error in executor.errors:
                print(f"geo-builder: error: {error}", file=sys.stderr)
            return 1

        result.save(arguments.out_directory)
        return 0
    except GeoError as error:
        if arguments.debug:
            raise
        print(f"geo-builder: error: {error}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())