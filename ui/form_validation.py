from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtWidgets import QWidget


def _refresh_widget(widget: QWidget) -> None:
    try:
        # Call the base QWidget implementation to avoid subclass overload issues
        # such as QListWidget.update(QModelIndex).
        QWidget.update(widget)
    except TypeError:
        widget.repaint()


def set_invalid(widget: QWidget, invalid: bool) -> None:
    widget.setProperty('invalid', invalid)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    _refresh_widget(widget)


def reset_invalid(widgets: Iterable[QWidget]) -> None:
    for widget in widgets:
        set_invalid(widget, False)
