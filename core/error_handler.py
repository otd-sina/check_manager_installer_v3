from __future__ import annotations

import logging
import sqlite3
import threading
from typing import Any

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget
from qt_material import apply_stylesheet 

logger = logging.getLogger(__name__)
_dialog_guard = threading.Lock()
_dialog_is_open = False


def user_message_for_exception(exc: BaseException) -> str:
    message = str(exc).strip()

    if isinstance(exc, ValueError) and message:
        return message
    if isinstance(exc, FileNotFoundError):
        return 'فایل مورد نظر پیدا نشد. مسیر فایل را بررسی کنید.'
    if isinstance(exc, PermissionError):
        return 'دسترسی لازم به فایل/پوشه وجود ندارد یا فایل در برنامه دیگری باز است.'
    if isinstance(exc, sqlite3.DatabaseError):
        return 'خطا در پایگاه داده رخ داد. لطفا عملیات را دوباره انجام دهید.'
    if isinstance(exc, OSError):
        return 'خطا در عملیات فایل رخ داد. دسترسی و فضای دیسک را بررسی کنید.'
    if message:
        return message
    return 'یک خطای غیرمنتظره رخ داد. جزئیات در فایل لاگ ثبت شد.'


def log_exception(
    exc: BaseException,
    *,
    context: str,
    logger_: logging.Logger | None = None,
) -> None:
    active_logger = logger_ or logger
    active_logger.error(
        '%s | type=%s | message=%s',
        context,
        type(exc).__name__,
        exc,
        exc_info=(type(exc), exc, exc.__traceback__),
    )


def show_error_message(parent: QWidget | None, title: str, message: str) -> None:
    global _dialog_is_open

    with _dialog_guard:
        if _dialog_is_open:
            return
        _dialog_is_open = True

    try:
        resolved_parent = parent
        if resolved_parent is None:
            app = QApplication.instance()
            if app is not None:
                active = app.activeWindow()
                if isinstance(active, QWidget):
                    resolved_parent = active
        QMessageBox.warning(resolved_parent, title, message)
    finally:
        with _dialog_guard:
            _dialog_is_open = False


def report_exception(
    parent: QWidget | None,
    exc: BaseException | Any,
    *,
    title: str = 'خطا',
    context: str = 'Unhandled exception',
    logger_: logging.Logger | None = None,
) -> str:
    normalized_exc: BaseException
    if isinstance(exc, BaseException):
        normalized_exc = exc
    else:
        normalized_exc = RuntimeError(str(exc))

    log_exception(normalized_exc, context=context, logger_=logger_)
    user_message = user_message_for_exception(normalized_exc)
    show_error_message(parent, title, user_message)
    return user_message


class GuardedApplication(QApplication):
    """QApplication wrapper that keeps UI alive on unexpected exceptions."""

    def notify(self, receiver, event):  # noqa: ANN001
        try:
            return super().notify(receiver, event)
        except Exception as exc:  # pragma: no cover - guarded runtime behavior
            report_exception(
                self.activeWindow(),
                exc,
                title='خطای غیرمنتظره',
                context=f'Unhandled UI exception in {type(receiver).__name__}',
                logger_=logger,
            )
            return True
