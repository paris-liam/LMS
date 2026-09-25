"""One logger for every stage: console plus runs/<id>/<stage>.log.

Levels: SUMMARY (25) = stage headers and closing counts, always shown;
INFO = per-item progress, hidden by --quiet; DEBUG = per-rule detail,
shown only with --verbose. The log file always records everything.
"""

import logging
import sys
from pathlib import Path

LOGGER_NAME = "catalog"
SUMMARY = 25
logging.addLevelName(SUMMARY, "SUMMARY")

_CONSOLE_LEVELS = {-1: SUMMARY, 0: logging.INFO, 1: logging.DEBUG}


def setup_logging(log_path=None, verbosity: int = 0, stream=None) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    console = logging.StreamHandler(stream if stream is not None else sys.stdout)
    console.setLevel(_CONSOLE_LEVELS.get(verbosity, logging.DEBUG))
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)

    if log_path is not None:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(file_handler)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def header(message: str) -> None:
    get_logger().log(SUMMARY, f"== {message} ==")


def summary(message: str) -> None:
    get_logger().log(SUMMARY, message)


def progress(index, total, label: str, message: str) -> None:
    get_logger().info(f"[{index}/{total}] {label}: {message}")


def detail(message: str) -> None:
    get_logger().debug(message)


def add_verbosity_args(parser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-v", "--verbose", action="store_true", help="show per-rule detail")
    group.add_argument("-q", "--quiet", action="store_true", help="show headers and summary only")


def verbosity(args) -> int:
    if getattr(args, "quiet", False):
        return -1
    if getattr(args, "verbose", False):
        return 1
    return 0
