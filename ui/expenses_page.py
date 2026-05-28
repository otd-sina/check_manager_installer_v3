from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)

from services.expense_service import ExpenseService
from services.export_service import ExportService
from ui.add_expense_dialog import AddExpenseDialog
from ui.expenses_table_widget import ExpensesTableWidget
from ui.manage_expense_categories_dialog import ManageExpenseCategoriesDialog
from utils.date_utils import today_jalali


class ExpensesPage(QWidget):
    expensesChanged = Signal()

    def __init__(
        self,
        expense_service: ExpenseService,
        export_service: ExportService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.expense_service = expense_service
        self.export_service = export_service
        self.metric_values: dict[str, QLabel] = {}

        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(20, 20, 20, 20)
        page_layout.setSpacing(12)

        header_panel = QFrame(self)
        header_panel.setObjectName('pageTopFixedPanel')
        header_panel_layout = QHBoxLayout(header_panel)
        header_panel_layout.setContentsMargins(18, 16, 18, 16)
        header_panel_layout.setSpacing(12)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)

        title = QLabel('مدیریت هزینه های روزانه')
        title.setObjectName('pageTitle')
        subtitle = QLabel('ثبت، دسته بندی و گزارش گیری یکپارچه برای هزینه ها')
        subtitle.setObjectName('pageSubtitle')
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        header_panel_layout.addLayout(header_layout, 1)

        self.btn_refresh = QPushButton('به روزرسانی گزارش')
        self.btn_refresh.setObjectName('dashboardRefreshButton')
        self.btn_refresh.clicked.connect(self.refresh)
        header_panel_layout.addWidget(self.btn_refresh)
        page_layout.addWidget(header_panel)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.verticalScrollBar().setSingleStep(18)
        page_layout.addWidget(scroll, 1)

        scroll_content = QWidget()
        root_layout = QVBoxLayout(scroll_content)
        root_layout.setContentsMargins(0, 0, 0, 6)
        root_layout.setSpacing(16)

        scroll.setWidget(scroll_content)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(14)
        self.metric_values['total'] = self._create_summary_card(
            cards_layout, 'مجموع هزینه های نمایش داده شده', '0', 'مجموع ریالی رکوردهای جدول فعلی'
        )
        self.metric_values['count'] = self._create_summary_card(
            cards_layout, 'تعداد رکوردها', '0', 'تعداد هزینه های منطبق با فیلترها'
        )
        self.metric_values['average'] = self._create_summary_card(
            cards_layout, 'میانگین هر هزینه', '0', 'میانگین مبلغ هر ثبت هزینه'
        )
        self.metric_values['max'] = self._create_summary_card(
            cards_layout, 'بیشترین هزینه', '0', 'بالاترین هزینه ثبت شده در نتایج'
        )
        root_layout.addLayout(cards_layout)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)
        self.btn_add = QPushButton('ثبت هزینه')
        self.btn_edit = QPushButton('ویرایش')
        self.btn_delete = QPushButton('حذف')
        self.btn_manage_categories = QPushButton('مدیریت دسته بندی')
        self.btn_export = QPushButton('خروجی اکسل')

        actions_layout.addWidget(self.btn_add)
        actions_layout.addWidget(self.btn_edit)
        actions_layout.addWidget(self.btn_delete)
        actions_layout.addStretch()
        actions_layout.addWidget(self.btn_manage_categories)
        actions_layout.addWidget(self.btn_export)
        root_layout.addLayout(actions_layout)

        self.expenses_table_widget = ExpensesTableWidget(self.expense_service)
        root_layout.addWidget(self.expenses_table_widget, 3)

        report_panel = QFrame()
        report_panel.setObjectName('dashboardPanel')
        report_layout = QVBoxLayout(report_panel)
        report_layout.setContentsMargins(18, 18, 18, 18)
        report_layout.setSpacing(10)
        report_panel.setMinimumHeight(220)

        report_title = QLabel('گزارش سریع هزینه ها')
        report_title.setObjectName('dashboardSectionTitle')
        report_layout.addWidget(report_title)

        meta_row = QHBoxLayout()
        self.lbl_today = QLabel('هزینه امروز: 0')
        self.lbl_month = QLabel('هزینه ماه جاری: 0')
        self.lbl_active_filter = QLabel('فیلتر فعال: همه')
        self.lbl_active_filter.setObjectName('dashboardHintBadge')
        meta_row.addWidget(self.lbl_today)
        meta_row.addWidget(self.lbl_month)
        meta_row.addStretch()
        meta_row.addWidget(self.lbl_active_filter)
        report_layout.addLayout(meta_row)

        tables_row = QHBoxLayout()
        tables_row.setSpacing(10)
        self.top_categories_table = self._create_report_table(
            ['دسته بندی', 'مجموع هزینه (ریال)']
        )
        self.payment_methods_table = self._create_report_table(
            ['روش پرداخت', 'مجموع هزینه (ریال)']
        )
        tables_row.addWidget(self.top_categories_table)
        tables_row.addWidget(self.payment_methods_table)
        report_layout.addLayout(tables_row)

        root_layout.addWidget(report_panel,1)

        self.btn_add.clicked.connect(self._add_expense)
        self.btn_edit.clicked.connect(self.expenses_table_widget.edit_selected)
        self.btn_delete.clicked.connect(self.expenses_table_widget.delete_selected)
        self.btn_manage_categories.clicked.connect(self._open_category_manager)
        self.btn_export.clicked.connect(self._export_expenses)

        self.expenses_table_widget.expensesChanged.connect(self._on_expenses_changed)
        self.expenses_table_widget.filtersChanged.connect(self._refresh_report_panels)

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

    def _create_report_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setObjectName('dashboardTable')
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def refresh(self):
        self.expenses_table_widget.refresh()
        self._refresh_report_panels()

    def _add_expense(self):
        dialog = AddExpenseDialog(self.expense_service, self)
        if not dialog.exec():
            return

        try:
            self.expense_service.add_expense(dialog.get_expense())
        except ValueError as exc:
            QMessageBox.warning(self, 'خطا', str(exc))
            return

        self.expenses_table_widget.refresh()
        self._on_expenses_changed()

    def trigger_add_expense(self):
        self._add_expense()

    def _open_category_manager(self):
        dialog = ManageExpenseCategoriesDialog(self.expense_service, self)
        dialog.exec()
        self.expenses_table_widget.refresh()
        self._refresh_report_panels()

    def _on_expenses_changed(self):
        self._refresh_report_panels()
        self.expensesChanged.emit()

    def _refresh_report_panels(self):
        expenses = self.expenses_table_widget.filtered_expenses()
        total_amount = sum(int(item.amount or 0) for item in expenses)
        count = len(expenses)
        average = int(total_amount / count) if count else 0
        max_amount = max([int(item.amount or 0) for item in expenses], default=0)

        self.metric_values['total'].setText(f'{total_amount:,}')
        self.metric_values['count'].setText(str(count))
        self.metric_values['average'].setText(f'{average:,}')
        self.metric_values['max'].setText(f'{max_amount:,}')

        today_text = today_jalali().strftime('%Y/%m/%d')
        month_prefix = today_text[:7]
        today_amount = sum(int(item.amount or 0) for item in expenses if item.expense_date == today_text)
        month_amount = sum(
            int(item.amount or 0)
            for item in expenses
            if (item.expense_date or '').startswith(month_prefix)
        )
        self.lbl_today.setText(f'هزینه امروز: {today_amount:,}')
        self.lbl_month.setText(f'هزینه ماه جاری: {month_amount:,}')

        active_filter = self._active_filter_label()
        self.lbl_active_filter.setText(f'فیلتر فعال: {active_filter}')

        category_totals: dict[str, int] = {}
        payment_totals: dict[str, int] = {}
        for item in expenses:
            category_totals[item.category_name] = category_totals.get(item.category_name, 0) + int(item.amount or 0)
            payment_label = ExpenseService.PAYMENT_METHODS.get(item.payment_method, item.payment_method)
            payment_totals[payment_label] = payment_totals.get(payment_label, 0) + int(item.amount or 0)

        top_categories = sorted(category_totals.items(), key=lambda pair: pair[1], reverse=True)[:5]
        top_methods = sorted(payment_totals.items(), key=lambda pair: pair[1], reverse=True)
        self._fill_report_table(self.top_categories_table, top_categories)
        self._fill_report_table(self.payment_methods_table, top_methods)

    def _fill_report_table(self, table: QTableWidget, rows: list[tuple[str, int]]):
        table.clearContents()
        table.setRowCount(len(rows))

        for row_index, (title, amount) in enumerate(rows):
            table.setItem(row_index, 0, QTableWidgetItem(title))
            amount_item = QTableWidgetItem(f'{int(amount):,}')
            amount_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row_index, 1, amount_item)

        table.resizeColumnsToContents()

    def _active_filter_label(self) -> str:
        filters = self.expenses_table_widget.current_filters()
        quick_map = {
            'all': 'همه',
            'today': 'امروز',
            'month': 'ماه جاری',
            'linked': 'دارای مرجع چک',
        }
        parts: list[str] = [quick_map.get(filters['quick_filter'], 'همه')]

        if filters['category_id'] is not None:
            category_name = self.expenses_table_widget.category_filter.currentText()
            parts.append(f'دسته: {category_name}')

        if filters['payment_method']:
            parts.append(f'پرداخت: {self.expenses_table_widget.payment_filter.currentText()}')

        if filters['from_date'] or filters['to_date']:
            parts.append(f"{filters['from_date'] or '...'} تا {filters['to_date'] or '...'}")

        if filters['search_text']:
            parts.append('دارای جستجو')

        return ' | '.join(parts)

    def _export_expenses(self):
        filters = self.expenses_table_widget.current_filters()
        from_date = filters['from_date']
        to_date = filters['to_date']
        quick_filter = filters['quick_filter']
        linked_only = quick_filter == 'linked'

        if quick_filter == 'today':
            today_text = today_jalali().strftime('%Y/%m/%d')
            from_date = today_text
            to_date = today_text
        elif quick_filter == 'month':
            today = today_jalali()
            if today.month <= 6:
                days_in_month = 31
            elif today.month <= 11:
                days_in_month = 30
            else:
                days_in_month = 30 if today.isleap() else 29
            from_date = f'{today.year}/{today.month:02d}/01'
            to_date = f'{today.year}/{today.month:02d}/{days_in_month:02d}'

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            'محل ذخیره گزارش هزینه ها',
            '',
            'Excel Files (*.xlsx)',
        )
        if not file_path:
            return

        try:
            result = self.export_service.export_expenses_to_excel(
                file_path=file_path,
                search_text=filters['search_text'],
                category_id=filters['category_id'],
                payment_method=filters['payment_method'],
                from_date=from_date,
                to_date=to_date,
                linked_only=linked_only,
            )
        except ValueError as exc:
            QMessageBox.warning(self, 'خطا', str(exc))
            return

        QMessageBox.information(self, 'خروجی اکسل', f'گزارش هزینه ها با موفقیت ذخیره شد\n{result}')

    def trigger_export_expenses(self):
        self._export_expenses()
