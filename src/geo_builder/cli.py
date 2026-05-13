from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from .executor import Executor
from .protocols import Catalog
from .tasks import Tasks


@dataclass
class CliArguments:
    task_path: Path
    in_directory: Path | None
    out_directory: Path


def parse_args(argv: list[str]) -> CliArguments:
    parser = argparse.ArgumentParser(
        prog="geo-builder",
        usage="geo-builder <task_path> [--in <in_directory>] [--out <out_directory>]",
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

    args = parser.parse_args(argv)

    return CliArguments(
        task_path=args.task_path,
        in_directory=args.in_directory,
        out_directory=args.out_directory,
    )


def main() -> int:
    arguments = parse_args(sys.argv[1:])

    tasks = Tasks.load(arguments.task_path)

    if arguments.in_directory is not None:
        catalog = Catalog.load(arguments.in_directory)
        executor = Executor(catalog)
    else:
        executor = Executor()

    result = executor.execute(tasks)

    result.save(arguments.out_directory)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())