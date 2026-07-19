"""Structured logging for FactVerse — console + rotating file in logs/."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from factverse import config as fv

_CONFIGURED = False


def get_logger(name: str = "factverse") -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger(name)
    if not _CONFIGURED:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        fileh = RotatingFileHandler(
            fv.LOGS / "factverse.log",
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        fileh.setFormatter(fmt)
        logger.addHandler(console)
        logger.addHandler(fileh)
        _CONFIGURED = True
    return logger
