"""Dialog for creating or editing a check record."""

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

from models.check_model import Check
from ui.form_validation import reset_invalid, set_invalid
from utils.date_utils import (
    is_valid_jalali_date_text,
    jalali_to_gregorian,
    normalize_jalali_date_text,
)
from widgets.jalali_date_picker import JalaliDatePicker


class AddCheckDialog(QDialog):
    """Collect and validate check fields from the user."""

    STATUS_OPTIONS = [
        ("در انتظار وصول", "PENDING"),
        ("واگذار شده به بانک", "DEPOSITED"),
        ("وصول شده", "PAID"),
        ("تسویه شده", "CLEARED"),
        ("برگشت خورده", "BOUNCED"),
        ("عودت داده شده", "RETURNED"),
        ("پشت نویسی شده", "ENDORSED"),
        ("لغو شده", "CANCELED"),
    ]

    def __init__(self, parent: QWidget | None = None, check: Check | None = None):
        super().__init__(parent)

        self.setObjectName('appFormDialog')
        self.setWindowTitle("ثبت/ویرایش چک")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(560, 760)
        self.setMinimumWidth(470)

        self._setup_ui()

        if check is not None:
            self._load_check(check)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 12)
        main_layout.setSpacing(12)

        header_panel = QFrame(self)
        header_panel.setObjectName('dialogHeaderPanel')
        header_layout = QVBoxLayout(header_panel)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(2)

        title = QLabel('فرم ثبت چک', self)
        title.setObjectName('formDialogTitle')
        subtitle = QLabel('لطفا اطلاعات را کامل و دقیق وارد کنید.', self)
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

        name_regex = QRegularExpression(r"[آ-یءئؤإأا-يA-Za-z\s]*")
        name_validator = QRegularExpressionValidator(name_regex, self)

        serial18_regex = QRegularExpression(r"\d{0,16}")
        serial18_validator = QRegularExpressionValidator(serial18_regex, self)

        self.edt_serial_18 = QLineEdit(self)
        self.edt_serial_18.setMaxLength(16)
        self.edt_serial_18.setValidator(serial18_validator)
        self.edt_serial_18.setPlaceholderText("16 رقم")
        form_layout.addRow(QLabel("شماره صیادی چک 16 رقم*", self), self.edt_serial_18)

        self.edt_serial_7 = QLineEdit(self)
        self.edt_serial_7.setPlaceholderText("مثال: 12/AB-سلام-999999999")
        form_layout.addRow(QLabel("شماره سریال چک*", self), self.edt_serial_7)

        self.edt_registrant_name = QLineEdit(self)
        self.edt_registrant_name.setMaxLength(70)
        self.edt_registrant_name.setValidator(name_validator)
        self.edt_registrant_name.setPlaceholderText("فقط حروف فارسی یا انگلیسی")
        form_layout.addRow(QLabel("نام ثبتنام کننده*", self), self.edt_registrant_name)

        self.edt_bank = QLineEdit(self)
        self.edt_bank.setMaxLength(50)
        self.edt_bank.setValidator(name_validator)
        self.edt_bank.setPlaceholderText("نام بانک")
        form_layout.addRow(QLabel("نام بانک*", self), self.edt_bank)

        self.edt_owner = QLineEdit(self)
        self.edt_owner.setMaxLength(70)
        self.edt_owner.setValidator(name_validator)
        self.edt_owner.setPlaceholderText("فقط حروف فارسی یا انگلیسی")
        form_layout.addRow(QLabel("نام صاحب حساب*", self), self.edt_owner)

        self.edt_amount = QLineEdit(self)
        self.edt_amount.setMaxLength(18)
        self.edt_amount.setValidator(QRegularExpressionValidator(QRegularExpression(r"[\d,]*"), self))
        self.edt_amount.setPlaceholderText("مثلا: 1,000,000")
        self.edt_amount.textChanged.connect(self._format_amount_with_commas)
        form_layout.addRow(QLabel("مبلغ (ریال)*", self), self.edt_amount)

        self.edt_payee = QLineEdit(self)
        self.edt_payee.setMaxLength(70)
        self.edt_payee.setValidator(name_validator)
        form_layout.addRow(QLabel("دریافت کننده", self), self.edt_payee)

        self.date_issue = JalaliDatePicker(self)
        form_layout.addRow(QLabel("تاریخ صدور", self), self.date_issue)

        self.date_due = JalaliDatePicker(self)
        form_layout.addRow(QLabel("تاریخ سررسید", self), self.date_due)

        self.cmb_status = QComboBox(self)
        for label, code in self.STATUS_OPTIONS:
            self.cmb_status.addItem(label, code)
        form_layout.addRow(QLabel("وضعیت چک", self), self.cmb_status)

        self.txt_notes = QTextEdit(self)
        self.txt_notes.setFixedHeight(120)
        self.txt_notes.setPlaceholderText("هر توضیح اضافی در مورد چک...")
        form_layout.addRow(QLabel("توضیحات", self), self.txt_notes)

        scroll.setWidget(form_container)
        main_layout.addWidget(scroll)

        button_layout = QHBoxLayout()
        btn_ok = QPushButton("ذخیره", self)
        btn_cancel = QPushButton("انصراف", self)

        button_layout.addStretch()
        button_layout.addWidget(btn_ok)
        button_layout.addWidget(btn_cancel)
        main_layout.addLayout(button_layout)

        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

    def _format_amount_with_commas(self, text: str) -> None:
        """Keep amount input numeric and formatted with thousand separators."""

        digits_only = "".join(ch for ch in text if ch.isdigit())
        formatted = f"{int(digits_only):,}" if digits_only else ""

        self.edt_amount.blockSignals(True)
        self.edt_amount.setText(formatted)
        self.edt_amount.setCursorPosition(len(formatted))
        self.edt_amount.blockSignals(False)

    def _load_check(self, check: Check) -> None:
        self.edt_serial_18.setText(check.serial_18)
        self.edt_serial_7.setText(check.serial_7)
        self.edt_registrant_name.setText(check.registrant_name)
        self.edt_bank.setText(check.bank_name)
        self.edt_owner.setText(check.account_owner)
        self.edt_amount.setText(f"{int(check.amount or 0):,}")
        self.edt_payee.setText(check.payee_name or "")

        if check.issue_date:
            self.date_issue.set_jalali_date_text(normalize_jalali_date_text(check.issue_date))
        if check.due_date:
            self.date_due.set_jalali_date_text(normalize_jalali_date_text(check.due_date))

        status_key = (check.status or "").upper()
        status_index = self.cmb_status.findData(status_key)
        if status_index < 0:
            status_index = self.cmb_status.findText(check.status)
        if status_index >= 0:
            self.cmb_status.setCurrentIndex(status_index)

        self.txt_notes.setPlainText(check.notes or "")

    def accept(self) -> None:
        errors = self._validate_form()
        if errors:
            for widget in self._validation_widgets():
                if widget.property('invalid'):
                    widget.setFocus(Qt.OtherFocusReason)
                    break
            QMessageBox.warning(self, "خطای اعتبارسنجی", "\n".join(errors))
            return
        super().accept()

    def get_check(self) -> Check:
        """Build a validated check object from current form inputs."""

        amount = int(self.edt_amount.text().replace(",", "").strip() or "0")
        return Check(
            id=None,
            serial_18=self.edt_serial_18.text().strip(),
            serial_7=self.edt_serial_7.text(),
            registrant_name=self.edt_registrant_name.text().strip(),
            bank_name=self.edt_bank.text().strip(),
            account_owner=self.edt_owner.text().strip(),
            amount=amount,
            issue_date=self.date_issue.jalali_text_date(),
            due_date=self.date_due.jalali_text_date(),
            payee_name=self.edt_payee.text().strip(),
            status=self.cmb_status.currentData() or "PENDING",
            notes=self.txt_notes.toPlainText().strip(),
        )

    def _validate_form(self) -> list[str]:
        errors: list[str] = []
        reset_invalid(self._validation_widgets())

        serial_18 = self.edt_serial_18.text().strip()
        serial_7 = self.edt_serial_7.text()
        registrant_name = self.edt_registrant_name.text().strip()
        bank_name = self.edt_bank.text().strip()
        account_owner = self.edt_owner.text().strip()
        amount_text = self.edt_amount.text().replace(",", "").strip()
        issue_date = self.date_issue.jalali_text_date()
        due_date = self.date_due.jalali_text_date()

        if not (serial_18.isdigit() and len(serial_18) == 16):
            errors.append("شماره صیادی چک باید دقیقا 16 رقم باشد.")
            set_invalid(self.edt_serial_18, True)

        if not serial_7.strip():
            errors.append("شماره سریال چک الزامی است.")
            set_invalid(self.edt_serial_7, True)

        if not self._is_alpha_name(registrant_name):
            errors.append("نام ثبتنام کننده فقط باید شامل حروف فارسی یا انگلیسی باشد.")
            set_invalid(self.edt_registrant_name, True)

        if not self._is_alpha_name(bank_name):
            errors.append("نام بانک فقط باید شامل حروف فارسی یا انگلیسی باشد.")
            set_invalid(self.edt_bank, True)

        if not self._is_alpha_name(account_owner):
            errors.append("نام صاحب حساب فقط باید شامل حروف فارسی یا انگلیسی باشد.")
            set_invalid(self.edt_owner, True)

        if not amount_text.isdigit() or int(amount_text) <= 0:
            errors.append("مبلغ باید عددی و بزرگ تر از صفر باشد.")
            set_invalid(self.edt_amount, True)

        if issue_date and not is_valid_jalali_date_text(issue_date):
            errors.append("تاریخ صدور باید در قالب YYYY/MM/DD و معتبر باشد.")
            set_invalid(self.date_issue, True)

        if due_date and not is_valid_jalali_date_text(due_date):
            errors.append("تاریخ سررسید باید در قالب YYYY/MM/DD و معتبر باشد.")
            set_invalid(self.date_due, True)

        if issue_date and due_date and is_valid_jalali_date_text(issue_date) and is_valid_jalali_date_text(due_date):
            issue_g = jalali_to_gregorian(issue_date)
            due_g = jalali_to_gregorian(due_date)
            if due_g < issue_g:
                errors.append("تاریخ سررسید نباید قبل از تاریخ صدور باشد.")
                set_invalid(self.date_due, True)

        return errors

    def _validation_widgets(self) -> list[QWidget]:
        return [
            self.edt_serial_18,
            self.edt_serial_7,
            self.edt_registrant_name,
            self.edt_bank,
            self.edt_owner,
            self.edt_amount,
            self.date_issue,
            self.date_due,
        ]

    @staticmethod
    def _is_alpha_name(value: str) -> bool:
        cleaned = value.strip()
        return bool(cleaned) and all(char.isalpha() or char.isspace() for char in cleaned)
