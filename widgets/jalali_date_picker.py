"""Jalali calendar and date picker widgets.

This module provides a fully Jalali (Persian) calendar grid using ``jdatetime``.
"""

from __future__ import annotations

from datetime import date as gregorian_date

import jdatetime
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from utils.date_utils import (
    JALALI_DATE_FORMAT,
    gregorian_to_jalali,
    jalali_to_gregorian,
    normalize_jalali_date_text,
    today_jalali,
)
from utils.holiday_service import get_iran_holidays_for_year


_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _to_persian_digits(value: str) -> str:
    return value.translate(_PERSIAN_DIGITS)


class JalaliCalendarWidget(QWidget):
    """A Jalali calendar widget with Saturday-first weeks and holiday highlighting."""

    selectionChanged = Signal()
    currentPageChanged = Signal(int, int)

    MONTH_NAMES = [
        "فروردین",
        "اردیبهشت",
        "خرداد",
        "تیر",
        "مرداد",
        "شهریور",
        "مهر",
        "آبان",
        "آذر",
        "دی",
        "بهمن",
        "اسفند",
    ]

    WEEKDAY_NAMES = ["شنبه", "یکشنبه", "دوشنبه", "سه شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("JalaliCalendarRoot")
        self.setLayoutDirection(Qt.RightToLeft)

        self._today = today_jalali()
        self._selected_date = self._today
        self._view_year = self._selected_date.year
        self._view_month = self._selected_date.month

        self._setup_ui()
        self._render_calendar()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(8)

        self._next_button = QToolButton(self)
        self._next_button.setText("◀")
        self._next_button.setToolTip("ماه بعد")
        self._next_button.clicked.connect(lambda: self._change_month(1))

        self._previous_button = QToolButton(self)
        self._previous_button.setText("▶")
        self._previous_button.setToolTip("ماه قبل")
        self._previous_button.clicked.connect(lambda: self._change_month(-1))

        self._title_label = QLabel(self)
        self._title_label.setAlignment(Qt.AlignCenter)

        self._today_button = QPushButton("امروز", self)
        self._today_button.clicked.connect(self._go_to_today)

        nav_layout.addWidget(self._next_button)
        nav_layout.addWidget(self._previous_button)
        nav_layout.addWidget(self._title_label, 1)
        nav_layout.addWidget(self._today_button)
        root_layout.addLayout(nav_layout)

        self._table = QTableWidget(6, 7, self)
        self._table.setHorizontalHeaderLabels(self.WEEKDAY_NAMES)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.NoSelection)
        self._table.setFocusPolicy(Qt.NoFocus)
        self._table.setLayoutDirection(Qt.LeftToRight)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.cellClicked.connect(self._on_cell_clicked)

        for row in range(self._table.rowCount()):
            self._table.setRowHeight(row, 44)

        root_layout.addWidget(self._table)

        self.setStyleSheet(
            """
            QWidget#JalaliCalendarRoot {
                background: #F5F8FC;
                border: 1px solid #D5DEEB;
                border-radius: 12px;
            }
            QLabel {
                color: #1F2D3D;
                font-size: 15px;
                font-weight: 700;
            }
            QToolButton {
                background: #FFFFFF;
                border: 1px solid #CAD5E5;
                border-radius: 8px;
                color: #27406D;
                min-width: 28px;
                min-height: 28px;
                font-size: 16px;
                font-weight: 600;
            }
            QToolButton:hover {
                background: #EAF1FB;
            }
            QPushButton {
                background: #0C4DA2;
                border: 0;
                border-radius: 8px;
                color: white;
                font-weight: 600;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background: #0A3F86;
            }
            QTableWidget {
                background: #FFFFFF;
                border: 1px solid #D9E3F1;
                border-radius: 10px;
                gridline-color: #E7EEF8;
                font-size: 12px;
            }
            QHeaderView::section {
                background: #E9F0FA;
                color: #27406D;
                border: 0;
                border-right: 1px solid #DCE5F3;
                padding: 6px;
                font-weight: 700;
            }
            """
        )

    def selected_jalali_date(self) -> jdatetime.date:
        """Return the currently selected Jalali date."""

        return self._selected_date

    def set_selected_jalali_date(self, value: jdatetime.date) -> None:
        """Set selected date and move view to that Jalali month."""

        self._selected_date = value
        self._view_year = value.year
        self._view_month = value.month
        self._render_calendar()

    def setCurrentPage(self, year: int, month: int) -> None:
        """Compatibility helper: accepts Gregorian year/month like QCalendarWidget."""

        g_first_day = gregorian_date(year, month, 1)
        j_first_day = gregorian_to_jalali(g_first_day)
        self._view_year = j_first_day.year
        self._view_month = j_first_day.month
        self._render_calendar()
        self.currentPageChanged.emit(self._view_year, self._view_month)

    def _go_to_today(self) -> None:
        self._selected_date = self._today
        self._view_year = self._today.year
        self._view_month = self._today.month
        self._render_calendar()
        self.selectionChanged.emit()

    def _change_month(self, delta: int) -> None:
        month = self._view_month + delta
        year = self._view_year

        if month < 1:
            month = 12
            year -= 1
        elif month > 12:
            month = 1
            year += 1

        self._view_year = year
        self._view_month = month
        self._render_calendar()
        self.currentPageChanged.emit(self._view_year, self._view_month)

    def _on_cell_clicked(self, row: int, column: int) -> None:
        item = self._table.item(row, column)
        if item is None:
            return

        value = item.data(Qt.UserRole)
        if not isinstance(value, str):
            return

        year_text, month_text, day_text = value.split("/")
        self._selected_date = jdatetime.date(int(year_text), int(month_text), int(day_text))
        self._render_calendar()
        self.selectionChanged.emit()

    def _render_calendar(self) -> None:
        self._title_label.setText(
            f"{self.MONTH_NAMES[self._view_month - 1]} {_to_persian_digits(str(self._view_year))}"
        )

        self._table.clearContents()

        first_day = jdatetime.date(self._view_year, self._view_month, 1)
        start_col = self._weekday_column(first_day)
        days_count = self._days_in_month(self._view_year, self._view_month)
        holidays = get_iran_holidays_for_year(self._view_year)
        month_holidays = holidays.get(self._view_month, set())

        default_font = QFont()
        default_font.setPointSize(11)

        for day in range(1, days_count + 1):
            position = start_col + day - 1
            row, col = divmod(position, 7)
            jalali_day = jdatetime.date(self._view_year, self._view_month, day)

            item = QTableWidgetItem(_to_persian_digits(str(day)))
            item.setTextAlignment(Qt.AlignCenter)
            item.setFont(default_font)
            item.setData(Qt.UserRole, jalali_day.strftime(JALALI_DATE_FORMAT))

            foreground = QColor("#1F2D3D")
            background = QColor("#FFFFFF")

            if col == 6 or jalali_day.day in month_holidays:
                foreground = QColor("#C62828")
                holiday_font = QFont(default_font)
                holiday_font.setBold(True)
                item.setFont(holiday_font)

            if jalali_day == self._today:
                background = QColor("#E8F4EA")

            if jalali_day == self._selected_date:
                background = QColor("#0C4DA2")
                foreground = QColor("#FFFFFF")
                selected_font = QFont(item.font())
                selected_font.setBold(True)
                item.setFont(selected_font)

            item.setForeground(foreground)
            item.setBackground(background)
            self._table.setItem(row, col, item)

    @staticmethod
    def _days_in_month(year: int, month: int) -> int:
        if month <= 6:
            return 31
        if month <= 11:
            return 30
        return 30 if jdatetime.date(year, 1, 1).isleap() else 29

    @staticmethod
    def _weekday_column(value: jdatetime.date) -> int:
        gregorian_value = jalali_to_gregorian(value)
        # Python weekday: Monday=0 ... Sunday=6; we need Saturday=0 ... Friday=6.
        return (gregorian_value.weekday() + 2) % 7


class JalaliDatePicker(QWidget):
    """Compact Jalali date picker with a modal calendar dialog."""

    dateChanged = Signal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._jalali_date = today_jalali()

        self._setup_ui()
        self._sync_display()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.display = QLineEdit(self)
        self.display.setReadOnly(True)
        self.display.setAlignment(Qt.AlignCenter)
        self.display.setLayoutDirection(Qt.LeftToRight)

        self.button = QPushButton("انتخاب تاریخ", self)
        self.button.clicked.connect(self._open_picker_dialog)

        layout.addWidget(self.display, 1)
        layout.addWidget(self.button)

    def jalali_date(self) -> jdatetime.date:
        return self._jalali_date

    def jalali_text_date(self) -> str:
        return self._jalali_date.strftime(JALALI_DATE_FORMAT)

    def gregorian_iso_date(self) -> str:
        """Return selected date in Gregorian ISO format (YYYY-MM-DD)."""

        return self._jalali_date.togregorian().isoformat()

    def set_jalali_date(self, value: jdatetime.date) -> None:
        self._jalali_date = value
        self._sync_display()
        self.dateChanged.emit(self._jalali_date)

    def set_jalali_date_text(self, value: str) -> None:
        normalized = normalize_jalali_date_text(value)
        year, month, day = map(int, normalized.split("/"))
        self.set_jalali_date(jdatetime.date(year, month, day))

    def set_gregorian_date(self, value: str | gregorian_date) -> None:
        self.set_jalali_date(gregorian_to_jalali(value))

    def _sync_display(self) -> None:
        self.display.setText(self.jalali_text_date())

    def _open_picker_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("انتخاب تاریخ")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(560, 460)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("تقویم جلالی")
        title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(title)

        calendar = JalaliCalendarWidget(dialog)
        calendar.set_selected_jalali_date(self._jalali_date)
        layout.addWidget(calendar)

        preview = QLabel(self.jalali_text_date())
        preview.setAlignment(Qt.AlignCenter)
        preview.setStyleSheet("font-size: 14px; font-weight: 700; color: #0C4DA2;")
        layout.addWidget(preview)

        calendar.selectionChanged.connect(
            lambda: preview.setText(calendar.selected_jalali_date().strftime(JALALI_DATE_FORMAT))
        )

        hint = QLabel("جمعه ها و تعطیلات رسمی با رنگ قرمز مشخص شده اند")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #C62828; font-size: 11px;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec():
            self.set_jalali_date(calendar.selected_jalali_date())
