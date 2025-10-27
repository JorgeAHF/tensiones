"""Utility helpers for configuring application-wide logging."""
from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional


def configure_logging(log_dir: Optional[Path] = None, level: int = logging.INFO) -> None:
    """Configure root logging with console and optional rotating file handler.

    Parameters
    ----------
    log_dir:
        Optional directory where log files should be written. When provided the
        directory is created if necessary and a rotating file handler is added.
    level:
        Logging level for the root logger.
    """

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(threadName)s | %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers so repeated invocations do not duplicate logs.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_path = log_dir / "mscl_tension.log"
        file_handler = logging.handlers.RotatingFileHandler(
            file_path, maxBytes=5 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    logging.debug(
        "Logging configured. level=%s, log_dir=%s", logging.getLevelName(level), log_dir
    )


__all__ = ["configure_logging"]
