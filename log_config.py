import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger that writes to stdout with timestamps.
    All loggers share the same format so Docker logs are consistent.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        fmt = logging.Formatter(
            fmt="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        # Prevent log records from propagating to the root logger
        # (avoids duplicate lines if something else configures root)
        logger.propagate = False

    return logger
