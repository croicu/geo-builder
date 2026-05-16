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
    tasks_path: Path | None
    in_directory: Path | None
    out_directory: Path


def parse_args(argv: list[str]) -> CliArguments:
    parser = argparse.ArgumentParser(
        prog="geo-builder",
        usage="geo-builder [<tasks_path>] [--in <in_directory>] [--out <out_directory>]",
    )

    parser.add_argument(
        "tasks_path",
        type=Path,
        nargs="?",
        default=None,
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


def _launch_designer(url: str, debug: bool = False, break_on_load: bool = False, dev_tools: bool = False, log_level=None) -> None:
    from geo_builder.designer.host import launch
    launch(url, debug=debug, break_on_load=break_on_load, dev_tools=dev_tools, log_level=log_level)


def main() -> int:
    arguments = parse_args(sys.argv[1:])

    try:
        settings = Settings.load(arguments.tasks_path)
    except GeoError as error:
        print(f"geo-builder: error: {error}", file=sys.stderr)
        return 1

    if arguments.tasks_path is None:
        if not settings.design_url:
            print("geo-builder: error: no tasks file given and no designUrl configured in build.json", file=sys.stderr)
            return 1
        _launch_designer(settings.design_url, debug=settings.debug, break_on_load=settings.break_on_load, dev_tools=settings.dev_tools, log_level=settings.logging)
        return 0

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
