"""python3 -m catalog <command> — argument parsing and dispatch only.

Each command module exposes register(subparsers), which adds its parser and
sets func=<callable(args) -> int>.
"""

import argparse
import sys

from catalog.errors import CatalogError

from catalog.apply import command as apply_command
from catalog.audit import command as audit_command
from catalog.libib import command as libib_command
from catalog.picker import command as picker_command

COMMANDS: list = [audit_command, picker_command, apply_command, libib_command]  # modules with register(subparsers), in help order


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m catalog",
        description="Little Movie Store catalog pipeline: audit → picker push → apply → libib.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    for module in COMMANDS:
        module.register(subparsers)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args) or 0
    except CatalogError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted. Work saved so far is kept; the run is not marked complete.", file=sys.stderr)
        return 130
