# import logging
# import sys
# from logging.handlers import RotatingFileHandler
# from pathlib import Path


# def setup_logger():
#     """Setup application logger"""
#     # Create logs directory
#     log_dir = Path("logs")
#     log_dir.mkdir(exist_ok=True)

#     # Create logger
#     logger = logging.getLogger("runitup_bot")
#     logger.setLevel(logging.INFO)

#     # Console handler
#     console_handler = logging.StreamHandler(sys.stdout)
#     console_handler.setLevel(logging.INFO)
#     console_formatter = logging.Formatter(
#         "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
#         datefmt="%Y-%m-%d %H:%M:%S",
#     )
#     console_handler.setFormatter(console_formatter)

#     # File handler
#     file_handler = RotatingFileHandler(
#         log_dir / "bot.log", maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB
#     )
#     file_handler.setLevel(logging.INFO)
#     file_formatter = logging.Formatter(
#         "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
#         datefmt="%Y-%m-%d %H:%M:%S",
#     )
#     file_handler.setFormatter(file_formatter)

#     # Add handlers
#     logger.addHandler(console_handler)
#     logger.addHandler(file_handler)

#     return logger


# def get_logger(name: str):
#     """Get logger for module"""
#     return logging.getLogger(f"runitup_bot.{name}")

import logging
import sys
import io
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger():
    """Setup application logger with UTF-8 encoding support"""
    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Create logger
    logger = logging.getLogger("runitup_bot")
    logger.setLevel(logging.INFO)

    # Console handler with UTF-8 encoding for Windows compatibility
    # This wraps stdout to handle unicode characters properly
    if sys.platform == "win32":
        console_stream = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
    else:
        console_stream = sys.stdout

    console_handler = logging.StreamHandler(console_stream)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)

    # File handler with UTF-8 encoding
    file_handler = RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str):
    """Get logger for module"""
    return logging.getLogger(f"runitup_bot.{name}")
