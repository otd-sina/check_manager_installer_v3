"""Dialog for creating or editing expense records."""

from __future__ import annotations

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from models.expense_model import Expense
from services.expense_service import ExpenseService
from ui.form_validation import reset_invalid, set_invalid

from widgets.jalali_date_picker import JalaliDatePicker


class AddExpenseDialog(QDialog):
    """Collect expense fields with light client-side validation."""

    def __init__(
        self,
        expense_service: ExpenseService,
        parent: QWidget | None = None,
        expense: Expense | None = None,
    ):
        super().__init__(parent)
        self.expense_service = expense_service
        self._editing_expense_id = expense.id if expense else None

        self.setObjectName('appFormDialog')
        self.setWindowTitle('ثبت / ویرایش هزینه')
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(560, 620)

        self._setup_ui()
        self._load_categories()
        self._load_linked_checks()

        if expense is not None:
            self._load_expense(expense)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 12)
        main_layout.setSpacing(12)

        header_panel = QFrame(self)
        header_panel.setObjectName('dialogHeaderPanel')
        header_layout = QVBoxLayout(header_panel)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(2)

        title = QLabel('فرم ثبت هزینه روزانه')
        title.setObjectName('formDialogTitle')
        subtitle = QLabel('لطفا رکورد هزینه را با دسته بندی و مبلغ معتبر ثبت کنید.')
        subtitle.setObjectName('formDialogSubtitle')
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        main_layout.addWidget(header_panel)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.verticalScrollBar().setSingleStep(18)

        form_container = QWidget(self)
        form_container.setObjectName('formCard')
        form_layout = QFormLayout(form_container)
        form_layout.setContentsMargins(14, 12, 14, 12)
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setFormAlignment(Qt.AlignTop | Qt.AlignRight)
        form_layout.setSpacing(12)

        self.edt_title = QLineEdit(self)
        self.edt_title.setMaxLength(120)
        self.edt_title.setPlaceholderText('مثلا: خرید تجهیزات، پرداخت قبض، هزینه خدمات')
        form_layout.addRow(QLabel('عنوان هزینه*', self), self.edt_title)

        self.cmb_category = QComboBox(self)
        form_layout.addRow(QLabel('دسته بندی*', self), self.cmb_category)

        self.edt_amount = QLineEdit(self)
        self.edt_amount.setMaxLength(16)
        self.edt_amount.setValidator(
            QRegularExpressionValidator(QRegularExpression(r'[\d,]*'), self)
        )
        self.edt_amount.setPlaceholderText('مثلا: 2,500,000')
        self.edt_amount.textChanged.connect(self._format_amount_with_commas)
        form_layout.addRow(QLabel('مبلغ (ریال)*', self), self.edt_amount)

        self.date_expense = JalaliDatePicker(self)
        form_layout.addRow(QLabel('تاریخ هزینه*', self), self.date_expense)

        self.cmb_payment_method = QComboBox(self)
        for code, label in ExpenseService.PAYMENT_METHODS.items():
            self.cmb_payment_method.addItem(label, code)
        form_layout.addRow(QLabel('روش پرداخت', self), self.cmb_payment_method)

        name_regex = QRegularExpression(r"[آ-یءئؤإأا-يA-Za-z0-9\s\-\._()]*")
        self.edt_vendor = QLineEdit(self)
        self.edt_vendor.setMaxLength(120)
        self.edt_vendor.setValidator(QRegularExpressionValidator(name_regex, self))
        self.edt_vendor.setPlaceholderText('نام فروشنده، مرکز خدمت یا دریافت کننده')
        form_layout.addRow(QLabel('فروشنده / پرداخت شونده', self), self.edt_vendor)

        self.cmb_reference_check = QComboBox(self)
        form_layout.addRow(QLabel('مرجع چک (اختیاری)', self), self.cmb_reference_check)

        self.txt_notes = QTextEdit(self)
        self.txt_notes.setPlaceholderText('جزئیات تکمیلی، شماره فاکتور یا یادداشت داخلی...')
        self.txt_notes.setFixedHeight(120)
        form_layout.addRow(QLabel('توضیحات', self), self.txt_notes)

        scroll.setWidget(form_container)
        main_layout.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch()

        self.btn_save = QPushButton('ذخیره')
        self.btn_cancel = QPushButton('انصراف')
        buttons.addWidget(self.btn_save)
        buttons.addWidget(self.btn_cancel)
        main_layout.addLayout(buttons)

        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def _load_categories(self):
        self.cmb_category.clear()
        categories = self.expense_service.list_categories()
        for category in categories:
            self.cmb_category.addItem(category.name, category.id)

    def _load_linked_checks(self):
        self.cmb_reference_check.clear()
        self.cmb_reference_check.addItem('بدون مرجع چک', None)

        for check in self.expense_service.list_linkable_checks():
            label = (
                f"#{check['id']} | {check['serial_7']} | "
                f"{check['registrant_name']} | {check['amount']:,}"
            )
            self.cmb_reference_check.addItem(label, check['id'])

    def _load_expense(self, expense: Expense):
        self.edt_title.setText(expense.title)
        self.edt_amount.setText(f'{int(expense.amount or 0):,}')
        self.date_expense.set_jalali_date_text(expense.expense_date)
        self.edt_vendor.setText(expense.vendor or '')
        self.txt_notes.setPlainText(expense.notes or '')

        category_index = self.cmb_category.findData(expense.category_id)
        if category_index >= 0:
            self.cmb_category.setCurrentIndex(category_index)

        method_index = self.cmb_payment_method.findData(expense.payment_method)
        if method_index >= 0:
            self.cmb_payment_method.setCurrentIndex(method_index)

        check_index = self.cmb_reference_check.findData(expense.reference_check_id)
        if check_index >= 0:
            self.cmb_reference_check.setCurrentIndex(check_index)

    def _format_amount_with_commas(self, text: str):
        digits_only = ''.join(ch for ch in text if ch.isdigit())
        formatted = f'{int(digits_only):,}' if digits_only else ''

        self.edt_amount.blockSignals(True)
        self.edt_amount.setText(formatted)
        self.edt_amount.setCursorPosition(len(formatted))
        self.edt_amount.blockSignals(False)

    def get_expense(self) -> Expense:
        amount_text = self.edt_amount.text().replace(',', '').strip()
        amount = int(amount_text or '0')
        return Expense(
            id=self._editing_expense_id,
            title=self.edt_title.text().strip(),
            amount=amount,
            expense_date=self.date_expense.jalali_text_date(),
            category_id=int(self.cmb_category.currentData() or 0),
            payment_method=self.cmb_payment_method.currentData() or 'OTHER',
            reference_check_id=self.cmb_reference_check.currentData(),
            vendor=self.edt_vendor.text().strip(),
            notes=self.txt_notes.toPlainText().strip(),
        )

    def accept(self):
        errors: list[str] = []
        reset_invalid(self._validation_widgets())

        if not self.edt_title.text().strip():
            errors.append('عنوان هزینه نمی تواند خالی باشد.')
            set_invalid(self.edt_title, True)

        amount_text = self.edt_amount.text().replace(',', '').strip()
        if not amount_text.isdigit() or int(amount_text) <= 0:
            errors.append('مبلغ هزینه باید عددی و بزرگ تر از صفر باشد.')
            set_invalid(self.edt_amount, True)

        if self.cmb_category.currentData() is None:
            errors.append('لطفا یک دسته بندی انتخاب کنید.')
            set_invalid(self.cmb_category, True)

        if errors:
            for widget in self._validation_widgets():
                if widget.property('invalid'):
                    widget.setFocus(Qt.OtherFocusReason)
                    break
            QMessageBox.warning(self, 'خطای اعتبارسنجی', '\n'.join(errors))
            return

        super().accept()

    def _validation_widgets(self) -> list[QWidget]:
        return [
            self.edt_title,
            self.cmb_category,
            self.edt_amount,
        ]
