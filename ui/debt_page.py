from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QRegularExpression,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from models.debt import Debt
from services.debt_service import DebtService
from ui.form_validation import reset_invalid, set_invalid
from widgets.jalali_date_picker import JalaliDatePicker


class AddDebtDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, debt: Debt | None = None):
        super().__init__(parent)
        self._editing_debt_id = debt.id if debt else None

        self.setObjectName('appFormDialog')
        self.setWindowTitle('ثبت / ویرایش بدهی')
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(540, 420)

        self._setup_ui()
        if debt is not None:
            self._load_debt(debt)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(12)

        header_panel = QFrame(self)
        header_panel.setObjectName('dialogHeaderPanel')
        header_layout = QVBoxLayout(header_panel)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(2)

        title = QLabel('فرم مدیریت بدهی')
        title.setObjectName('formDialogTitle')
        subtitle = QLabel('اطلاعات بدهکار را وارد کنید. مانده و وضعیت به صورت خودکار محاسبه می شود.')
        subtitle.setObjectName('formDialogSubtitle')
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header_panel)

        card = QFrame(self)
        card.setObjectName('formCard')
        form = QFormLayout(card)
        form.setContentsMargins(14, 12, 14, 12)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignTop | Qt.AlignRight)
        form.setSpacing(12)

        self.edt_debtor_name = QLineEdit(self)
        self.edt_debtor_name.setMaxLength(100)
        self.edt_debtor_name.setPlaceholderText('نام شخص یا مشتری')
        form.addRow(QLabel('نام بدهکار*', self), self.edt_debtor_name)

        self.edt_phone = QLineEdit(self)
        self.edt_phone.setMaxLength(11)
        self.edt_phone.setValidator(QRegularExpressionValidator(QRegularExpression(r'^\d{11}$'), self))
        self.edt_phone.setPlaceholderText('مثال: 09123456789')
        form.addRow(QLabel('شماره تماس*', self), self.edt_phone)

        amount_validator = QRegularExpressionValidator(QRegularExpression(r'[\d,]*'), self)

        self.edt_total_amount = QLineEdit(self)
        self.edt_total_amount.setValidator(amount_validator)
        self.edt_total_amount.setPlaceholderText('مبلغ بدهی (ریال)')
        self.edt_total_amount.textChanged.connect(self._format_total_amount)
        self.edt_total_amount.textChanged.connect(self._refresh_computed_fields)
        form.addRow(QLabel('مبلغ بدهی*', self), self.edt_total_amount)

        self.edt_paid_amount = QLineEdit(self)
        self.edt_paid_amount.setValidator(amount_validator)
        self.edt_paid_amount.setPlaceholderText('مبلغ پرداخت شده')
        self.edt_paid_amount.textChanged.connect(self._format_paid_amount)
        self.edt_paid_amount.textChanged.connect(self._refresh_computed_fields)
        form.addRow(QLabel('مبلغ پرداخت شده', self), self.edt_paid_amount)

        self.lbl_remaining_balance = QLabel('0')
        self.lbl_remaining_balance.setObjectName('dashboardHintBadge')
        form.addRow(QLabel('مانده بدهی', self), self.lbl_remaining_balance)

        self.date_purchase = JalaliDatePicker(self)
        form.addRow(QLabel('تاریخ خرید*', self), self.date_purchase)

        self.date_due = JalaliDatePicker(self)
        form.addRow(QLabel('تاریخ سررسید', self), self.date_due)

        self.edt_description = QLineEdit(self)
        self.edt_description.setMaxLength(500)
        self.edt_description.setPlaceholderText('توضیحات اختیاری')
        form.addRow(QLabel('توضیحات', self), self.edt_description)

        self.cmb_status = QComboBox(self)
        self.cmb_status.setEnabled(False)
        self.cmb_status.addItem('پرداخت نشده', 'UNPAID')
        self.cmb_status.addItem('پرداخت ناقص', 'PARTIAL')
        self.cmb_status.addItem('تسویه شده', 'PAID')
        form.addRow(QLabel('وضعیت', self), self.cmb_status)

        layout.addWidget(card, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        self.btn_save = QPushButton('ذخیره')
        self.btn_cancel = QPushButton('انصراف')
        actions.addWidget(self.btn_save)
        actions.addWidget(self.btn_cancel)
        layout.addLayout(actions)

        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        self._refresh_computed_fields()

    def _format_total_amount(self, text: str):
        self._format_amount_field(self.edt_total_amount, text)

    def _format_paid_amount(self, text: str):
        self._format_amount_field(self.edt_paid_amount, text)

    @staticmethod
    def _format_amount_field(widget: QLineEdit, text: str):
        digits_only = ''.join(ch for ch in text if ch.isdigit())
        formatted = f'{int(digits_only):,}' if digits_only else ''

        widget.blockSignals(True)
        widget.setText(formatted)
        widget.setCursorPosition(len(formatted))
        widget.blockSignals(False)

    def _load_debt(self, debt: Debt):
        self.edt_debtor_name.setText(debt.debtor_name)
        self.edt_phone.setText(debt.phone)
        self.edt_total_amount.setText(f'{int(debt.total_amount or 0):,}')
        self.edt_paid_amount.setText(f'{int(debt.paid_amount or 0):,}')
        if debt.purchase_date:
            self.date_purchase.set_jalali_date_text(debt.purchase_date)
        if debt.due_date:
            self.date_due.set_jalali_date_text(debt.due_date)
        self.edt_description.setText(debt.description or '')
        self._refresh_computed_fields()

    def _refresh_computed_fields(self):
        total_amount = self._amount_from_text(self.edt_total_amount.text())
        paid_amount = self._amount_from_text(self.edt_paid_amount.text())
        if paid_amount > total_amount:
            paid_amount = total_amount

        remaining = max(total_amount - paid_amount, 0)
        self.lbl_remaining_balance.setText(f'{remaining:,}')

        if remaining == 0 and total_amount > 0:
            status = 'PAID'
        elif paid_amount == 0:
            status = 'UNPAID'
        else:
            status = 'PARTIAL'

        index = self.cmb_status.findData(status)
        if index >= 0:
            self.cmb_status.setCurrentIndex(index)

    @staticmethod
    def _amount_from_text(text: str) -> int:
        raw = (text or '').replace(',', '').strip()
        return int(raw) if raw.isdigit() else 0

    def accept(self):
        errors: list[str] = []
        reset_invalid(self._validation_widgets())

        debtor_name = self.edt_debtor_name.text().strip()
        phone = self.edt_phone.text().strip()
        total_amount = self._amount_from_text(self.edt_total_amount.text())
        paid_amount = self._amount_from_text(self.edt_paid_amount.text())

        if not debtor_name:
            errors.append('نام بدهکار الزامی است.')
            set_invalid(self.edt_debtor_name, True)

        if len(phone) != 11:
            errors.append('تلفن همراه باید دقیقا 11 رقم باشد.')
            set_invalid(self.edt_phone, True)

        if total_amount <= 0:
            errors.append('مبلغ بدهی باید بزرگ تر از صفر باشد.')
            set_invalid(self.edt_total_amount, True)

        if paid_amount > total_amount:
            errors.append('مبلغ پرداخت شده نمی تواند بیشتر از مبلغ بدهی باشد.')
            set_invalid(self.edt_paid_amount, True)

        if errors:
            for widget in self._validation_widgets():
                if widget.property('invalid'):
                    widget.setFocus(Qt.OtherFocusReason)
                    break
            QMessageBox.warning(self, 'خطای اعتبارسنجی', '\n'.join(errors))
            return

        super().accept()

    def get_debt(self) -> Debt:
        total_amount = self._amount_from_text(self.edt_total_amount.text())
        paid_amount = self._amount_from_text(self.edt_paid_amount.text())
        remaining = max(total_amount - paid_amount, 0)

        return Debt(
            id=self._editing_debt_id,
            debtor_name=self.edt_debtor_name.text().strip(),
            phone=self.edt_phone.text().strip(),
            purchase_date=self.date_purchase.jalali_text_date(),
            due_date=self.date_due.jalali_text_date(),
            total_amount=total_amount,
            paid_amount=paid_amount,
            remaining_balance=remaining,
            status=self.cmb_status.currentData() or 'UNPAID',
            description=self.edt_description.text().strip(),
        )

    def _validation_widgets(self) -> list[QWidget]:
        return [
            self.edt_debtor_name,
            self.edt_phone,
            self.edt_total_amount,
            self.edt_paid_amount,
            self.edt_description,
        ]


class DebtsTableModel(QAbstractTableModel):
    HEADERS = [
        'ID',
        'نام بدهکار',
        'شماره تماس',
        'تاریخ خرید',
        'مبلغ بدهی',
        'پرداخت شده',
        'مانده بدهی',
        'تاریخ سررسید',
        'وضعیت',
        'توضیحات',
    ]

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._debts: list[Debt] = []

    def set_debts(self, debts: list[Debt]):
        self.beginResetModel()
        self._debts = debts
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._debts)

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

        debt = self._debts[index.row()]
        column = index.column()

        if role == Qt.DisplayRole:
            return self._display_value(debt, column)

        if role == Qt.TextAlignmentRole:
            if column in {0, 3, 4, 5, 6, 7, 8}:
                return int(Qt.AlignCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        if role == Qt.ForegroundRole and column == 6:
            if int(debt.remaining_balance or 0) > 0:
                return QColor('#b91c1c')
            return QColor('#15803d')

        if role == Qt.BackgroundRole and column == 8:
            status = (debt.status or '').upper()
            if status == 'PAID':
                return QColor('#dcfce7')
            if status == 'PARTIAL':
                return QColor('#fef3c7')
            return QColor('#fee2e2')

        if role == Qt.UserRole:
            return debt

        return None

    def debt_at(self, row: int) -> Debt | None:
        if 0 <= row < len(self._debts):
            return self._debts[row]
        return None

    def _display_value(self, debt: Debt, column: int):
        values = [
            str(debt.id or ''),
            debt.debtor_name or '-',
            debt.phone or '-',
            debt.purchase_date or '-',
            f'{int(debt.total_amount or 0):,}',
            f'{int(debt.paid_amount or 0):,}',
            f'{int(debt.remaining_balance or 0):,}',
            debt.due_date or '-',
            DebtService.STATUS_LABELS.get((debt.status or '').upper(), debt.status or '-'),
            debt.description or '-',
        ]
        return values[column]


class DebtsFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.search_text = ''
        self.status_filter = ''
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setDynamicSortFilter(True)

    def set_search_text(self, text: str):
        self.search_text = (text or '').strip().lower()
        self.invalidateFilter()

    def set_status_filter(self, status: str):
        self.status_filter = (status or '').strip().upper()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex):
        model = self.sourceModel()
        if model is None:
            return False

        debt = model.debt_at(source_row)
        if debt is None:
            return False

        if self.status_filter and (debt.status or '').upper() != self.status_filter:
            return False

        if not self.search_text:
            return True

        haystack = ' '.join(
            [
                str(debt.id or ''),
                debt.debtor_name or '',
                debt.phone or '',
                debt.purchase_date or '',
                str(debt.total_amount or ''),
                str(debt.paid_amount or ''),
                str(debt.remaining_balance or ''),
                debt.due_date or '',
                debt.status or '',
                debt.description or '',
                DebtService.STATUS_LABELS.get((debt.status or '').upper(), ''),
            ]
        ).lower()
        return self.search_text in haystack

    def lessThan(self, left: QModelIndex, right: QModelIndex):
        model = self.sourceModel()
        if model is None:
            return super().lessThan(left, right)

        left_debt = model.debt_at(left.row())
        right_debt = model.debt_at(right.row())
        if left_debt is None or right_debt is None:
            return super().lessThan(left, right)

        if left.column() == 0:
            return int(left_debt.id or 0) < int(right_debt.id or 0)
        if left.column() == 3:
            return (left_debt.purchase_date or '') < (right_debt.purchase_date or '')
        if left.column() == 4:
            return int(left_debt.total_amount or 0) < int(right_debt.total_amount or 0)
        if left.column() == 5:
            return int(left_debt.paid_amount or 0) < int(right_debt.paid_amount or 0)
        if left.column() == 6:
            return int(left_debt.remaining_balance or 0) < int(right_debt.remaining_balance or 0)
        if left.column() == 7:
            return (left_debt.due_date or '') < (right_debt.due_date or '')
        return super().lessThan(left, right)


class DebtPage(QWidget):
    debtsChanged = Signal()

    def __init__(self, debt_service: DebtService, export_service=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.debt_service = debt_service
        self.export_service = export_service
        self.model = DebtsTableModel(self)
        self.proxy_model = DebtsFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)

        self.metric_values: dict[str, QLabel] = {}

        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(20, 20, 20, 20)
        page_layout.setSpacing(12)

        header_panel = QFrame(self)
        header_panel.setObjectName('pageTopFixedPanel')
        header_layout = QHBoxLayout(header_panel)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(12)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        title = QLabel('لیست بدهکاران')
        title.setObjectName('pageTitle')
        subtitle = QLabel('مدیریت حساب های دریافتنی، پیگیری پرداخت ها و مانده بدهی')
        subtitle.setObjectName('pageSubtitle')
        subtitle.setWordWrap(True)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header_layout.addLayout(title_layout, 1)

        self.btn_refresh = QPushButton('به روزرسانی')
        self.btn_refresh.setObjectName('dashboardRefreshButton')
        self.btn_refresh.clicked.connect(self.refresh)
        header_layout.addWidget(self.btn_refresh)

        page_layout.addWidget(header_panel)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)
        self.metric_values['outstanding'] = self._create_summary_card(
            cards_layout,
            'مطالبات باقی مانده',
            '0',
            'جمع مانده بدهی های پرداخت نشده یا ناقص',
        )
        self.metric_values['total_debt'] = self._create_summary_card(
            cards_layout,
            'مجموع مبلغ بدهی',
            '0',
            'جمع کل مبلغ ثبت شده برای بدهکاران',
        )
        self.metric_values['count'] = self._create_summary_card(
            cards_layout,
            'تعداد بدهکاران',
            '0',
            'تعداد رکوردهای نمایش داده شده در جدول',
        )
        page_layout.addLayout(cards_layout)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText('جستجو بر اساس نام بدهکار، تلفن، مبلغ یا وضعیت')
        controls_layout.addWidget(self.search_input, 1)

        self.status_filter = QComboBox(self)
        self.status_filter.addItem('همه وضعیت ها', '')
        self.status_filter.addItem('پرداخت نشده', 'UNPAID')
        self.status_filter.addItem('پرداخت ناقص', 'PARTIAL')
        self.status_filter.addItem('تسویه شده', 'PAID')
        controls_layout.addWidget(self.status_filter)

        self.btn_add = QPushButton('ثبت بدهی')
        self.btn_edit = QPushButton('ویرایش')
        self.btn_delete = QPushButton('حذف')
        self.btn_export = QPushButton('خروجی اکسل')

        controls_layout.addWidget(self.btn_add)
        controls_layout.addWidget(self.btn_edit)
        controls_layout.addWidget(self.btn_delete)
        controls_layout.addWidget(self.btn_export)
        page_layout.addLayout(controls_layout)

        self.table_view = QTableView(self)
        self.table_view.setObjectName('debtsTableView')
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
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_view.setColumnHidden(0, True)
        page_layout.addWidget(self.table_view, 1)

        self.search_input.textChanged.connect(self.proxy_model.set_search_text)
        self.search_input.textChanged.connect(self._refresh_metrics)
        self.status_filter.currentIndexChanged.connect(self._on_status_filter_changed)

        self.proxy_model.layoutChanged.connect(self._refresh_metrics)
        self.proxy_model.modelReset.connect(self._refresh_metrics)

        self.btn_add.clicked.connect(self._add_debt)
        self.btn_edit.clicked.connect(self._edit_debt)
        self.btn_delete.clicked.connect(self._delete_debt)
        self.btn_export.clicked.connect(self._export_debts)

        self.table_view.customContextMenuRequested.connect(self._open_context_menu)
        self.table_view.doubleClicked.connect(lambda *_: self._edit_debt())

        self.proxy_model.sort(7, Qt.AscendingOrder)

    def _create_summary_card(self, parent_layout, title_text: str, value_text: str, helper_text: str):
        card = QFrame()
        card.setObjectName('summaryCard')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)

        title = QLabel(title_text)
        title.setObjectName('summaryCardTitle')
        value = QLabel(value_text)
        value.setObjectName('summaryCardValue')
        helper = QLabel(helper_text)
        helper.setObjectName('summaryCardHelper')
        helper.setWordWrap(True)

        card_layout.addWidget(title)
        card_layout.addWidget(value)
        card_layout.addStretch()
        card_layout.addWidget(helper)

        parent_layout.addWidget(card, 1)
        return value

    def refresh(self):
        self.table_view.setUpdatesEnabled(False)
        try:
            self.model.set_debts(self.debt_service.list_debts())
            self.table_view.sortByColumn(7, Qt.AscendingOrder)
        finally:
            self.table_view.setUpdatesEnabled(True)
        self._refresh_metrics()

    def _filtered_debts(self) -> list[Debt]:
        rows: list[Debt] = []
        for row in range(self.proxy_model.rowCount()):
            proxy_index = self.proxy_model.index(row, 0)
            source_index = self.proxy_model.mapToSource(proxy_index)
            debt = self.model.debt_at(source_index.row())
            if debt is not None:
                rows.append(debt)
        return rows

    def _refresh_metrics(self):
        debts = self._filtered_debts()
        outstanding = sum(int(item.remaining_balance or 0) for item in debts)
        total_debt = sum(int(item.total_amount or 0) for item in debts)

        self.metric_values['outstanding'].setText(f'{outstanding:,}')
        self.metric_values['total_debt'].setText(f'{total_debt:,}')
        self.metric_values['count'].setText(str(len(debts)))

        if outstanding > 0:
            self.metric_values['outstanding'].setStyleSheet('color: #b91c1c;')
        else:
            self.metric_values['outstanding'].setStyleSheet('color: #15803d;')

    def _on_status_filter_changed(self):
        self.proxy_model.set_status_filter(self.status_filter.currentData() or '')
        self._refresh_metrics()

    def _current_debt(self) -> Debt | None:
        index = self.table_view.currentIndex()
        if not index.isValid():
            return None
        source_index = self.proxy_model.mapToSource(index)
        return self.model.debt_at(source_index.row())

    def _add_debt(self):
        dialog = AddDebtDialog(self)
        if not dialog.exec():
            return

        try:
            self.debt_service.add_debt(dialog.get_debt())
        except ValueError as exc:
            QMessageBox.warning(self, 'خطا', str(exc))
            return

        self.refresh()
        self.debtsChanged.emit()

    def _edit_debt(self):
        debt = self._current_debt()
        if debt is None:
            QMessageBox.information(self, 'ویرایش بدهی', 'ابتدا یک رکورد بدهی انتخاب کنید.')
            return

        dialog = AddDebtDialog(self, debt)
        if not dialog.exec():
            return

        try:
            self.debt_service.update_debt(dialog.get_debt())
        except ValueError as exc:
            QMessageBox.warning(self, 'خطا', str(exc))
            return

        self.refresh()
        self.debtsChanged.emit()

    def _delete_debt(self):
        debt = self._current_debt()
        if debt is None:
            QMessageBox.information(self, 'حذف بدهی', 'ابتدا یک رکورد بدهی انتخاب کنید.')
            return

        answer = QMessageBox.question(
            self,
            'حذف بدهی',
            f'آیا از حذف بدهی {debt.debtor_name} مطمئن هستید؟',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            self.debt_service.delete_debt(int(debt.id or 0))
        except ValueError as exc:
            QMessageBox.warning(self, 'خطا', str(exc))
            return

        self.refresh()
        self.debtsChanged.emit()

    def _export_debts(self):
        if self.export_service is None:
            QMessageBox.warning(self, 'خروجی اکسل', 'سرویس خروجی اکسل برای بدهی ها پیکربندی نشده است.')
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            'محل ذخیره گزارش بدهی ها',
            '',
            'Excel Files (*.xlsx)',
        )
        if not file_path:
            return

        try:
            result = self.export_service.export_debts_to_excel(
                file_path=file_path,
                debts=self._filtered_debts(),
            )
        except Exception as exc:
            QMessageBox.warning(self, 'خروجی اکسل', str(exc))
            return

        QMessageBox.information(self, 'خروجی اکسل', f'گزارش بدهی ها با موفقیت ذخیره شد\n{result}')

    def _open_context_menu(self, pos):
        index = self.table_view.indexAt(pos)
        if index.isValid():
            self.table_view.selectRow(index.row())

        menu = QMenu(self)
        action_edit = QAction('ویرایش بدهی', self)
        action_delete = QAction('حذف بدهی', self)
        action_edit.triggered.connect(self._edit_debt)
        action_delete.triggered.connect(self._delete_debt)
        menu.addAction(action_edit)
        menu.addAction(action_delete)
        menu.exec(self.table_view.viewport().mapToGlobal(pos))

    def trigger_add_debt(self):
        self._add_debt()

    def trigger_edit_debt(self):
        self._edit_debt()

    def trigger_delete_debt(self):
        self._delete_debt()

    def trigger_export_debts(self):
        self._export_debts()
