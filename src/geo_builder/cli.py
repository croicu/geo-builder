from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from .builder import Builder
from .diagnostics import ConsoleLogSink, Logger
from .entities import GeoCatalog
from .errors import GeoError
from .persistence import load_catalog, save_catalog
from .settings import Settings


@dataclass
class CliArguments:
    tasks_path: Path
    in_directory: Path
    out_directory: Path
    edit: bool = False


def parse_args(argv: list[str]) -> CliArguments:
    parser = argparse.ArgumentParser(
        prog="geo-builder",
        usage="geo-builder <tasks_path> [--in <dir>] [--out <dir>] [--edit]",
        description=("Build static geographic datasets, or open the designer UI with --edit."),
    )

    parser.add_argument(
        "tasks_path",
        type=Path,
        help="tasks JSON file",
    )

    parser.add_argument(
        "--in",
        dest="in_directory",
        type=Path,
        default=Path("./in"),
        metavar="dir",
        help="working directory for service artifacts (default: ./in); auto-created if absent; pulled from the service on first designer launch",
    )

    parser.add_argument(
        "--out",
        dest="out_directory",
        type=Path,
        default=Path("./out"),
        metavar="dir",
        help="output directory for built artifacts (default: ./out)",
    )

    parser.add_argument(
        "--edit",
        action="store_true",
        default=False,
        help="open the designer WebView (requires designUrl in settings.json)",
    )

    args = parser.parse_args(argv)

    return CliArguments(
        tasks_path=args.tasks_path,
        in_directory=args.in_directory,
        out_directory=args.out_directory,
        edit=args.edit,
    )


def _launch_designer(
    url: str,
    catalog=None,
    out_dir=None,
    in_dir=None,
    debug: bool = False,
    break_on_load: bool = False,
    dev_tools: bool = False,
    log_level=None,
) -> None:
    from geo_builder.designer.host import launch

    launch(
        url,
        catalog=catalog,
        out_dir=out_dir,
        in_dir=in_dir,
        debug=debug,
        break_on_load=break_on_load,
        dev_tools=dev_tools,
        log_level=log_level,
    )


def main() -> int:
    arguments = parse_args(sys.argv[1:])

    try:
        settings = Settings.load(arguments.tasks_path)
    except GeoError as error:
        print(f"geo-builder: error: {error}", file=sys.stderr)
        return 1

    if arguments.edit:
        if not settings.design_url:
            print("geo-builder: error: no designUrl configured in settings.json", file=sys.stderr)
            return 1
        try:
            catalog = load_catalog(arguments.in_directory, debug=settings.debug)
        except GeoError:
            catalog = GeoCatalog(is_default=True)
        _launch_designer(
            settings.design_url,
            catalog=catalog,
            out_dir=arguments.out_directory,
            in_dir=arguments.in_directory,
            debug=settings.debug,
            break_on_load=settings.break_on_load,
            dev_tools=settings.dev_tools,
            log_level=settings.logging,
        )
        return 0

    Logger.set_logger(ConsoleLogSink(min_level=settings.logging))
    try:
        try:
            catalog = load_catalog(arguments.in_directory, debug=settings.debug)
            executor = Builder(catalog)
        except GeoError:
            executor = Builder()

        geo_catalog = executor.run()

        if executor.errors:
            for error in executor.errors:
                print(f"geo-builder: error: {error}", file=sys.stderr)
            return 1

        save_catalog(geo_catalog, arguments.out_directory, debug=settings.debug, in_dir=arguments.in_directory)
        return 0
    except GeoError as error:
        if settings.debug:
            raise
        print(f"geo-builder: error: {error}", file=sys.stderr)
        return 1
    finally:
        Logger.set_logger(None)


if __name__ == "__main__":
    raise SystemExit(main())
