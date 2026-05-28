from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.registration_model import Registration
from services.registration_service import RegistrationService


class RegistrationPaymentsDialog(QDialog):
    def __init__(
        self,
        registration_service: RegistrationService,
        registration: Registration,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.registration_service = registration_service
        self.registration = registration

        self.setObjectName('appFormDialog')
        self.setWindowTitle(f'سوابق پرداخت ثبت نام #{registration.id}')
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(760, 520)

        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 14, 16, 12)
        root_layout.setSpacing(12)

        header_panel = QFrame(self)
        header_panel.setObjectName('dialogHeaderPanel')
        header_layout = QVBoxLayout(header_panel)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(4)

        title = QLabel(f'ریز پرداخت های ثبت نام "{self.registration.customer_name}"')
        title.setObjectName('formDialogTitle')
        subtitle = QLabel(
            f'دوره: {self.registration.course_name} | تاریخ: {self.registration.registration_date}'
        )
        subtitle.setObjectName('formDialogSubtitle')
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root_layout.addWidget(header_panel)

        metrics_layout = QHBoxLayout()
        self.lbl_total_fee = QLabel('شهریه: 0')
        self.lbl_check_total = QLabel('مجموع چک: 0')
        self.lbl_non_check_total = QLabel('مجموع غیرچکی: 0')
        self.lbl_income_total = QLabel('درآمد ثبت شده: 0')
        self.lbl_remaining = QLabel('مانده: 0')
        for widget in (
            self.lbl_total_fee,
            self.lbl_check_total,
            self.lbl_non_check_total,
            self.lbl_income_total,
            self.lbl_remaining,
        ):
            widget.setObjectName('dashboardHintBadge')
            metrics_layout.addWidget(widget)
        metrics_layout.addStretch()
        root_layout.addLayout(metrics_layout)

        self.table = QTableWidget(0, 7, self)
        self.table.setObjectName('dashboardTable')
        self.table.setHorizontalHeaderLabels(
            [
                'شناسه پرداخت',
                'روش',
                'مبلغ (ریال)',
                'تاریخ',
                'شناسه چک',
                'سریال چک',
                'توضیحات',
            ]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        root_layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        btn_close = QPushButton('بستن')
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        root_layout.addLayout(footer)

    def _load_data(self):
        payments = self.registration_service.list_payments(int(self.registration.id or 0))

        self.table.clearContents()
        self.table.setRowCount(len(payments))

        income_total = 0
        check_total = 0
        non_check_total = 0
        for row_index, payment in enumerate(payments):
            payment_method = str(payment['payment_method'] or '').upper()
            amount = int(payment['amount'] or 0)
            income_total += amount

            if payment_method == 'CHECK':
                method_label = 'چک'
                check_total += amount
            else:
                registration_method = str(
                    payment['registration_payment_method'] or self.registration.payment_method
                ).upper()
                rendered_method = self.registration_service.PAYMENT_METHOD_LABELS.get(
                    registration_method,
                    'غیرچکی',
                )
                method_label = f'غیرچکی ({rendered_method})'
                non_check_total += amount

            values = [
                str(int(payment['id'] or 0)),
                method_label,
                f'{amount:,}',
                payment['payment_date'] or '-',
                str(payment['check_id'] or '-'),
                payment['serial_7'] or '-',
                payment['notes'] or '',
            ]

            for col_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col_index in {0, 2, 4}:
                    item.setTextAlignment(Qt.AlignCenter)
                if payment_method == 'CHECK':
                    item.setBackground(QColor('#f8fafc'))
                self.table.setItem(row_index, col_index, item)

        self.table.resizeColumnsToContents()

        total_fee = int(self.registration.total_fee or 0)
        remaining = total_fee - income_total
        self.lbl_total_fee.setText(f'شهریه: {total_fee:,}')
        self.lbl_check_total.setText(f'مجموع چک: {check_total:,}')
        self.lbl_non_check_total.setText(f'مجموع غیرچکی: {non_check_total:,}')
        self.lbl_income_total.setText(f'درآمد ثبت شده: {income_total:,}')
        self.lbl_remaining.setText(f'مانده: {remaining:,}')

        if remaining <= 0:
            self.lbl_remaining.setStyleSheet('color: #15803d;')
        else:
            self.lbl_remaining.setStyleSheet('color: #b45309;')
