from __future__ import annotations

from datetime import date

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QRect, Qt, QSortFilterProxyModel, Signal
from PySide6.QtGui import QAction, QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from models.check_model import Check
from ui.add_check_dialog import AddCheckDialog
from utils.date_utils import jalali_to_gregorian, normalize_jalali_date_text


class StatusBadgeDelegate(QStyledItemDelegate):
    STATUS_COLORS = {
    'PENDING': ('#f59e0b', '#fff7ed'),      # در انتظار وصول - نارنجی
    'DEPOSITED': ('#3b82f6', '#eff6ff'),    # واگذار شده به بانک - آبی
    'PAID': ('#059669', '#ecfdf5'),         # وصول شده - سبز
    'CLEARED': ('#16a34a', '#f0fdf4'),      # تسویه شده - سبز پررنگ
    'BOUNCED': ('#dc2626', '#fef2f2'),      # برگشت خورده - قرمز
    'RETURNED': ('#ef4444', '#fff1f2'),     # عودت داده شده - قرمز روشن
    'ENDORSED': ('#8b5cf6', '#f5f3ff'),     # پشت‌نویسی شده - بنفش
    'CANCELED': ('#64748b', '#f8fafc'),     # لغو شده - خاکستری
}


    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        status_key = (index.data(Qt.UserRole + 1) or '').upper()
        label = index.data(Qt.DisplayRole) or '-'

        painter.save()
        option.widget.style().drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, option.widget)

        fg_hex, bg_hex = self.STATUS_COLORS.get(status_key, ('#475569', '#f8fafc'))
        badge_rect = QRect(option.rect.adjusted(10, 8, -10, -8))
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(bg_hex))
        painter.drawRoundedRect(badge_rect, 12, 12)

        painter.setPen(QColor(fg_hex))
        painter.drawText(badge_rect, Qt.AlignCenter, label)
        painter.restore()


class ChecksTableModel(QAbstractTableModel):
    HEADERS = [
        'ID',
        'شماره صیادی چک 16 رقم',
        'شماره سریال چک',
        'نام ثبتنام کننده',
        'بانک',
        'صاحب حساب',
        'مبلغ',
        'دریافت کننده',
        'تاریخ سررسید',
        'وضعیت',
        'توضیحات',
    ]

    STATUS_LABELS = {
        'PENDING': 'در انتظار وصول',
        'DEPOSITED': 'واگذار شده به بانک',
        'PAID': 'وصول شده',
        'CLEARED': 'تسویه شده',
        'BOUNCED': 'برگشت خورده',
        'RETURNED': 'عودت داده شده',
        'ENDORSED': 'پشت‌نویسی شده',
        'CANCELED': 'لغو شده',
    }

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._checks: list[Check] = []

    def set_checks(self, checks: list[Check]):
        self.beginResetModel()
        self._checks = checks
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._checks)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return str(section + 1)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        check = self._checks[index.row()]
        column = index.column()

        if role == Qt.DisplayRole:
            return self._display_value(check, column)

        if role == Qt.TextAlignmentRole:
            if column in {0, 1, 2, 6, 8, 9}:
                return int(Qt.AlignCenter)
            return int(Qt.AlignVCenter | Qt.AlignLeft)

        if role == Qt.BackgroundRole:
            return self._background_color(check, column)

        if role == Qt.ForegroundRole:
            return self._foreground_color(check, column)

        if role == Qt.UserRole:
            return check

        if role == Qt.UserRole + 1:
            return check.status

        return None

    def check_at(self, row: int) -> Check | None:
        if 0 <= row < len(self._checks):
            return self._checks[row]
        return None

    def _display_value(self, check: Check, column: int):
        values = [
            str(check.id or ''),
            check.serial_18,
            check.serial_7,
            check.registrant_name,
            check.bank_name,
            check.account_owner,
            f'{int(check.amount or 0):,}',
            check.payee_name,
            check.due_date,
            self.STATUS_LABELS.get((check.status or '').upper(), check.status or '-'),
            check.notes or '',
        ]
        return values[column]

    def _background_color(self, check: Check, column: int):
        if column == 9:
            return None

        status = (check.status or '').upper()
        due_date = self._parse_date(check.due_date)
        today = date.today()

        if status == 'BOUNCED':
            return QColor('#e5e7eb')
        if due_date and status == 'PENDING' and due_date < today:
            return QColor('#fee2e2')
        if due_date and status == 'PENDING' and due_date == today:
            return QColor('#fef3c7')
        return None

    def _foreground_color(self, check: Check, column: int):
        if column == 9:
            return None

        status = (check.status or '').upper()
        due_date = self._parse_date(check.due_date)
        today = date.today()

        if status == 'BOUNCED':
            return QColor('#4b5563')
        if due_date and status == 'PENDING' and due_date < today:
            return QColor('#991b1b')
        if due_date and status == 'PENDING' and due_date == today:
            return QColor('#92400e')
        return None

    @staticmethod
    def _parse_date(value: str):
        if not value:
            return None
        try:
            normalized = normalize_jalali_date_text(value)
            return jalali_to_gregorian(normalized)
        except ValueError:
            return None


class ChecksFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.search_text = ''
        self.status_filter = ''
        self.quick_filter = 'all'
        self.setDynamicSortFilter(True)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def set_search_text(self, text: str):
        self.search_text = text.strip().lower()
        self.invalidateFilter()

    def set_status_filter(self, status: str):
        self.status_filter = status.strip().upper()
        self.invalidateFilter()

    def set_quick_filter(self, quick_filter: str):
        self.quick_filter = quick_filter
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex):
        model = self.sourceModel()
        if model is None:
            return False

        check = model.check_at(source_row)
        if check is None:
            return False

        if self.status_filter and (check.status or '').upper() != self.status_filter:
            return False

        if not self._matches_quick_filter(check):
            return False

        if not self.search_text:
            return True

        haystack = ' '.join(
            [
                str(check.id or ''),
                check.serial_18,
                check.serial_7,
                check.registrant_name,
                check.bank_name,
                check.account_owner,
                check.payee_name,
                check.due_date,
                check.notes or '',
                str(check.amount or ''),
                model.STATUS_LABELS.get((check.status or '').upper(), check.status or ''),
                check.status or '',
            ]
        ).lower()
        return self.search_text in haystack

    def lessThan(self, left: QModelIndex, right: QModelIndex):
        model = self.sourceModel()
        if model is None:
            return super().lessThan(left, right)

        left_check = model.check_at(left.row())
        right_check = model.check_at(right.row())
        if left_check is None or right_check is None:
            return super().lessThan(left, right)

        if left.column() == 0:
            return int(left_check.id or 0) < int(right_check.id or 0)
        if left.column() == 6:
            return int(left_check.amount or 0) < int(right_check.amount or 0)
        if left.column() == 8:
            return (left_check.due_date or '') < (right_check.due_date or '')
        return super().lessThan(left, right)

    def _matches_quick_filter(self, check: Check) -> bool:
        if self.quick_filter == 'all':
            return True

        due_date = ChecksTableModel._parse_date(check.due_date)
        today = date.today()
        status = (check.status or '').upper()

        if self.quick_filter == 'today':
            return due_date == today and status == 'PENDING'
        if self.quick_filter == 'overdue':
            return due_date is not None and due_date < today and status == 'PENDING'
        if self.quick_filter == 'returned':
            return status == 'BOUNCED'
        return True


class ChecksTableWidget(QWidget):
    checksChanged = Signal()

    def __init__(self, check_service, parent=None):
        super().__init__(parent)
        self.check_service = check_service
        self.model = ChecksTableModel(self)
        self.proxy_model = ChecksFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        filters_layout = QHBoxLayout()
        filters_layout.setSpacing(12)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('جستجو بر اساس سریال، نام ثبتنام کننده، بانک، دریافت کننده، مبلغ یا توضیحات')
        filters_layout.addWidget(self.search_input, 1)

        self.status_filter = QComboBox()
        self.status_filter.addItem('همه وضعیت ها', '')
        self.status_filter.addItem('در انتظار', 'PENDING')
        self.status_filter.addItem('پرداخت شده', 'PAID')
        self.status_filter.addItem('برگشتی', 'BOUNCED')
        self.status_filter.addItem('لغو شده', 'CANCELED')
        filters_layout.addWidget(self.status_filter)

        layout.addLayout(filters_layout)

        quick_filters_layout = QHBoxLayout()
        quick_filters_layout.setSpacing(8)

        self.quick_filter_buttons = {}
        for key, label in [
            ('all', 'همه'),
            ('today', 'امروز'),
            ('overdue', 'معوق'),
            ('returned', 'برگشتی'),
        ]:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName('filterChipButton')
            button.clicked.connect(lambda checked, value=key: self._set_quick_filter(value))
            quick_filters_layout.addWidget(button)
            self.quick_filter_buttons[key] = button
        quick_filters_layout.addStretch()
        layout.addLayout(quick_filters_layout)

        self.table_view = QTableView()
        self.table_view.setObjectName('checksTableView')
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSortingEnabled(True)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setSelectionMode(QTableView.SingleSelection)
        self.table_view.setEditTriggers(QTableView.NoEditTriggers)
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.setVerticalScrollMode(QTableView.ScrollPerPixel)
        self.table_view.setHorizontalScrollMode(QTableView.ScrollPerPixel)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table_view.horizontalHeader().setSectionResizeMode(10, QHeaderView.Stretch)
        self.table_view.setColumnHidden(0, True)
        self.table_view.setItemDelegateForColumn(9, StatusBadgeDelegate(self.table_view))
        layout.addWidget(self.table_view)

        self.search_input.textChanged.connect(self.proxy_model.set_search_text)
        self.status_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.table_view.customContextMenuRequested.connect(self._open_context_menu)
        self.table_view.doubleClicked.connect(lambda _: self.edit_selected())

        self._set_quick_filter('all')
        self.proxy_model.sort(8, Qt.AscendingOrder)

    def refresh(self):
        self.table_view.setUpdatesEnabled(False)
        try:
            self.model.set_checks(self.check_service.list_checks())
            self.table_view.sortByColumn(8, Qt.AscendingOrder)
        finally:
            self.table_view.setUpdatesEnabled(True)

    def focus_check(self, check_id: int) -> bool:
        self.search_input.clear()
        self.status_filter.setCurrentIndex(0)
        self._set_quick_filter('all')

        for source_row in range(self.model.rowCount()):
            check = self.model.check_at(source_row)
            if check is None or int(check.id or 0) != int(check_id):
                continue

            source_index = self.model.index(source_row, 0)
            proxy_index = self.proxy_model.mapFromSource(source_index)
            if not proxy_index.isValid():
                return False

            self.table_view.setCurrentIndex(proxy_index)
            self.table_view.selectRow(proxy_index.row())
            self.table_view.scrollTo(proxy_index, QTableView.PositionAtCenter)
            self.table_view.setFocus(Qt.ShortcutFocusReason)
            return True

        return False

    def current_check(self) -> Check | None:
        index = self.table_view.currentIndex()
        if not index.isValid():
            return None
        source_index = self.proxy_model.mapToSource(index)
        return self.model.check_at(source_index.row())

    def edit_selected(self):
        check = self.current_check()
        if check is None:
            QMessageBox.warning(self, 'خطا', 'لطفاً یک چک را انتخاب کنید.')
            return

        dialog = AddCheckDialog(self, check)
        if dialog.exec():
            updated_check = dialog.get_check()
            updated_check.id = check.id
            self.check_service.update_check(updated_check)
            self.refresh()
            self.checksChanged.emit()

    def delete_selected(self):
        check = self.current_check()
        if check is None:
            QMessageBox.warning(self, 'خطا', 'لطفاً یک چک را انتخاب کنید.')
            return

        reply = QMessageBox.question(
            self,
            'حذف چک',
            'آیا از حذف این چک مطمئن هستید؟',
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.check_service.delete_check(check.id)
            self.refresh()
            self.checksChanged.emit()

    def mark_selected_returned(self):
        check = self.current_check()
        if check is None:
            QMessageBox.warning(self, 'خطا', 'لطفاً یک چک را انتخاب کنید.')
            return

        check.status = 'BOUNCED'
        self.check_service.update_check(check)
        self.refresh()
        self.checksChanged.emit()

    def _on_filter_changed(self):
        self.proxy_model.set_status_filter(self.status_filter.currentData() or '')

    def _set_quick_filter(self, value: str):
        self.proxy_model.set_quick_filter(value)
        for key, button in self.quick_filter_buttons.items():
            button.setChecked(key == value)

    def _open_context_menu(self, pos):
        index = self.table_view.indexAt(pos)
        if index.isValid():
            self.table_view.selectRow(index.row())

        menu = QMenu(self)
        action_edit = QAction('ویرایش', self)
        action_delete = QAction('حذف', self)
        action_returned = QAction('علامت گذاری به عنوان برگشتی', self)

        action_edit.triggered.connect(self.edit_selected)
        action_delete.triggered.connect(self.delete_selected)
        action_returned.triggered.connect(self.mark_selected_returned)

        menu.addAction(action_edit)
        menu.addAction(action_delete)
        menu.addSeparator()
        menu.addAction(action_returned)
        menu.exec(self.table_view.viewport().mapToGlobal(pos))
