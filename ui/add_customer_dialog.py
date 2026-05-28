from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QScrollArea, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QRegularExpressionValidator, QRegularExpression
from check_manager.services.customer_service import CustomerService
from check_manager.models.customer import Customer

class AddCustomerDialog(QDialog):
    def __init__(self, db, customer: Customer = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ثبت / ویرایش مشتری")
        self.service = CustomerService(db)
        self.edit_mode = customer is not None
        self.customer = customer

        self._build_ui()

        if self.edit_mode:
            self._load_data()

    # --------------------- UI ---------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QVBoxLayout(content)

        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.national_code_input = QLineEdit()
        self.notes_input = QLineEdit()

        # ولیدیشن نام
        name_validator = QRegularExpressionValidator(
            QRegularExpression(r"[آ-یA-Za-z\s]+")
        )
        self.name_input.setValidator(name_validator)

        # ولیدیشن موبایل
        phone_validator = QRegularExpressionValidator(
            QRegularExpression(r"^(09\d{9})?$")
        )
        self.phone_input.setValidator(phone_validator)

        # ولیدیشن کدملی
        nc_validator = QRegularExpressionValidator(
            QRegularExpression(r"^\d{10}$")
        )
        self.national_code_input.setValidator(nc_validator)

        form.addWidget(QLabel("نام مشتری"))
        form.addWidget(self.name_input)

        form.addWidget(QLabel("شماره موبایل"))
        form.addWidget(self.phone_input)

        form.addWidget(QLabel("کد ملی"))
        form.addWidget(self.national_code_input)

        form.addWidget(QLabel("توضیحات"))
        form.addWidget(self.notes_input)

        content.setLayout(form)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Buttons
        btns = QHBoxLayout()
        save = QPushButton("ذخیره")
        cancel = QPushButton("انصراف")

        save.clicked.connect(self._on_save)
        cancel.clicked.connect(self.reject)

        btns.addWidget(save)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    # --------------------- Load Data ---------------------
    def _load_data(self):
        self.name_input.setText(self.customer.name)
        self.phone_input.setText(self.customer.phone)
        self.national_code_input.setText(self.customer.national_code)
        self.notes_input.setText(self.customer.notes)

    # --------------------- Validation ---------------------
    def _validate(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "خطا", "نام مشتری وارد نشده است.")
            return False

        return True

    # --------------------- Save ---------------------
    def _on_save(self):
        if not self._validate():
            return

        model = self.get_data()

        if self.edit_mode:
            model.id = self.customer.id
            self.service.update(model)
        else:
            self.service.create(model)

        self.accept()

    # --------------------- get_data ---------------------
    def get_data(self) -> Customer:
        return Customer(
            id=None,
            name=self.name_input.text().strip(),
            phone=self.phone_input.text().strip(),
            national_code=self.national_code_input.text().strip(),
            notes=self.notes_input.text().strip()
        )
