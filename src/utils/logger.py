"""Configurazione logger centralizzato per la pipeline."""

import logging
import sys
from pathlib import Path


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    Restituisce un logger con formattazione coerente su stdout.
    Su GitHub Actions, stdout viene catturato automaticamente nei log del workflow.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        # già configurato
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False

    return logger


def setup_file_logger(name: str, log_path: Path, level: str = "INFO") -> logging.Logger:
    """Logger duplicato anche su file (utile per debug locale)."""
    logger = get_logger(name, level)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    )
    logger.addHandler(fh)
    return logger
