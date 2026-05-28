from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.expense_service import ExpenseService
from services.export_service import ExportService
from services.registration_service import RegistrationService
from ui.add_registration_dialog import AddRegistrationDialog
from ui.registration_payments_dialog import RegistrationPaymentsDialog


class RegistrationsPage(QWidget):
    registrationsChanged = Signal()

    def __init__(
        self,
        registration_service: RegistrationService,
        expense_service: ExpenseService,
        export_service: ExportService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.registration_service = registration_service
        self.expense_service = expense_service
        self.export_service = export_service
        self._registrations = []
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
        title = QLabel('مدیریت ثبت نام و درآمد')
        title.setObjectName('pageTitle')
        subtitle = QLabel('ثبت نام هنرجو، لینک چک ها و مدیریت ورود نقدی در یک صفحه')
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

        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)
        self.metric_values['registrations'] = self._create_summary_card(
            metrics_layout, 'تعداد ثبت نام', '0', 'تعداد کل ثبت نام های ذخیره شده'
        )
        self.metric_values['income'] = self._create_summary_card(
            metrics_layout, 'مجموع درآمد', '0', 'جمع مبالغ ثبت شده در جدول پرداخت ها'
        )
        self.metric_values['expenses'] = self._create_summary_card(
            metrics_layout, 'مجموع هزینه ها', '0', 'کل هزینه های ثبت شده در سیستم'
        )
        self.metric_values['net'] = self._create_summary_card(
            metrics_layout, 'خالص درآمد', '0', 'مجموع درآمد منهای هزینه ها'
        )
        page_layout.addLayout(metrics_layout)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText('جستجو بر اساس نام، کد ملی، شماره تماس، دوره یا توضیحات')
        self.search_input.textChanged.connect(self.refresh)
        controls_layout.addWidget(self.search_input, 1)

        self.btn_add = QPushButton('ثبت نام جدید')
        self.btn_payments = QPushButton('سوابق پرداخت')
        self.btn_edit = QPushButton('ویرایش')
        self.btn_delete = QPushButton('حذف')
        self.btn_export = QPushButton('خروجی اکسل')
        controls_layout.addWidget(self.btn_add)
        controls_layout.addWidget(self.btn_payments)
        controls_layout.addWidget(self.btn_edit)
        controls_layout.addWidget(self.btn_delete)
        controls_layout.addWidget(self.btn_export)
        page_layout.addLayout(controls_layout)

        self.result_hint = QLabel('نمایش تمام ثبت نام ها')
        self.result_hint.setObjectName('dashboardHintBadge')
        page_layout.addWidget(self.result_hint)

        self.table = QTableWidget(0, 14, self)
        self.table.setObjectName('dashboardTable')
        self.table.setHorizontalHeaderLabels(
            [
                'شناسه',
                'نام',
                'کد ملی',
                'تماس',
                'دوره',
                'تاریخ',
                'شهریه کل',
                'پرداخت اولیه',
                'روش پرداخت',
                'درآمد ثبت شده',
                'مانده',
                'تفکیک پرداخت',
                'وضعیت مالی',
                'توضیحات',
            ]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.itemDoubleClicked.connect(lambda *_: self._edit_registration())
        page_layout.addWidget(self.table, 1)

        self.btn_add.clicked.connect(self._add_registration)
        self.btn_payments.clicked.connect(self._show_payment_history)
        self.btn_edit.clicked.connect(self._edit_registration)
        self.btn_delete.clicked.connect(self._delete_registration)
        self.btn_export.clicked.connect(self._export_registrations)

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
        search_text = self.search_input.text().strip()
        self._registrations = self.registration_service.list_all(search_text=search_text)
        self._fill_table()
        self._refresh_metrics()
        if search_text:
            self.result_hint.setText(f'{len(self._registrations)} نتیجه برای "{search_text}"')
        else:
            self.result_hint.setText(f'نمایش {len(self._registrations)} ثبت نام')

    def _fill_table(self):
        self.table.setUpdatesEnabled(False)
        try:
            self.table.clearContents()
            self.table.setRowCount(len(self._registrations))

            for row_index, registration in enumerate(self._registrations):
                values = [
                    str(registration.id or ''),
                    registration.customer_name or '-',
                    registration.national_code or '-',
                    registration.phone or '-',
                    registration.course_name or '-',
                    registration.registration_date or '-',
                    f"{int(registration.total_fee or 0):,}",
                    f"{int(getattr(registration, 'initial_payment', 0) or 0):,}",
                    self.registration_service.PAYMENT_METHOD_LABELS.get(
                        (registration.payment_method or '').upper(),
                        registration.payment_method or '-',
                    ),
                    f"{int(registration.income_total or 0):,}",
                    f"{self._remaining_balance(registration):,}",
                    self._payment_breakdown_label(registration),
                    self._financial_status_label(registration),
                    registration.description or '',
                ]

                for column_index, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column_index in {0, 6, 7, 9, 10, 11}:
                        item.setTextAlignment(Qt.AlignCenter)
                    if column_index == 12:
                        remaining = self._remaining_balance(registration)
                        if remaining > 0:
                            item.setBackground(QColor('#fef3c7'))
                        else:
                            item.setBackground(QColor('#dcfce7'))
                    self.table.setItem(row_index, column_index, item)

            self.table.resizeColumnsToContents()
        finally:
            self.table.setUpdatesEnabled(True)

    def _refresh_metrics(self):
        financials = self.registration_service.build_financial_report()
        total_income = int(financials.get('total_income', 0))
        total_expenses = int(financials.get('total_expenses', 0))
        net_income = int(financials.get('net_income', 0))

        self.metric_values['registrations'].setText(str(len(self._registrations)))
        self.metric_values['income'].setText(f'{total_income:,}')
        self.metric_values['expenses'].setText(f'{total_expenses:,}')
        self.metric_values['net'].setText(f'{net_income:,}')

        if net_income >= 0:
            self.metric_values['net'].setStyleSheet('color: #15803d;')
        else:
            self.metric_values['net'].setStyleSheet('color: #b91c1c;')

    def _selected_registration(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._registrations):
            return None
        return self._registrations[row]

    @staticmethod
    def _financial_status_label(registration) -> str:
        remaining = RegistrationsPage._remaining_balance(registration)
        if remaining == 0:
            return 'تسویه کامل'
        if remaining < 0:
            return f'مازاد {abs(remaining):,}'
        return f'کسری {remaining:,}'

    @staticmethod
    def _payment_breakdown_label(registration) -> str:
        check_amount = int(getattr(registration, 'check_income_total', 0) or 0)
        non_check_amount = int(getattr(registration, 'non_check_income_total', 0) or 0)
        return f'چک {check_amount:,} | غیرچکی {non_check_amount:,}'

    @staticmethod
    def _remaining_balance(registration) -> int:
        total_fee = int(getattr(registration, 'total_fee', 0) or 0)
        initial_payment = int(getattr(registration, 'initial_payment', 0) or 0)
        checks_total = int(getattr(registration, 'check_income_total', 0) or 0)
        return total_fee - initial_payment - checks_total

    def _add_registration(self):
        dialog = AddRegistrationDialog(self.registration_service.db, parent=self)
        if not dialog.exec():
            return
        self.refresh()
        self.registrationsChanged.emit()

    def trigger_add_registration(self):
        self._add_registration()

    def trigger_edit_registration(self):
        self._edit_registration()

    def trigger_delete_registration(self):
        self._delete_registration()

    def _show_payment_history(self):
        registration = self._selected_registration()
        if registration is None:
            QMessageBox.information(self, 'سوابق پرداخت', 'ابتدا یک ثبت نام را انتخاب کنید.')
            return
        dialog = RegistrationPaymentsDialog(self.registration_service, registration, self)
        dialog.exec()

    def _edit_registration(self):
        registration = self._selected_registration()
        if registration is None:
            QMessageBox.information(self, 'ویرایش ثبت نام', 'ابتدا یک رکورد ثبت نام را انتخاب کنید.')
            return

        dialog = AddRegistrationDialog(self.registration_service.db, registration=registration, parent=self)
        if not dialog.exec():
            return
        self.refresh()
        self.registrationsChanged.emit()

    def _export_registrations(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            'محل ذخیره خروجی ثبت نام و درآمد',
            '',
            'Excel Files (*.xlsx)',
        )
        if not file_path:
            return

        try:
            result = self.export_service.export_registrations_to_excel(
                file_path=file_path,
                search_text=self.search_input.text().strip(),
            )
        except Exception as exc:
            QMessageBox.warning(self, 'خروجی اکسل', str(exc))
            return

        QMessageBox.information(self, 'خروجی اکسل', f'فایل خروجی با موفقیت ذخیره شد\n{result}')

    def trigger_export_registrations(self):
        self._export_registrations()

    def _delete_registration(self):
        registration = self._selected_registration()
        if registration is None:
            QMessageBox.information(self, 'حذف ثبت نام', 'ابتدا یک رکورد ثبت نام را انتخاب کنید.')
            return

        answer = QMessageBox.question(
            self,
            'حذف ثبت نام',
            f'ثبت نام شماره {registration.id} حذف شود؟',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            self.registration_service.delete(int(registration.id or 0))
        except Exception as exc:
            QMessageBox.warning(self, 'حذف ثبت نام', str(exc))
            return

        self.refresh()
        self.registrationsChanged.emit()
