"""
backend/app/logging_config.py

Central structured logging setup. Previously the codebase used bare print()
statements for operational events (LLM call failures, KB parse errors,
appointment assignment issues) -- these are invisible to any real log
aggregation/monitoring tool, have no severity level, and can't be filtered
or searched. This gives every component a properly named, leveled logger
instead, configured once at startup.

Usage in any module:
    import logging
    logger = logging.getLogger("clarimed.<component>")
    logger.warning("something recoverable happened: %s", detail)
    logger.error("something worse happened", exc_info=True)
"""

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """Call once at application startup. Safe to call more than once --
    clears existing handlers first so it doesn't duplicate log lines if
    triggered twice (e.g. by a test harness re-importing main)."""
    root = logging.getLogger("clarimed")
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(handler)
    root.propagate = False