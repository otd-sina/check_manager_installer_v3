from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QWidget, QComboBox, QMessageBox
)
from PySide6.QtGui import QIntValidator
from check_manager.services.registration_service import RegistrationService
from check_manager.services.payment_service import PaymentService
from check_manager.models.payment import Payment
from check_manager.ui.widgets.jalali_datepicker import JalaliDatePicker

class AddPaymentDialog(QDialog):
    def __init__(self, db, registration_id=None, payment: Payment=None):
        super().__init__()
        self.service = PaymentService(db)
        self.reg_service = RegistrationService(db)
        self.payment = payment
        self.registration_id = registration_id
        self.edit_mode = payment is not None

        self.setWindowTitle("ثبت / ویرایش پرداخت")
        self._build_ui()

        if self.edit_mode:
            self._load_data()

    # --------------------- UI ---------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        v = QVBoxLayout(content)

        # اگر از صفحه ثبت‌نام فراخوانی شد — combo نمایش نده
        self.registration_combo = QComboBox()
        regs = self.reg_service.list_by_customer(1)  # امکان توسعه
        self._reg_map = {f"Reg #{r.id} - {r.course_name}": r.id for r in regs}

        if self.registration_id is None:
            for k in self._reg_map.keys():
                self.registration_combo.addItem(k)
        else:
            self.registration_combo.hide()

        self.amount = QLineEdit()
        self.amount.setValidator(QIntValidator(0, 999999999))

        self.method_combo = QComboBox()
        methods = ["CASH", "CARD", "CHEQUE", "TRANSFER", "ONLINE", "OTHER"]
        self.method_combo.addItems(methods)

        self.check_id_input = QLineEdit()
        self.check_id_input.setValidator(QIntValidator(1, 99999999))

        self.date_picker = JalaliDatePicker()

        self.notes = QLineEdit()

        v.addWidget(QLabel("مبلغ پرداخت"))
        v.addWidget(self.amount)

        v.addWidget(QLabel("روش پرداخت"))
        v.addWidget(self.method_combo)

        v.addWidget(QLabel("شناسه چک (اختیاری)"))
        v.addWidget(self.check_id_input)

        v.addWidget(QLabel("تاریخ پرداخت"))
        v.addWidget(self.date_picker)

        v.addWidget(QLabel("توضیحات"))
        v.addWidget(self.notes)

        content.setLayout(v)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        btns = QHBoxLayout()
        save = QPushButton("ذخیره")
        cancel = QPushButton("انصراف")

        save.clicked.connect(self._on_save)
        cancel.clicked.connect(self.reject)

        btns.addWidget(save)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    # --------------------- Load ---------------------
    def _load_data(self):
        if self.registration_id is None:
            for k, rid in self._reg_map.items():
                if rid == self.payment.registration_id:
                    self.registration_combo.setCurrentText(k)
                    break

        self.amount.setText(str(self.payment.amount))
        self.method_combo.setCurrentText(self.payment.payment_method)
        self.check_id_input.setText(str(self.payment.check_id or ""))
        self.date_picker.set_jalali(self.payment.payment_date)
        self.notes.setText(self.payment.notes)

    # --------------------- Validation ---------------------
    def _validate(self):
        if not self.amount.text().strip():
            QMessageBox.warning(self, "خطا", "مبلغ پرداخت وارد نشده است.")
            return False
        return True

    # --------------------- Save ---------------------
    def _on_save(self):
        if not self._validate():
            return

        model = self.get_data()

        if self.edit_mode:
            model.id = self.payment.id
            self.service.update(model)
        else:
            self.service.create(model)

        self.accept()

    # --------------------- get_data ---------------------
    def get_data(self) -> Payment:
        reg_id = (
            self.registration_id
            if self.registration_id is not None
            else self._reg_map[self.registration_combo.currentText()]
        )

        return Payment(
            id=None,
            registration_id=reg_id,
            amount=int(self.amount.text()),
            payment_method=self.method_combo.currentText(),
            payment_date=self.date_picker.get_iso_date(),
            check_id=int(self.check_id_input.text()) if self.check_id_input.text() else None,
            notes=self.notes.text().strip()
        )
