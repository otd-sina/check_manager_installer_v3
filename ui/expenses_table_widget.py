from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, QSortFilterProxyModel, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from models.expense_model import Expense
from services.expense_service import ExpenseService
from ui.add_expense_dialog import AddExpenseDialog
from utils.date_utils import normalize_jalali_date_text, today_jalali


class ExpensesTableModel(QAbstractTableModel):
    HEADERS = [
        'ID',
        'عنوان هزینه',
        'دسته بندی',
        'روش پرداخت',
        'مبلغ (ریال)',
        'تاریخ',
        'فروشنده / پرداخت شونده',
        'مرجع چک',
        'توضیحات',
    ]

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._expenses: list[Expense] = []

    def set_expenses(self, expenses: list[Expense]):
        self.beginResetModel()
        self._expenses = expenses
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._expenses)

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

        expense = self._expenses[index.row()]
        column = index.column()

        if role == Qt.DisplayRole:
            return self._display_value(expense, column)
        if role == Qt.TextAlignmentRole:
            if column in {0, 4, 5, 7}:
                return int(Qt.AlignCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.BackgroundRole:
            return self._background_color(expense)
        if role == Qt.ForegroundRole:
            if expense.amount >= 50_000_000 and column == 4:
                return QColor('#b91c1c')
            return None
        if role == Qt.UserRole:
            return expense
        return None

    def expense_at(self, row: int) -> Expense | None:
        if 0 <= row < len(self._expenses):
            return self._expenses[row]
        return None

    def _display_value(self, expense: Expense, column: int):
        values = [
            str(expense.id or ''),
            expense.title,
            expense.category_name,
            ExpenseService.PAYMENT_METHODS.get(expense.payment_method, expense.payment_method),
            f'{int(expense.amount or 0):,}',
            expense.expense_date,
            expense.vendor,
            str(expense.reference_check_id or '-'),
            expense.notes,
        ]
        return values[column]

    @staticmethod
    def _background_color(expense: Expense):
        today = today_jalali().strftime('%Y/%m/%d')
        if expense.expense_date == today:
            return QColor('#ecfeff')
        if expense.reference_check_id:
            return QColor('#f8fafc')
        return None


class ExpensesFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.search_text = ''
        self.category_filter: int | None = None
        self.payment_filter = ''
        self.from_date_filter = ''
        self.to_date_filter = ''
        self.quick_filter = 'all'
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setDynamicSortFilter(True)

    def set_search_text(self, text: str):
        self.search_text = (text or '').strip().lower()
        self.invalidateFilter()

    def set_category_filter(self, category_id: int | None):
        self.category_filter = category_id
        self.invalidateFilter()

    def set_payment_filter(self, payment_method: str):
        self.payment_filter = (payment_method or '').strip().upper()
        self.invalidateFilter()

    def set_date_range_filter(self, from_date: str, to_date: str):
        self.from_date_filter = self._safe_date(from_date)
        self.to_date_filter = self._safe_date(to_date)
        self.invalidateFilter()

    def set_quick_filter(self, quick_filter: str):
        self.quick_filter = quick_filter
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex):
        model = self.sourceModel()
        if model is None:
            return False

        expense = model.expense_at(source_row)
        if expense is None:
            return False

        if self.category_filter is not None and expense.category_id != self.category_filter:
            return False

        if self.payment_filter and expense.payment_method != self.payment_filter:
            return False

        if self.from_date_filter and expense.expense_date < self.from_date_filter:
            return False

        if self.to_date_filter and expense.expense_date > self.to_date_filter:
            return False

        if not self._matches_quick_filter(expense):
            return False

        if not self.search_text:
            return True

        haystack = ' '.join(
            [
                str(expense.id or ''),
                expense.title,
                expense.category_name,
                expense.vendor or '',
                expense.notes or '',
                str(expense.amount or ''),
                expense.expense_date,
                str(expense.reference_check_id or ''),
                expense.payment_method,
                ExpenseService.PAYMENT_METHODS.get(expense.payment_method, ''),
            ]
        ).lower()
        return self.search_text in haystack

    def lessThan(self, left: QModelIndex, right: QModelIndex):
        model = self.sourceModel()
        if model is None:
            return super().lessThan(left, right)

        left_expense = model.expense_at(left.row())
        right_expense = model.expense_at(right.row())
        if left_expense is None or right_expense is None:
            return super().lessThan(left, right)

        if left.column() == 0:
            return int(left_expense.id or 0) < int(right_expense.id or 0)
        if left.column() == 4:
            return int(left_expense.amount or 0) < int(right_expense.amount or 0)
        if left.column() == 5:
            return (left_expense.expense_date or '') < (right_expense.expense_date or '')
        return super().lessThan(left, right)

    def _matches_quick_filter(self, expense: Expense) -> bool:
        if self.quick_filter == 'all':
            return True

        today_text = today_jalali().strftime('%Y/%m/%d')
        month_prefix = today_text[:7]
        expense_date = self._safe_date(expense.expense_date)
        today_date = self._safe_date(today_text)

        if self.quick_filter == 'today':
            return expense_date == today_date

        if self.quick_filter == 'month':
            return expense.expense_date.startswith(month_prefix)

        if self.quick_filter == 'linked':
            return expense.reference_check_id is not None

        return True

    @staticmethod
    def _safe_date(value: str) -> str:
        if not value:
            return ''
        try:
            return normalize_jalali_date_text(value)
        except ValueError:
            return ''


class ExpensesTableWidget(QWidget):
    expensesChanged = Signal()
    filtersChanged = Signal()

    def __init__(self, expense_service: ExpenseService, parent=None):
        super().__init__(parent)
        self.expense_service = expense_service
        self.model = ExpensesTableModel(self)
        self.proxy_model = ExpensesFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        filters_layout = QHBoxLayout()
        filters_layout.setSpacing(10)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText('جستجو در عنوان، دسته بندی، فروشنده، مرجع چک، مبلغ یا توضیحات')
        filters_layout.addWidget(self.search_input, 1)

        self.category_filter = QComboBox(self)
        self.category_filter.addItem('همه دسته ها', None)
        filters_layout.addWidget(self.category_filter)

        self.payment_filter = QComboBox(self)
        self.payment_filter.addItem('همه روش های پرداخت', '')
        for code, label in ExpenseService.PAYMENT_METHODS.items():
            self.payment_filter.addItem(label, code)
        filters_layout.addWidget(self.payment_filter)

        self.from_date_filter = QLineEdit(self)
        self.from_date_filter.setPlaceholderText('از تاریخ: 1405/01/01')
        self.from_date_filter.setLayoutDirection(Qt.LeftToRight)
        filters_layout.addWidget(self.from_date_filter)

        self.to_date_filter = QLineEdit(self)
        self.to_date_filter.setPlaceholderText('تا تاریخ: 1405/01/31')
        self.to_date_filter.setLayoutDirection(Qt.LeftToRight)
        filters_layout.addWidget(self.to_date_filter)

        layout.addLayout(filters_layout)

        quick_filters_layout = QHBoxLayout()
        quick_filters_layout.setSpacing(8)
        self.quick_filter_buttons: dict[str, QPushButton] = {}

        for key, label in [
            ('all', 'همه'),
            ('today', 'امروز'),
            ('month', 'ماه جاری'),
            ('linked', 'دارای مرجع چک'),
        ]:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName('filterChipButton')
            button.clicked.connect(lambda checked, value=key: self._set_quick_filter(value))
            quick_filters_layout.addWidget(button)
            self.quick_filter_buttons[key] = button

        quick_filters_layout.addStretch()
        layout.addLayout(quick_filters_layout)

        self.table_view = QTableView(self)
        self.table_view.setModel(self.proxy_model)
        self.table_view.setObjectName('expensesTableView')
        self.table_view.setSortingEnabled(True)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setSelectionMode(QTableView.SingleSelection)
        self.table_view.setEditTriggers(QTableView.NoEditTriggers)
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.setVerticalScrollMode(QTableView.ScrollPerPixel)
        self.table_view.setHorizontalScrollMode(QTableView.ScrollPerPixel)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(8, QHeaderView.Stretch)
        self.table_view.setColumnHidden(0, True)
        layout.addWidget(self.table_view, 1)

        self.search_input.textChanged.connect(self.proxy_model.set_search_text)
        self.search_input.textChanged.connect(self.filtersChanged.emit)
        self.category_filter.currentIndexChanged.connect(self._on_category_changed)
        self.payment_filter.currentIndexChanged.connect(self._on_payment_changed)
        self.from_date_filter.textChanged.connect(self._on_date_changed)
        self.to_date_filter.textChanged.connect(self._on_date_changed)
        self.table_view.customContextMenuRequested.connect(self._open_context_menu)
        self.table_view.doubleClicked.connect(lambda _: self.edit_selected())

        self.proxy_model.layoutChanged.connect(self.filtersChanged.emit)
        self.proxy_model.modelReset.connect(self.filtersChanged.emit)

        self._set_quick_filter('all')
        self.proxy_model.sort(5, Qt.DescendingOrder)

    def refresh(self):
        self._reload_category_filter_options()
        self.table_view.setUpdatesEnabled(False)
        try:
            self.model.set_expenses(self.expense_service.list_expenses())
            self.table_view.sortByColumn(5, Qt.DescendingOrder)
        finally:
            self.table_view.setUpdatesEnabled(True)
        self.filtersChanged.emit()

    def filtered_expenses(self) -> list[Expense]:
        expenses: list[Expense] = []
        for row in range(self.proxy_model.rowCount()):
            proxy_index = self.proxy_model.index(row, 0)
            source_index = self.proxy_model.mapToSource(proxy_index)
            expense = self.model.expense_at(source_index.row())
            if expense is not None:
                expenses.append(expense)
        return expenses

    def current_filters(self) -> dict:
        return {
            'search_text': self.search_input.text().strip(),
            'category_id': self.category_filter.currentData(),
            'payment_method': self.payment_filter.currentData() or '',
            'from_date': self.from_date_filter.text().strip(),
            'to_date': self.to_date_filter.text().strip(),
            'quick_filter': self.proxy_model.quick_filter,
        }

    def current_expense(self) -> Expense | None:
        index = self.table_view.currentIndex()
        if not index.isValid():
            return None
        source_index = self.proxy_model.mapToSource(index)
        return self.model.expense_at(source_index.row())

    def edit_selected(self):
        expense = self.current_expense()
        if expense is None:
            QMessageBox.warning(self, 'خطا', 'لطفا یک هزینه را انتخاب کنید.')
            return

        dialog = AddExpenseDialog(self.expense_service, self, expense)
        if dialog.exec():
            try:
                self.expense_service.update_expense(dialog.get_expense())
            except ValueError as exc:
                QMessageBox.warning(self, 'خطا', str(exc))
                return
            self.refresh()
            self.expensesChanged.emit()

    def delete_selected(self):
        expense = self.current_expense()
        if expense is None:
            QMessageBox.warning(self, 'خطا', 'لطفا یک هزینه را انتخاب کنید.')
            return

        reply = QMessageBox.question(
            self,
            'حذف هزینه',
            'آیا از حذف این هزینه مطمئن هستید؟',
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.expense_service.delete_expense(int(expense.id or 0))
        except ValueError as exc:
            QMessageBox.warning(self, 'خطا', str(exc))
            return

        self.refresh()
        self.expensesChanged.emit()

    def _reload_category_filter_options(self):
        previous = self.category_filter.currentData()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem('همه دسته ها', None)

        for category in self.expense_service.list_categories():
            self.category_filter.addItem(category.name, category.id)

        if previous is not None:
            index = self.category_filter.findData(previous)
            if index >= 0:
                self.category_filter.setCurrentIndex(index)
        self.category_filter.blockSignals(False)

    def _on_category_changed(self):
        self.proxy_model.set_category_filter(self.category_filter.currentData())
        self.filtersChanged.emit()

    def _on_payment_changed(self):
        self.proxy_model.set_payment_filter(self.payment_filter.currentData() or '')
        self.filtersChanged.emit()

    def _on_date_changed(self):
        self.proxy_model.set_date_range_filter(
            self.from_date_filter.text().strip(),
            self.to_date_filter.text().strip(),
        )
        self.filtersChanged.emit()

    def _set_quick_filter(self, value: str):
        self.proxy_model.set_quick_filter(value)
        for key, button in self.quick_filter_buttons.items():
            button.setChecked(key == value)
        self.filtersChanged.emit()

    def _open_context_menu(self, pos):
        index = self.table_view.indexAt(pos)
        if index.isValid():
            self.table_view.selectRow(index.row())

        menu = QMenu(self)
        action_edit = QAction('ویرایش هزینه', self)
        action_delete = QAction('حذف هزینه', self)
        action_edit.triggered.connect(self.edit_selected)
        action_delete.triggered.connect(self.delete_selected)
        menu.addAction(action_edit)
        menu.addAction(action_delete)
        menu.exec(self.table_view.viewport().mapToGlobal(pos))
