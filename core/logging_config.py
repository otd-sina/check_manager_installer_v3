from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from pathlib import Path


DEFAULT_LOG_FILE = 'application.log'
_FORMAT = '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
_DATEFMT = '%Y-%m-%d %H:%M:%S'


_is_configured = False


def setup_logging(log_dir: Path, level: int | str = logging.INFO) -> logging.Logger:
    global _is_configured

    root_logger = logging.getLogger()
    if _is_configured:
        return root_logger

    resolved_level = _resolve_level(level)

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / DEFAULT_LOG_FILE

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=12,
        encoding='utf-8',
    )
    file_handler.setLevel(resolved_level)
    file_handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(resolved_level)
    console_handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))

    root_logger.setLevel(resolved_level)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    _install_exception_hooks(root_logger)
    _is_configured = True
    root_logger.info(
        'Logging initialized | level=%s | file=%s',
        logging.getLevelName(resolved_level),
        log_path,
    )
    return root_logger


def _resolve_level(level: int | str) -> int:
    if isinstance(level, int):
        return level

    text = str(level or '').strip().upper()
    if not text:
        return logging.INFO
    resolved = logging.getLevelName(text)
    if isinstance(resolved, int):
        return resolved
    return logging.INFO


def _install_exception_hooks(logger: logging.Logger):
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical(
            'Unhandled exception | type=%s | message=%s',
            exc_type.__name__,
            exc_value,
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def handle_thread_exception(args: threading.ExceptHookArgs):
        logger.critical(
            'Unhandled thread exception | thread=%s | type=%s | message=%s',
            getattr(args.thread, 'name', 'unknown'),
            args.exc_type.__name__ if args.exc_type else 'UnknownError',
            args.exc_value,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception
