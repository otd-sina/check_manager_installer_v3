from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtCore import QRegularExpression

from models.registration_model import Registration
from services.registration_service import RegistrationService
from ui.form_validation import reset_invalid, set_invalid
from widgets.jalali_date_picker import JalaliDatePicker


PAYMENT_METHODS = [
    ('CASH', 'نقدی'),
    ('CARD', 'کارت'),
    ('TRANSFER', 'انتقال'),
    ('CHECK', 'چک'),
]


class AddRegistrationDialog(QDialog):
    def __init__(self, db, registration: Registration | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.registration_service = RegistrationService(db)
        self.registration = registration

        self.setObjectName('appFormDialog')
        self.setWindowTitle('ثبت درآمد / ثبت نام')
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(620, 760)
        self._build_ui()
        self._load_available_checks(self.registration.id if self.registration is not None else None)

        if self.registration is not None:
            self._load_registration()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(12)

        header_panel = QFrame(self)
        header_panel.setObjectName('dialogHeaderPanel')
        header_layout = QVBoxLayout(header_panel)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(2)

        title = QLabel('فرم ثبت نام و درآمد')
        title.setObjectName('formDialogTitle')
        subtitle = QLabel('مشخصات هنرجو و روش پرداخت را ثبت کنید تا درآمد به صورت خودکار در گزارش مالی اعمال شود.')
        subtitle.setObjectName('formDialogSubtitle')
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header_panel)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        form_container = QWidget(self)
        form_container.setObjectName('formCard')
        form_layout = QFormLayout(form_container)
        form_layout.setContentsMargins(14, 12, 14, 12)
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setFormAlignment(Qt.AlignTop | Qt.AlignRight)
        form_layout.setSpacing(12)

        self.name_input = QLineEdit()
        self.name_input.setMaxLength(120)

        self.national_id_input = QLineEdit()
        self.national_id_input.setMaxLength(10)
        self.national_id_input.setValidator(QRegularExpressionValidator(QRegularExpression(r'\d{0,10}'), self))

        self.phone_input = QLineEdit()
        self.phone_input.setMaxLength(11)
        self.phone_input.setValidator(QRegularExpressionValidator(QRegularExpression(r'\d{0,11}'), self))

        self.course_input = QLineEdit()
        self.course_input.setMaxLength(120)

        self.date_picker = JalaliDatePicker()

        self.total_fee_input = QLineEdit()
        self.total_fee_input.setValidator(QRegularExpressionValidator(QRegularExpression(r'[\d,]*'), self))
        self.total_fee_input.textChanged.connect(self._format_amount_with_commas)

        self.initial_payment_input = QLineEdit()
        self.initial_payment_input.setValidator(QRegularExpressionValidator(QRegularExpression(r'[\d,]*'), self))
        self.initial_payment_input.setText('0')
        self.initial_payment_input.textChanged.connect(self._format_initial_payment_with_commas)

        self.payment_method_combo = QComboBox()
        for key, label in PAYMENT_METHODS:
            self.payment_method_combo.addItem(label, key)

        self.checks_title = QLabel('اتصال چک‌ها')
        self.checks_title.setObjectName('formSectionTitle')
        self.checks_list = QListWidget()
        self.checks_list.setSelectionMode(QListWidget.MultiSelection)
        self.checks_list.itemSelectionChanged.connect(self._update_selected_checks_summary)
        self.selected_checks_summary = QLabel('چک انتخاب نشده است.')
        self.selected_checks_summary.setObjectName('dashboardHintBadge')
        self.remaining_amount_summary = QLabel('مانده غیرچکی: 0 ریال')
        self.remaining_amount_summary.setObjectName('dashboardHintBadge')
        self.payment_breakdown_summary = QLabel('ترکیب پرداخت: 0 (چک) + 0 (غیرچکی)')
        self.payment_breakdown_summary.setObjectName('dashboardHintBadge')

        self.description_input = QTextEdit()
        self.description_input.setFixedHeight(110)

        form_layout.addRow(QLabel('نام و نام خانوادگی*'), self.name_input)
        form_layout.addRow(QLabel('کد ملی*'), self.national_id_input)
        form_layout.addRow(QLabel('شماره تماس*'), self.phone_input)
        form_layout.addRow(QLabel('دوره*'), self.course_input)
        form_layout.addRow(QLabel('تاریخ ثبت نام*'), self.date_picker)
        form_layout.addRow(QLabel('شهریه کل (ریال)*'), self.total_fee_input)
        form_layout.addRow(QLabel('پرداخت اولیه (ریال)'), self.initial_payment_input)
        form_layout.addRow(QLabel('روش پرداخت'), self.payment_method_combo)
        form_layout.addRow(self.checks_title)
        form_layout.addRow(QLabel('لیست چک های قابل لینک'), self.checks_list)
        form_layout.addRow(QLabel('خلاصه چک های انتخابی'), self.selected_checks_summary)
        form_layout.addRow(QLabel('مانده قابل پرداخت غیرچکی'), self.remaining_amount_summary)
        form_layout.addRow(QLabel('ترکیب نهایی پرداخت'), self.payment_breakdown_summary)
        form_layout.addRow(QLabel('توضیحات'), self.description_input)

        scroll.setWidget(form_container)
        layout.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        save_btn = QPushButton('ذخیره')
        cancel_btn = QPushButton('انصراف')
        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        self._invalid_targets = [
            self.name_input,
            self.national_id_input,
            self.phone_input,
            self.course_input,
            self.total_fee_input,
            self.initial_payment_input,
            self.payment_method_combo,
            self.checks_list,
        ]

        self._update_selected_checks_summary()

    def _load_registration(self):
        if self.registration is None:
            return

        self.name_input.setText(self.registration.customer_name or self.name_input.text())
        self.national_id_input.setText(self.registration.national_code or self.national_id_input.text())
        self.phone_input.setText(self.registration.phone or self.phone_input.text())
        self.course_input.setText(self.registration.course_name or '')
        if self.registration.registration_date:
            self.date_picker.set_jalali_date_text(self.registration.registration_date)
        self.total_fee_input.setText(f"{int(self.registration.total_fee or 0):,}")
        self.initial_payment_input.setText(f"{int(self.registration.initial_payment or 0):,}")
        self.description_input.setPlainText(self.registration.description or '')

        method_index = self.payment_method_combo.findData((self.registration.payment_method or 'CASH').upper())
        if method_index >= 0:
            self.payment_method_combo.setCurrentIndex(method_index)

        selected_check_ids = set(self.registration_service.list_selected_check_ids(int(self.registration.id or 0)))
        for row in range(self.checks_list.count()):
            item = self.checks_list.item(row)
            payload = item.data(Qt.UserRole) or {}
            if int(payload.get('id') or 0) in selected_check_ids:
                item.setSelected(True)
        self._update_selected_checks_summary()

    def _load_available_checks(self, registration_id: int | None = None):
        self.checks_list.clear()
        checks = self.registration_service.list_available_checks(registration_id=registration_id)
        for check in checks:
            item = QListWidgetItem(
                f"#{check.id} | سریال {check.serial_7} | {check.amount:,} | سررسید {check.due_date}"
            )
            item.setData(Qt.UserRole, {'id': check.id, 'amount': int(check.amount or 0)})
            self.checks_list.addItem(item)
        self._update_selected_checks_summary()

    def _selected_check_ids(self) -> list[int]:
        selected_ids: list[int] = []
        for item in self.checks_list.selectedItems():
            payload = item.data(Qt.UserRole) or {}
            check_id = int(payload.get('id') or 0)
            if check_id > 0:
                selected_ids.append(check_id)
        return selected_ids

    def _selected_checks_total(self) -> int:
        total = 0
        for item in self.checks_list.selectedItems():
            payload = item.data(Qt.UserRole) or {}
            total += int(payload.get('amount') or 0)
        return total

    def _current_total_fee(self) -> int:
        fee_text = self.total_fee_input.text().replace(',', '').strip()
        if not fee_text.isdigit():
            return 0
        return int(fee_text)

    def _update_selected_checks_summary(self):
        selected_count = len(self.checks_list.selectedItems())
        selected_total = self._selected_checks_total()
        total_fee = self._current_total_fee()
        initial_payment = self._current_initial_payment()
        remaining_amount = total_fee - (selected_total + initial_payment)
        safe_remaining = max(remaining_amount, 0)

        self.selected_checks_summary.setText(
            f'تعداد چک انتخابی: {selected_count} | مجموع: {selected_total:,} ریال'
        )
        if remaining_amount < 0:
            self.selected_checks_summary.setStyleSheet('color: #b91c1c;')
        else:
            self.selected_checks_summary.setStyleSheet('')

        self.remaining_amount_summary.setText(
            f'مانده غیرچکی: {safe_remaining:,} ریال'
        )
        self.payment_breakdown_summary.setText(
            f'ترکیب پرداخت: {selected_total:,} (چک) + {initial_payment:,} (اولیه) | مانده {safe_remaining:,}'
        )

        if remaining_amount < 0:
            self.remaining_amount_summary.setStyleSheet('color: #b91c1c;')
            self.payment_breakdown_summary.setStyleSheet('color: #b91c1c;')
        else:
            self.remaining_amount_summary.setStyleSheet('')
            self.payment_breakdown_summary.setStyleSheet('')

    def _format_amount_with_commas(self, text: str):
        digits_only = ''.join(ch for ch in text if ch.isdigit())
        formatted = f'{int(digits_only):,}' if digits_only else ''

        self.total_fee_input.blockSignals(True)
        self.total_fee_input.setText(formatted)
        self.total_fee_input.setCursorPosition(len(formatted))
        self.total_fee_input.blockSignals(False)
        self._update_selected_checks_summary()

    def _format_initial_payment_with_commas(self, text: str):
        digits_only = ''.join(ch for ch in text if ch.isdigit())
        formatted = f'{int(digits_only):,}' if digits_only else '0'

        self.initial_payment_input.blockSignals(True)
        self.initial_payment_input.setText(formatted)
        self.initial_payment_input.setCursorPosition(len(formatted))
        self.initial_payment_input.blockSignals(False)
        self._update_selected_checks_summary()

    def _current_initial_payment(self) -> int:
        payment_text = self.initial_payment_input.text().replace(',', '').strip()
        if not payment_text.isdigit():
            return 0
        return int(payment_text)

    def _validate(self) -> bool:
        reset_invalid(self._invalid_targets)
        valid = True

        def fail(widget):
            nonlocal valid
            set_invalid(widget, True)
            valid = False

        name = self.name_input.text().strip()
        if not name:
            fail(self.name_input)

        national_id = self.national_id_input.text().strip()
        if not (national_id.isdigit() and len(national_id) == 10):
            fail(self.national_id_input)

        phone = self.phone_input.text().strip()
        if not (phone.isdigit() and len(phone) >= 10):
            fail(self.phone_input)

        if not self.course_input.text().strip():
            fail(self.course_input)

        fee_text = self.total_fee_input.text().replace(',', '').strip()
        if not fee_text.isdigit() or int(fee_text) <= 0:
            fail(self.total_fee_input)
        initial_payment_text = self.initial_payment_input.text().replace(',', '').strip()
        if not initial_payment_text.isdigit():
            fail(self.initial_payment_input)

        method = self.payment_method_combo.currentData()
        if method is None:
            fail(self.payment_method_combo)
        selected_total = self._selected_checks_total()
        total_fee = int(fee_text) if fee_text.isdigit() else 0
        initial_payment = int(initial_payment_text) if initial_payment_text.isdigit() else 0
        if initial_payment > total_fee:
            fail(self.initial_payment_input)
        if selected_total + initial_payment > total_fee:
            fail(self.total_fee_input)
            fail(self.initial_payment_input)
            fail(self.checks_list)

        if not valid:
            QMessageBox.warning(self, 'خطا', 'لطفاً فیلدهای مشخص شده را صحیح تکمیل کنید.')
            return False

        return True

    def _on_save(self):
        if not self._validate():
            return

        try:
            model = Registration(
                id=self.registration.id if self.registration is not None else None,
                customer_name=self.name_input.text().strip(),
                national_code=self.national_id_input.text().strip(),
                phone=self.phone_input.text().strip(),
                course_name=self.course_input.text().strip(),
                registration_date=self.date_picker.jalali_text_date(),
                total_fee=int(self.total_fee_input.text().replace(',', '').strip()),
                initial_payment=int(self.initial_payment_input.text().replace(',', '').strip() or 0),
                payment_method=str(self.payment_method_combo.currentData()),
                description=self.description_input.toPlainText().strip(),
            )

            if model.id is None:
                self.registration_service.create(model, selected_check_ids=self._selected_check_ids())
            else:
                self.registration_service.update(model, selected_check_ids=self._selected_check_ids())
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self, 'خطا در ذخیره', str(exc))
