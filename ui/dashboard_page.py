from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtCharts import (
        QCategoryAxis,
        QBarCategoryAxis,
        QBarSeries,
        QBarSet,
        QChart,
        QChartView,
        QLineSeries,
        QValueAxis,
    )
except ImportError:  # pragma: no cover - QtCharts should be bundled with PySide6.
    QChart = None
    QChartView = None

from utils.date_utils import jalali_to_gregorian, normalize_jalali_date_text, today_jalali


class DashboardPage(QWidget):
    STATUS_LABELS = {
        'PENDING': 'در انتظار وصول',
        'DEPOSITED': 'واگذار شده به بانک',
        'PAID': 'وصول شده',
        'CLEARED': 'تسویه شده',
        'BOUNCED': 'برگشت خورده',
        'RETURNED': 'عودت داده شده',
        'ENDORSED': 'پشت نویسی شده',
        'CANCELED': 'لغو شده',
    }

    STATUS_COLORS = {
        'PENDING': ('#f59e0b', '#fff7ed'),
        'DEPOSITED': ('#3b82f6', '#eff6ff'),
        'PAID': ('#059669', '#ecfdf5'),
        'CLEARED': ('#10b981', '#ecfdf5'),
        'BOUNCED': ('#dc2626', '#fef2f2'),
        'RETURNED': ('#f97316', '#fff7ed'),
        'ENDORSED': ('#6366f1', '#eef2ff'),
        'CANCELED': ('#64748b', '#f8fafc'),
    }

    OPEN_STATUSES = {'PENDING', 'DEPOSITED', 'ENDORSED'}
    PAID_STATUSES = {'PAID', 'CLEARED'}

    def __init__(
        self,
        check_service,
        expense_service=None,
        registration_service=None,
        export_service=None,
        ai_service=None,
        debt_service=None,
        parent=None,
    ):
        super().__init__(parent)
        self.check_service = check_service
        self.expense_service = expense_service
        self.registration_service = registration_service
        self.export_service = export_service
        self.ai_service = ai_service
        self.debt_service = debt_service

        self.metric_values: dict[str, QLabel] = {}
        self.module_values: dict[str, QLabel] = {}
        self.module_growth_values: dict[str, QLabel] = {}
        self.cashflow_values: dict[str, QLabel] = {}

        self._all_checks = []
        self._all_expenses = []
        self._all_registrations = []
        self._all_debts = []
        self._current_dashboard_export_payload = {}
        self._latest_ai_result = {}
        self._ai_html_feed: list[str] = []

        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root_layout.addWidget(scroll)

        content = QWidget(self)
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(12)

        self._build_header(content_layout)
        self._build_module_summary(content_layout)
        self._build_analytics_metrics(content_layout)
        self._build_ai_insights_panel(content_layout)
        self._build_charts(content_layout)
        self._build_monthly_analytics_view(content_layout)
        self._build_cashflow_snapshot(content_layout)
        self._build_monthly_comparison(content_layout)
        self._build_category_breakdown(content_layout)
        self._build_upcoming_panel(content_layout)
        content_layout.addStretch()

    def _build_header(self, root_layout):
        panel = QFrame(self)
        panel.setObjectName('pageHeaderPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        row = QHBoxLayout()
        title_box = QVBoxLayout()

        title = QLabel('Dr. Harrasi')
        title.setObjectName('dashboardTitle')
        subtitle = QLabel('Advanced Financial Intelligence Dashboard')
        subtitle.setObjectName('dashboardSubtitle')
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        row.addLayout(title_box)
        row.addStretch()

        controls = QVBoxLayout()
        filter_row = QHBoxLayout()

        self.year_filter = QComboBox(self)
        self.month_filter = QComboBox(self)
        self.year_filter.setMinimumWidth(120)
        self.month_filter.setMinimumWidth(120)

        lbl_year = QLabel('سال')
        lbl_year.setObjectName('dashboardHintBadge')
        lbl_month = QLabel('ماه')
        lbl_month.setObjectName('dashboardHintBadge')

        filter_row.addWidget(lbl_year)
        filter_row.addWidget(self.year_filter)
        filter_row.addWidget(lbl_month)
        filter_row.addWidget(self.month_filter)

        self.last_updated_label = QLabel('آخرین به روزرسانی: -')
        self.last_updated_label.setObjectName('dashboardLastUpdated')
        self.last_updated_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.btn_refresh = QPushButton('به روزرسانی')
        self.btn_refresh.setObjectName('dashboardRefreshButton')
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_export_dashboard = QPushButton('خروجی تحلیل')
        self.btn_export_dashboard.setObjectName('dashboardRefreshButton')
        self.btn_export_dashboard.clicked.connect(self._export_dashboard_analytics)

        controls.addLayout(filter_row)
        controls.addWidget(self.last_updated_label)
        controls.addWidget(self.btn_export_dashboard)
        controls.addWidget(self.btn_refresh)

        row.addLayout(controls)
        layout.addLayout(row)
        root_layout.addWidget(panel)

        self.year_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.month_filter.currentIndexChanged.connect(self._on_filter_changed)

    def _build_module_summary(self, root_layout):
        panel = QFrame(self)
        panel.setObjectName('dashboardPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title = QLabel('خلاصه یکپارچه دامنه ها')
        title.setObjectName('dashboardSectionTitle')
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        modules = [
            ('checks', 'چک ها', '0', 'کل مبلغ چک های بازه'),
            ('incomes', 'درآمدها', '0', 'مجموع درآمد ثبت شده'),
            ('registrations', 'ثبت نام ها', '0', 'تعداد ثبت نام های بازه'),
            ('expenses', 'هزینه ها', '0', 'مجموع هزینه های ثبت شده'),
            ('receivables', 'مطالبات', '0', 'مجموع مانده حساب های دریافتنی'),
        ]

        for idx, (key, module_title, default_value, helper) in enumerate(modules):
            card = QFrame()
            card.setObjectName('moduleSummaryCard')
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)

            label = QLabel(module_title)
            label.setObjectName('moduleSummaryTitle')
            value = QLabel(default_value)
            value.setObjectName('moduleSummaryValue')
            growth = QLabel('تغییر: -')
            growth.setObjectName('moduleGrowthNeutral')
            helper_label = QLabel(helper)
            helper_label.setObjectName('moduleSummaryHelper')

            card_layout.addWidget(label)
            card_layout.addWidget(value)
            card_layout.addWidget(growth)
            card_layout.addStretch()
            card_layout.addWidget(helper_label)

            self.module_values[key] = value
            self.module_growth_values[key] = growth
            grid.addWidget(card, idx // 2, idx % 2)

        for col in range(2):
            grid.setColumnStretch(col, 1)

        layout.addLayout(grid)
        root_layout.addWidget(panel)

    def _build_analytics_metrics(self, root_layout):
        panel = QFrame(self)
        panel.setObjectName('dashboardPanel')
        layout = QGridLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)

        metrics = [
            ('net_cashflow', 'خالص جریان نقدی', '0', 'اختلاف کل درآمد و کل هزینه.'),
            ('collection_rate', 'نرخ وصول', '0%', 'درصد چک های وصول/تسویه شده.'),
            ('open_checks_amount', 'ریسک چک باز', '0', 'مبلغ چک های باز در بازه.'),
            ('avg_monthly_margin', 'میانگین حاشیه ماهانه', '0', 'میانگین خالص درآمد ماهانه.'),
        ]

        for idx, (key, title, value_text, helper) in enumerate(metrics):
            self.metric_values[key] = self._create_summary_card(layout, idx // 2, idx % 2, title, value_text, helper)

        for col in range(2):
            layout.setColumnStretch(col, 1)
        root_layout.addWidget(panel)

    def _build_ai_insights_panel(self, root_layout):
        panel = QFrame(self)
        panel.setObjectName('dashboardPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel('AI Insights & Automation')
        title.setObjectName('dashboardSectionTitle')
        self.ai_status_badge = QLabel('AI Status: Local Engine Ready')
        self.ai_status_badge.setObjectName('dashboardHintBadge')
        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(self.ai_status_badge)
        layout.addLayout(header_row)

        self.ai_connection_banner = QLabel('')
        self.ai_connection_banner.setObjectName('dashboardEmptyState')
        self.ai_connection_banner.setWordWrap(True)
        self.ai_connection_banner.hide()
        layout.addWidget(self.ai_connection_banner)

        buttons_row = QHBoxLayout()
        self.btn_generate_ai = QPushButton('تولید تحلیل هوشمند')
        self.btn_generate_ai.setObjectName('dashboardRefreshButton')
        self.btn_generate_ai.clicked.connect(self._refresh_ai_outputs)
        self.btn_export_ai_excel = QPushButton('گزارش حرفه ای Excel')
        self.btn_export_ai_excel.setObjectName('dashboardRefreshButton')
        self.btn_export_ai_excel.clicked.connect(self._export_ai_excel_report)
        self.btn_export_ai_pdf = QPushButton('گزارش حرفه ای PDF')
        self.btn_export_ai_pdf.setObjectName('dashboardRefreshButton')
        self.btn_export_ai_pdf.clicked.connect(self._export_ai_pdf_report)
        self.btn_monthly_export = QPushButton('خروجی ماهانه')
        self.btn_monthly_export.setObjectName('dashboardRefreshButton')
        self.btn_monthly_export.clicked.connect(self._open_monthly_export_dialog)
        buttons_row.addWidget(self.btn_generate_ai)
        buttons_row.addWidget(self.btn_export_ai_excel)
        buttons_row.addWidget(self.btn_export_ai_pdf)
        buttons_row.addWidget(self.btn_monthly_export)
        buttons_row.addStretch()
        layout.addLayout(buttons_row)

        query_row = QHBoxLayout()
        self.ai_query_input = QLineEdit(self)
        self.ai_query_input.setPlaceholderText(
            'سوال طبیعی بپرسید یا خروجی بگیرید: مثلا \"خروجی PDF 1405/01\"'
        )
        self.btn_ai_query = QPushButton('پرسش از AI')
        self.btn_ai_query.setObjectName('dashboardRefreshButton')
        self.btn_ai_query.clicked.connect(self._ask_ai_query)
        query_row.addWidget(self.ai_query_input, 1)
        query_row.addWidget(self.btn_ai_query)
        layout.addLayout(query_row)

        self.ai_insights_text = QTextEdit(self)
        self.ai_insights_text.setReadOnly(True)
        self.ai_insights_text.setMinimumHeight(190)
        self.ai_insights_text.setAcceptRichText(True)
        self.ai_insights_text.setPlaceholderText('AI analysis report and chat will appear here.')
        layout.addWidget(self.ai_insights_text)

        self.ai_insights_text.setHtml(
            '<p>موتور تحلیل محلی فعال است و بدون نیاز به اینترنت کار می کند.</p>'
            '<p>برای تحلیل، پرسش طبیعی یا دستور خروجی ماهانه وارد کنید.</p>'
        )
        self._refresh_ai_ui_state()
        root_layout.addWidget(panel)

    def _build_charts(self, root_layout):
        panel = QFrame(self)
        panel.setObjectName('dashboardPanel')
        layout = QGridLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setHorizontalSpacing(12)

        trend_title = QLabel('روند مالی (درآمد / هزینه)')
        trend_title.setObjectName('dashboardSectionTitle')
        layout.addWidget(trend_title, 0, 0)

        status_title = QLabel('توزیع وضعیت چک ها')
        status_title.setObjectName('dashboardSectionTitle')
        layout.addWidget(status_title, 0, 1)

        if QChartView is not None:
            self.trend_chart_view = QChartView(self)
            self.trend_chart_view.setObjectName('dashboardChart')
            self.trend_chart_view.setRenderHint(QPainter.Antialiasing)

            self.status_chart_view = QChartView(self)
            self.status_chart_view.setObjectName('dashboardChart')
            self.status_chart_view.setRenderHint(QPainter.Antialiasing)

            layout.addWidget(self.trend_chart_view, 1, 0)
            layout.addWidget(self.status_chart_view, 1, 1)
        else:
            self.trend_chart_view = QLabel('ماژول QtCharts در محیط فعلی در دسترس نیست.')
            self.status_chart_view = QLabel('ماژول QtCharts در محیط فعلی در دسترس نیست.')
            self.trend_chart_view.setObjectName('dashboardEmptyState')
            self.status_chart_view.setObjectName('dashboardEmptyState')
            layout.addWidget(self.trend_chart_view, 1, 0)
            layout.addWidget(self.status_chart_view, 1, 1)

        root_layout.addWidget(panel)

    def _build_monthly_analytics_view(self, root_layout):
        panel = QFrame(self)
        panel.setObjectName('dashboardPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel('نمای تحلیل ماهانه')
        title.setObjectName('dashboardSectionTitle')
        self.monthly_analytics_badge = QLabel('بازه: -')
        self.monthly_analytics_badge.setObjectName('dashboardHintBadge')
        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(self.monthly_analytics_badge)
        layout.addLayout(header_row)

        self.monthly_analytics_table = QTableWidget(0, 6)
        self.monthly_analytics_table.setObjectName('dashboardTable')
        self.monthly_analytics_table.setHorizontalHeaderLabels(
            ['دوره', 'درآمد', 'هزینه', 'خالص', 'تعداد ثبت نام', 'چک ها (تعداد/مبلغ)']
        )
        self.monthly_analytics_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.monthly_analytics_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.monthly_analytics_table.verticalHeader().setVisible(False)
        self.monthly_analytics_table.horizontalHeader().setStretchLastSection(True)
        self.monthly_analytics_table.setMinimumHeight(230)
        layout.addWidget(self.monthly_analytics_table)

        root_layout.addWidget(panel)

    def _build_cashflow_snapshot(self, root_layout):
        panel = QFrame(self)
        panel.setObjectName('dashboardPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header = QLabel('نمای سریع جریان نقدی')
        header.setObjectName('dashboardSectionTitle')
        layout.addWidget(header)

        row = QHBoxLayout()
        row.setSpacing(10)

        blocks = [
            ('incoming', 'ورودی نقدی', '0'),
            ('outgoing', 'خروجی نقدی', '0'),
            ('net', 'جریان خالص', '0'),
            ('expense_ratio', 'نسبت هزینه به درآمد', '0%'),
        ]

        for key, title, default in blocks:
            card = QFrame()
            card.setObjectName('monthlyMetricCard')
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            title_label = QLabel(title)
            title_label.setObjectName('monthlyMetricTitle')
            value_label = QLabel(default)
            value_label.setObjectName('monthlyMetricValue')
            card_layout.addWidget(title_label)
            card_layout.addWidget(value_label)
            row.addWidget(card, 1)
            self.cashflow_values[key] = value_label

        layout.addLayout(row)
        root_layout.addWidget(panel)

    def _build_monthly_comparison(self, root_layout):
        panel = QFrame(self)
        panel.setObjectName('dashboardPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)

        header_row = QHBoxLayout()
        title = QLabel('مقایسه ماه جاری و ماه قبل')
        title.setObjectName('dashboardSectionTitle')
        self.comparison_badge = QLabel('بازه: -')
        self.comparison_badge.setObjectName('dashboardHintBadge')
        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(self.comparison_badge)
        layout.addLayout(header_row)

        self.monthly_comparison_table = QTableWidget(0, 4)
        self.monthly_comparison_table.setObjectName('dashboardTable')
        self.monthly_comparison_table.setHorizontalHeaderLabels(['شاخص', 'دوره فعلی', 'دوره قبلی', 'تغییر'])
        self.monthly_comparison_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.monthly_comparison_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.monthly_comparison_table.verticalHeader().setVisible(False)
        self.monthly_comparison_table.horizontalHeader().setStretchLastSection(True)
        self.monthly_comparison_table.setMinimumHeight(190)
        layout.addWidget(self.monthly_comparison_table)

        root_layout.addWidget(panel)

    def _build_category_breakdown(self, root_layout):
        panel = QFrame(self)
        panel.setObjectName('dashboardPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel('تحلیل دسته بندی هزینه ها')
        title.setObjectName('dashboardSectionTitle')
        layout.addWidget(title)

        self.category_table = QTableWidget(0, 4)
        self.category_table.setObjectName('dashboardTable')
        self.category_table.setHorizontalHeaderLabels(['دسته بندی', 'مبلغ', 'سهم از کل', 'روند'])
        self.category_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.category_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.category_table.verticalHeader().setVisible(False)
        self.category_table.horizontalHeader().setStretchLastSection(True)
        self.category_table.setMinimumHeight(220)
        layout.addWidget(self.category_table)

        root_layout.addWidget(panel)

    def _build_upcoming_panel(self, root_layout):
        panel = QFrame(self)
        panel.setObjectName('dashboardPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel('هشدار ریسک چک های سررسید نزدیک')
        title.setObjectName('dashboardSectionTitle')
        helper = QLabel('چک های باز با سررسید 7 روز آینده')
        helper.setObjectName('dashboardHintBadge')
        header.addWidget(title)
        header.addStretch()
        header.addWidget(helper)
        layout.addLayout(header)

        self.upcoming_empty_state = QLabel('هیچ چک ریسکی برای 7 روز آینده وجود ندارد.')
        self.upcoming_empty_state.setObjectName('dashboardEmptyState')
        self.upcoming_empty_state.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.upcoming_empty_state)

        self.upcoming_table = QTableWidget(0, 7)
        self.upcoming_table.setObjectName('dashboardTable')
        self.upcoming_table.setHorizontalHeaderLabels(
            ['شماره سریال چک', 'ثبت کننده', 'تاریخ سررسید', 'روز باقی مانده', 'وضعیت', 'مبلغ', 'سطح ریسک']
        )
        self.upcoming_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.upcoming_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.upcoming_table.setSelectionMode(QTableWidget.SingleSelection)
        self.upcoming_table.setAlternatingRowColors(True)
        self.upcoming_table.verticalHeader().setVisible(False)
        self.upcoming_table.horizontalHeader().setStretchLastSection(True)
        self.upcoming_table.setMinimumHeight(230)
        layout.addWidget(self.upcoming_table)

        root_layout.addWidget(panel)

    def _create_summary_card(self, parent_layout, row, col, title_text, value_text, helper_text):
        card = QFrame()
        card.setObjectName('summaryCard')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)

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

        parent_layout.addWidget(card, row, col)
        return value

    def refresh(self):
        self._all_checks = self.check_service.list_checks()
        self._all_expenses = self.expense_service.list_expenses() if self.expense_service is not None else []
        self._all_registrations = self.registration_service.list_all() if self.registration_service is not None else []
        self._all_debts = self.debt_service.list_debts() if self.debt_service is not None else []

        self._rebuild_filter_options()
        self._refresh_filtered_metrics()
        self.last_updated_label.setText(f"آخرین به روزرسانی: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def _on_filter_changed(self):
        selected_year = self.year_filter.currentData()
        self.month_filter.setEnabled(selected_year is not None)
        if selected_year is None and self.month_filter.currentData() is not None:
            self.month_filter.blockSignals(True)
            self.month_filter.setCurrentIndex(0)
            self.month_filter.blockSignals(False)

        self._refresh_filtered_metrics()

    def _rebuild_filter_options(self):
        previous_year = self.year_filter.currentData()
        previous_month = self.month_filter.currentData()

        years = sorted(self._collect_years())
        today = today_jalali()

        self.year_filter.blockSignals(True)
        self.month_filter.blockSignals(True)

        self.year_filter.clear()
        self.year_filter.addItem('همه سال ها (نمای کلی)', None)
        for year in years:
            self.year_filter.addItem(str(year), year)

        target_year = previous_year
        if target_year not in years:
            target_year = today.year if today.year in years else None
        self._set_combo_value(self.year_filter, target_year)

        self.month_filter.clear()
        self.month_filter.addItem('همه ماه ها', None)
        for month in range(1, 13):
            self.month_filter.addItem(f'{month:02d}', month)

        selected_year = self.year_filter.currentData()
        if selected_year is None:
            target_month = None
        elif previous_month is not None and 1 <= int(previous_month) <= 12:
            target_month = int(previous_month)
        elif selected_year == today.year:
            target_month = today.month
        else:
            target_month = None

        self._set_combo_value(self.month_filter, target_month)
        self.month_filter.setEnabled(selected_year is not None)

        self.year_filter.blockSignals(False)
        self.month_filter.blockSignals(False)

    def _refresh_filtered_metrics(self):
        year = self.year_filter.currentData()
        month = self.month_filter.currentData() if year is not None else None

        checks = [item for item in self._all_checks if self._date_matches_period(getattr(item, 'due_date', ''), year, month)]
        expenses = [
            item for item in self._all_expenses if self._date_matches_period(getattr(item, 'expense_date', ''), year, month)
        ]
        registrations = [
            item
            for item in self._all_registrations
            if self._date_matches_period(getattr(item, 'registration_date', ''), year, month)
        ]
        debts = [item for item in self._all_debts if self._date_matches_period(getattr(item, 'due_date', ''), year, month)]

        prev_period = self._previous_period(year, month)
        previous_checks, previous_expenses, previous_registrations, previous_debts = self._period_data(
            *prev_period,
            include_all=False,
        )

        self._update_module_summary(
            checks,
            expenses,
            registrations,
            debts,
            previous_checks,
            previous_expenses,
            previous_registrations,
            previous_debts,
        )
        self._update_analytics_metrics(checks, expenses, registrations)
        monthly_rows = self._update_monthly_analytics_view(year, month)
        self._update_cashflow_snapshot(expenses, registrations)
        self._update_monthly_comparison(
            expenses,
            registrations,
            previous_expenses,
            previous_registrations,
            prev_period,
        )
        self._update_category_breakdown(expenses, previous_expenses)
        self._update_upcoming_checks(checks)
        self._update_charts(checks, expenses, registrations, year, month)
        self._current_dashboard_export_payload = self._build_export_payload(
            year,
            month,
            checks,
            expenses,
            registrations,
            previous_checks,
            previous_expenses,
            previous_registrations,
            monthly_rows,
        )
        self._refresh_ai_ui_state()

    def _period_data(self, year, month, include_all=True):
        if year is None and not include_all:
            return [], [], [], []
        checks = [item for item in self._all_checks if self._date_matches_period(getattr(item, 'due_date', ''), year, month)]
        expenses = [
            item for item in self._all_expenses if self._date_matches_period(getattr(item, 'expense_date', ''), year, month)
        ]
        registrations = [
            item
            for item in self._all_registrations
            if self._date_matches_period(getattr(item, 'registration_date', ''), year, month)
        ]
        debts = [item for item in self._all_debts if self._date_matches_period(getattr(item, 'due_date', ''), year, month)]
        return checks, expenses, registrations, debts

    def _update_module_summary(
        self,
        checks,
        expenses,
        registrations,
        debts,
        previous_checks,
        previous_expenses,
        previous_registrations,
        previous_debts,
    ):
        current_values = {
            'checks': sum(int(item.amount or 0) for item in checks),
            'incomes': sum(int(item.income_total or 0) for item in registrations),
            'registrations': len(registrations),
            'expenses': sum(int(item.amount or 0) for item in expenses),
            'receivables': sum(int(item.remaining_balance or 0) for item in debts),
        }

        previous_values = {
            'checks': sum(int(item.amount or 0) for item in previous_checks),
            'incomes': sum(int(item.income_total or 0) for item in previous_registrations),
            'registrations': len(previous_registrations),
            'expenses': sum(int(item.amount or 0) for item in previous_expenses),
            'receivables': sum(int(item.remaining_balance or 0) for item in previous_debts),
        }

        for key, value in current_values.items():
            self.module_values[key].setText(f'{value:,}')
            growth = self._growth_text(value, previous_values[key])
            self._apply_growth_style(self.module_growth_values[key], growth)

    def _update_analytics_metrics(self, checks, expenses, registrations):
        total_income = sum(int(item.income_total or 0) for item in registrations)
        total_expenses = sum(int(item.amount or 0) for item in expenses)
        net_cashflow = total_income - total_expenses

        open_checks = [item for item in checks if (item.status or '').upper() in self.OPEN_STATUSES]
        paid_checks = [item for item in checks if (item.status or '').upper() in self.PAID_STATUSES]

        total_checks = len(open_checks) + len(paid_checks)
        collection_rate = (len(paid_checks) / total_checks * 100) if total_checks else 0
        open_checks_amount = sum(int(item.amount or 0) for item in open_checks)

        month_rows = self._build_monthly_rows(expenses, registrations)
        avg_monthly_margin = int(sum(item['net'] for item in month_rows) / len(month_rows)) if month_rows else 0

        self.metric_values['net_cashflow'].setText(f'{net_cashflow:+,}')
        self.metric_values['net_cashflow'].setStyleSheet(
            'color: #15803d;' if net_cashflow >= 0 else 'color: #b91c1c;'
        )

        self.metric_values['collection_rate'].setText(f'{collection_rate:.1f}%')
        self.metric_values['open_checks_amount'].setText(f'{open_checks_amount:,}')
        self.metric_values['avg_monthly_margin'].setText(f'{avg_monthly_margin:+,}')
        self.metric_values['avg_monthly_margin'].setStyleSheet(
            'color: #15803d;' if avg_monthly_margin >= 0 else 'color: #b91c1c;'
        )

    def _update_cashflow_snapshot(self, expenses, registrations):
        incoming = sum(int(item.income_total or 0) for item in registrations)
        outgoing = sum(int(item.amount or 0) for item in expenses)
        net = incoming - outgoing
        ratio = (outgoing / incoming * 100) if incoming else 0

        self.cashflow_values['incoming'].setText(f'{incoming:,}')
        self.cashflow_values['outgoing'].setText(f'{outgoing:,}')
        self.cashflow_values['net'].setText(f'{net:+,}')
        self.cashflow_values['expense_ratio'].setText(f'{ratio:.1f}%')

    def _update_monthly_analytics_view(self, year, month):
        rows = self._build_monthly_analytics_rows(year, month)
        self.monthly_analytics_table.setRowCount(len(rows))
        self.monthly_analytics_badge.setText(f'بازه: {self._period_label(year, month)}')

        for row_index, row in enumerate(rows):
            period_item = QTableWidgetItem(row['period'])
            income_item = QTableWidgetItem(f"{row['income']:,}")
            expense_item = QTableWidgetItem(f"{row['expense']:,}")
            net_item = QTableWidgetItem(f"{row['net']:+,}")
            registrations_item = QTableWidgetItem(str(row['registrations']))
            checks_item = QTableWidgetItem(f"{row['checks_count']} / {row['checks_amount']:,}")

            income_item.setTextAlignment(Qt.AlignCenter)
            expense_item.setTextAlignment(Qt.AlignCenter)
            net_item.setTextAlignment(Qt.AlignCenter)
            registrations_item.setTextAlignment(Qt.AlignCenter)
            checks_item.setTextAlignment(Qt.AlignCenter)
            net_item.setForeground(QColor('#15803d' if row['net'] >= 0 else '#b91c1c'))

            self.monthly_analytics_table.setItem(row_index, 0, period_item)
            self.monthly_analytics_table.setItem(row_index, 1, income_item)
            self.monthly_analytics_table.setItem(row_index, 2, expense_item)
            self.monthly_analytics_table.setItem(row_index, 3, net_item)
            self.monthly_analytics_table.setItem(row_index, 4, registrations_item)
            self.monthly_analytics_table.setItem(row_index, 5, checks_item)

        self.monthly_analytics_table.resizeColumnsToContents()
        return rows

    def _update_monthly_comparison(
        self,
        expenses,
        registrations,
        previous_expenses,
        previous_registrations,
        previous_period,
    ):
        current_income = sum(int(item.income_total or 0) for item in registrations)
        current_expense = sum(int(item.amount or 0) for item in expenses)
        current_net = current_income - current_expense

        prev_income = sum(int(item.income_total or 0) for item in previous_registrations)
        prev_expense = sum(int(item.amount or 0) for item in previous_expenses)
        prev_net = prev_income - prev_expense

        rows = [
            ('درآمد', current_income, prev_income),
            ('هزینه', current_expense, prev_expense),
            ('خالص', current_net, prev_net),
        ]

        self.monthly_comparison_table.setRowCount(len(rows))
        for row_index, (name, current, previous) in enumerate(rows):
            delta_text = self._growth_text(current, previous)
            self.monthly_comparison_table.setItem(row_index, 0, QTableWidgetItem(name))
            self.monthly_comparison_table.setItem(row_index, 1, QTableWidgetItem(f'{current:,}'))
            self.monthly_comparison_table.setItem(row_index, 2, QTableWidgetItem(f'{previous:,}'))
            delta_item = QTableWidgetItem(delta_text)
            if delta_text.startswith('تغییر: +'):
                delta_item.setForeground(QColor('#15803d'))
            elif delta_text.startswith('تغییر: -') and delta_text != 'تغییر: -':
                delta_item.setForeground(QColor('#b91c1c'))
            self.monthly_comparison_table.setItem(row_index, 3, delta_item)

        self.monthly_comparison_table.resizeColumnsToContents()
        if previous_period[0] is None:
            self.comparison_badge.setText('بازه مقایسه: مبنای قبلی ندارد')
        else:
            self.comparison_badge.setText(f'بازه مقایسه: {self._period_label(*previous_period)}')

    def _update_category_breakdown(self, expenses, previous_expenses):
        totals: dict[str, int] = {}
        prev_totals: dict[str, int] = {}

        for item in expenses:
            name = getattr(item, 'category_name', '') or 'نامشخص'
            totals[name] = totals.get(name, 0) + int(item.amount or 0)

        for item in previous_expenses:
            name = getattr(item, 'category_name', '') or 'نامشخص'
            prev_totals[name] = prev_totals.get(name, 0) + int(item.amount or 0)

        total_expense = sum(totals.values())
        ordered = sorted(totals.items(), key=lambda it: it[1], reverse=True)

        self.category_table.setRowCount(len(ordered))
        for row_index, (category, amount) in enumerate(ordered):
            share = (amount / total_expense * 100) if total_expense else 0
            trend = self._growth_text(amount, prev_totals.get(category, 0))

            self.category_table.setItem(row_index, 0, QTableWidgetItem(category))
            self.category_table.setItem(row_index, 1, QTableWidgetItem(f'{amount:,}'))
            self.category_table.setItem(row_index, 2, QTableWidgetItem(f'{share:.1f}%'))
            trend_item = QTableWidgetItem(trend)
            if trend.startswith('تغییر: +'):
                trend_item.setForeground(QColor('#15803d'))
            elif trend.startswith('تغییر: -') and trend != 'تغییر: -':
                trend_item.setForeground(QColor('#b91c1c'))
            self.category_table.setItem(row_index, 3, trend_item)

        self.category_table.resizeColumnsToContents()

    def _update_upcoming_checks(self, checks):
        today = date.today()
        horizon = today + timedelta(days=7)

        upcoming = []
        for check in checks:
            due = self._parse_date(getattr(check, 'due_date', ''))
            status_key = (getattr(check, 'status', '') or '').upper()
            if due and today <= due <= horizon and status_key in self.OPEN_STATUSES:
                days_left = (due - today).days
                upcoming.append((days_left, due, check))

        upcoming.sort(key=lambda item: item[0])

        self.upcoming_table.setRowCount(len(upcoming))
        self.upcoming_empty_state.setVisible(not upcoming)
        self.upcoming_table.setVisible(bool(upcoming))

        for row_index, (days_left, due, check) in enumerate(upcoming):
            risk_level = 'بحرانی' if days_left <= 1 else 'زیاد' if days_left <= 3 else 'متوسط'
            risk_color = '#dc2626' if days_left <= 1 else '#ea580c' if days_left <= 3 else '#b45309'

            self.upcoming_table.setItem(row_index, 0, QTableWidgetItem(check.serial_7 or '-'))
            self.upcoming_table.setItem(row_index, 1, QTableWidgetItem(check.registrant_name or '-'))
            self.upcoming_table.setItem(row_index, 2, QTableWidgetItem(check.due_date or '-'))

            days_item = QTableWidgetItem(str(days_left))
            days_item.setTextAlignment(Qt.AlignCenter)
            self.upcoming_table.setItem(row_index, 3, days_item)

            status_key = (check.status or '').upper()
            status_item = QTableWidgetItem(self.STATUS_LABELS.get(status_key, status_key or '-'))
            self._apply_status_style(status_item, status_key)
            status_item.setTextAlignment(Qt.AlignCenter)
            self.upcoming_table.setItem(row_index, 4, status_item)

            amount_item = QTableWidgetItem(f"{int(check.amount or 0):,}")
            amount_item.setTextAlignment(Qt.AlignCenter)
            self.upcoming_table.setItem(row_index, 5, amount_item)

            risk_item = QTableWidgetItem(risk_level)
            risk_item.setForeground(QColor(risk_color))
            risk_item.setTextAlignment(Qt.AlignCenter)
            self.upcoming_table.setItem(row_index, 6, risk_item)

        self.upcoming_table.resizeColumnsToContents()

    def _update_charts(self, checks, expenses, registrations, year, month):
        if QChartView is None:
            return

        periods = self._build_chart_periods(year, month)
        if not periods:
            periods = self._last_available_periods(6)

        income_map = self._aggregate_by_period(registrations, 'registration_date', 'income_total')
        expense_map = self._aggregate_by_period(expenses, 'expense_date', 'amount')

        income_series = QLineSeries()
        income_series.setName('درآمد')
        income_series.setColor(QColor('#0f766e'))
        expense_series = QLineSeries()
        expense_series.setName('هزینه')
        expense_series.setColor(QColor('#ef4444'))

        labels = []
        max_value = 0
        for idx, period in enumerate(periods):
            labels.append(period)
            income_value = income_map.get(period, 0)
            expense_value = expense_map.get(period, 0)
            income_series.append(idx, income_value)
            expense_series.append(idx, expense_value)
            max_value = max(max_value, income_value, expense_value)

        trend_chart = QChart()
        trend_chart.addSeries(income_series)
        trend_chart.addSeries(expense_series)
        trend_chart.setTitle('روند ماهانه')
        trend_chart.legend().setVisible(True)

        axis_x = QCategoryAxis()
        for idx, label in enumerate(labels):
            axis_x.append(label, idx)
        axis_x.setRange(0, max(len(labels) - 1, 0))
        axis_y = QValueAxis()
        axis_y.setLabelFormat('%d')
        axis_y.setRange(0, max(max_value * 1.1, 1000))

        trend_chart.addAxis(axis_x, Qt.AlignBottom)
        trend_chart.addAxis(axis_y, Qt.AlignLeft)
        income_series.attachAxis(axis_x)
        income_series.attachAxis(axis_y)
        expense_series.attachAxis(axis_x)
        expense_series.attachAxis(axis_y)

        self.trend_chart_view.setChart(trend_chart)

        status_counts = {}
        for check in checks:
            key = (check.status or '').upper() or 'UNKNOWN'
            status_counts[key] = status_counts.get(key, 0) + 1

        status_chart = QChart()
        status_chart.setTitle('ترکیب وضعیت چک ها')
        status_bar = QBarSeries()

        categories = []
        status_values = []
        count_set = QBarSet('تعداد')
        for status_key, count in sorted(status_counts.items(), key=lambda it: it[1], reverse=True):
            categories.append(self.STATUS_LABELS.get(status_key, status_key))
            status_values.append(int(count))

        if categories:
            count_set.append(status_values)
            status_bar.append(count_set)
            status_chart.addSeries(status_bar)
            axis_status_x = QBarCategoryAxis()
            axis_status_x.append(categories)
            axis_status_y = QValueAxis()
            axis_status_y.setRange(0, max(status_values) + 1)
            status_chart.addAxis(axis_status_x, Qt.AlignBottom)
            status_chart.addAxis(axis_status_y, Qt.AlignLeft)
            status_bar.attachAxis(axis_status_x)
            status_bar.attachAxis(axis_status_y)
        else:
            status_chart.setTitle('ترکیب وضعیت چک ها - داده ای وجود ندارد')

        self.status_chart_view.setChart(status_chart)

    def _build_chart_periods(self, year, month):
        if year is None:
            return self._last_available_periods(8)

        if month is None:
            return [f'{year}/{value:02d}' for value in range(1, 13)]

        periods = []
        current_year = int(year)
        current_month = int(month)
        for _ in range(6):
            periods.append(f'{current_year}/{current_month:02d}')
            current_year, current_month = self._shift_month(current_year, current_month, -1)
        periods.reverse()
        return periods

    def _build_monthly_analytics_rows(self, year, month):
        if year is None:
            periods = self._last_available_periods(24)
        elif month is None:
            periods = [f'{int(year)}/{value:02d}' for value in range(1, 13)]
        else:
            periods = [f'{int(year)}/{int(month):02d}']

        income_map = self._aggregate_by_period(self._all_registrations, 'registration_date', 'income_total')
        expense_map = self._aggregate_by_period(self._all_expenses, 'expense_date', 'amount')
        registrations_map = self._aggregate_count_by_period(self._all_registrations, 'registration_date')
        checks_count_map = self._aggregate_count_by_period(self._all_checks, 'due_date')
        checks_amount_map = self._aggregate_by_period(self._all_checks, 'due_date', 'amount')

        rows = []
        for period in periods:
            income = income_map.get(period, 0)
            expense = expense_map.get(period, 0)
            rows.append(
                {
                    'period': period,
                    'income': income,
                    'expense': expense,
                    'net': income - expense,
                    'registrations': registrations_map.get(period, 0),
                    'checks_count': checks_count_map.get(period, 0),
                    'checks_amount': checks_amount_map.get(period, 0),
                }
            )

        rows.sort(key=lambda item: item['period'], reverse=True)
        if year is None:
            rows = [
                item
                for item in rows
                if any([item['income'], item['expense'], item['registrations'], item['checks_count']])
            ]
        return rows

    def _last_available_periods(self, count):
        period_keys = set()
        for item in self._all_registrations:
            key = self._period_key(getattr(item, 'registration_date', ''))
            if key:
                period_keys.add(key)
        for item in self._all_expenses:
            key = self._period_key(getattr(item, 'expense_date', ''))
            if key:
                period_keys.add(key)
        ordered = sorted(period_keys)
        return ordered[-count:]

    def _aggregate_by_period(self, items, field_name, amount_field):
        values = {}
        for item in items:
            key = self._period_key(getattr(item, field_name, ''))
            if not key:
                continue
            values[key] = values.get(key, 0) + int(getattr(item, amount_field, 0) or 0)
        return values

    def _aggregate_count_by_period(self, items, field_name):
        values = {}
        for item in items:
            key = self._period_key(getattr(item, field_name, ''))
            if not key:
                continue
            values[key] = values.get(key, 0) + 1
        return values

    def _build_monthly_rows(self, expenses, registrations):
        totals = {}

        for item in registrations:
            key = self._period_key(getattr(item, 'registration_date', ''))
            if not key:
                continue
            cell = totals.setdefault(key, {'income': 0, 'expense': 0})
            cell['income'] += int(getattr(item, 'income_total', 0) or 0)

        for item in expenses:
            key = self._period_key(getattr(item, 'expense_date', ''))
            if not key:
                continue
            cell = totals.setdefault(key, {'income': 0, 'expense': 0})
            cell['expense'] += int(getattr(item, 'amount', 0) or 0)

        rows = []
        for key, values in totals.items():
            rows.append({'period': key, 'income': values['income'], 'expense': values['expense'], 'net': values['income'] - values['expense']})
        rows.sort(key=lambda row: row['period'])
        return rows

    def _collect_years(self):
        years = set()

        for check in self._all_checks:
            parts = self._extract_date_parts(getattr(check, 'due_date', ''))
            if parts:
                years.add(parts[0])
        for expense in self._all_expenses:
            parts = self._extract_date_parts(getattr(expense, 'expense_date', ''))
            if parts:
                years.add(parts[0])
        for registration in self._all_registrations:
            parts = self._extract_date_parts(getattr(registration, 'registration_date', ''))
            if parts:
                years.add(parts[0])
        for debt in self._all_debts:
            parts = self._extract_date_parts(getattr(debt, 'due_date', ''))
            if parts:
                years.add(parts[0])

        return years

    def _previous_period(self, year, month):
        if year is None:
            return None, None
        year = int(year)
        if month is None:
            return year - 1, None
        return self._shift_month(year, int(month), -1)

    @staticmethod
    def _shift_month(year, month, delta):
        step = 1 if delta > 0 else -1
        for _ in range(abs(delta)):
            month += step
            if month > 12:
                month = 1
                year += 1
            elif month < 1:
                month = 12
                year -= 1
        return year, month

    @staticmethod
    def _set_combo_value(combo, value):
        for idx in range(combo.count()):
            if combo.itemData(idx) == value:
                combo.setCurrentIndex(idx)
                return
        combo.setCurrentIndex(0)

    def _period_key(self, value):
        parts = self._extract_date_parts(value)
        if not parts:
            return ''
        return f'{parts[0]}/{parts[1]:02d}'

    def _period_label(self, year, month):
        if year is None:
            return 'نمای کلی'
        if month is None:
            return f'سال {year}'
        return f'{year}/{int(month):02d}'

    def _build_export_payload(
        self,
        year,
        month,
        checks,
        expenses,
        registrations,
        previous_checks,
        previous_expenses,
        previous_registrations,
        monthly_rows,
    ):
        total_income = sum(int(item.income_total or 0) for item in registrations)
        total_expenses = sum(int(item.amount or 0) for item in expenses)
        return {
            'period_label': self._period_label(year, month),
            'filters': {'year': year, 'month': month},
            'summary': {
                'incomes': total_income,
                'expenses': total_expenses,
                'net': total_income - total_expenses,
                'registrations_count': len(registrations),
                'checks_count': len(checks),
                'checks_amount': sum(int(item.amount or 0) for item in checks),
            },
            'growth': {
                'incomes': self._growth_text(
                    total_income,
                    sum(int(item.income_total or 0) for item in previous_registrations),
                ),
                'expenses': self._growth_text(
                    total_expenses,
                    sum(int(item.amount or 0) for item in previous_expenses),
                ),
                'registrations': self._growth_text(len(registrations), len(previous_registrations)),
                'checks': self._growth_text(len(checks), len(previous_checks)),
            },
            'monthly_analytics': monthly_rows,
            'category_breakdown': self._collect_table_rows(self.category_table),
            'monthly_comparison': self._collect_table_rows(self.monthly_comparison_table),
            'upcoming_risks': self._collect_table_rows(self.upcoming_table),
            'checks': [self._serialize_check(item) for item in checks],
            'expenses_rows': [self._serialize_expense(item) for item in expenses],
            'registrations_rows': [self._serialize_registration(item) for item in registrations],
        }

    @staticmethod
    def _collect_table_rows(table: QTableWidget):
        headers = []
        for idx in range(table.columnCount()):
            header_item = table.horizontalHeaderItem(idx)
            headers.append(header_item.text() if header_item else f'Column {idx + 1}')

        rows = []
        for row_idx in range(table.rowCount()):
            row = {}
            for col_idx, header in enumerate(headers):
                item = table.item(row_idx, col_idx)
                row[header] = item.text() if item else ''
            rows.append(row)
        return rows

    @staticmethod
    def _serialize_check(check):
        return {
            'id': getattr(check, 'id', None),
            'serial_7': getattr(check, 'serial_7', ''),
            'serial_18': getattr(check, 'serial_18', ''),
            'registrant_name': getattr(check, 'registrant_name', ''),
            'due_date': getattr(check, 'due_date', ''),
            'status': getattr(check, 'status', ''),
            'amount': int(getattr(check, 'amount', 0) or 0),
        }

    @staticmethod
    def _serialize_expense(expense):
        return {
            'id': getattr(expense, 'id', None),
            'title': getattr(expense, 'title', ''),
            'expense_date': getattr(expense, 'expense_date', ''),
            'category_name': getattr(expense, 'category_name', ''),
            'amount': int(getattr(expense, 'amount', 0) or 0),
        }

    @staticmethod
    def _serialize_registration(registration):
        return {
            'id': getattr(registration, 'id', None),
            'customer_name': getattr(registration, 'customer_name', ''),
            'registration_date': getattr(registration, 'registration_date', ''),
            'course_name': getattr(registration, 'course_name', ''),
            'income_total': int(getattr(registration, 'income_total', 0) or 0),
            'total_fee': int(getattr(registration, 'total_fee', 0) or 0),
        }

    def _export_dashboard_analytics(self):
        if self.export_service is None:
            QMessageBox.warning(self, 'خروجی تحلیل', 'سرویس خروجی اکسل در دسترس نیست.')
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            'انتخاب محل ذخیره تحلیل داشبورد',
            '',
            'Excel Files (*.xlsx)',
        )
        if not file_path:
            return

        try:
            destination = self.export_service.export_dashboard_analytics_to_excel(
                Path(file_path),
                self._current_dashboard_export_payload,
            )
        except Exception as exc:
            QMessageBox.warning(self, 'خروجی تحلیل', str(exc))
            return

        QMessageBox.information(
            self,
            'خروجی تحلیل',
            f'گزارش تحلیل داشبورد با موفقیت ذخیره شد\n{destination}',
        )

    def _refresh_ai_outputs(self):
        if self.ai_service is None:
            self._set_ai_controls_enabled(False, 'AI service در دسترس نیست.')
            self.ai_insights_text.setHtml('<p>AI service در دسترس نیست.</p>')
            return
        self._set_ai_controls_enabled(False, 'در حال دریافت تحلیل AI...')

        try:
            result = self.ai_service.generate_insights(self._current_dashboard_export_payload)
        except Exception as exc:
            self._set_ai_controls_enabled(False, f'خطای ارتباط با AI: {exc}')
            self.ai_insights_text.setHtml(f'<p>خطا در تحلیل AI: {escape(str(exc))}</p>')
            return

        self._latest_ai_result = result
        self._current_dashboard_export_payload['insights'] = result.get('insights') or []
        self._current_dashboard_export_payload['recommendations'] = result.get('recommendations') or []
        self._current_dashboard_export_payload['ai_report'] = result.get('report') or {}
        self._current_dashboard_export_payload['ai_source'] = result.get('source') or 'LOCAL'

        self._refresh_ai_ui_state()
        self._ai_html_feed = []
        report_html = self._render_structured_report_html(result)
        self._append_ai_html_message('assistant', 'AI Analysis', report_html)

    def _refresh_ai_ui_state(self):
        if self.ai_service is None:
            self._set_ai_controls_enabled(False, 'AI service در دسترس نیست.')
            return

        state = self.ai_service.get_connection_state()
        if state == 'CONNECTED':
            self._set_ai_controls_enabled(True)
            return

        if state == 'RECONNECTING':
            self._set_ai_controls_enabled(False, 'اتصال AI در پس زمینه در حال انجام است...')
            return

        reason = self.ai_service.last_api_error or 'موتور تحلیل محلی در حال آماده سازی است.'
        self._set_ai_controls_enabled(False, reason)

    def _ask_ai_query(self):
        if self.ai_service is None:
            QMessageBox.warning(self, 'پرسش AI', 'سرویس AI در دسترس نیست.')
            return
        if not self.btn_ai_query.isEnabled():
            QMessageBox.warning(self, 'پرسش AI', 'موتور تحلیل محلی آماده نیست.')
            return

        query = self.ai_query_input.text().strip()
        if not query:
            return

        self._append_ai_html_message('user', 'You', f'<p>{escape(query)}</p>')

        try:
            answer = self.ai_service.answer_query(query, self._current_dashboard_export_payload)
        except Exception as exc:
            QMessageBox.warning(self, 'پرسش AI', str(exc))
            return

        answer_text = escape(str(answer.get('answer', '')))
        answer_source = escape(str(answer.get('source', 'LOCAL')))
        reasoning_steps = answer.get('reasoning_steps') or []
        recommendations = answer.get('recommendations') or []
        html = [f'<p><b>Answer:</b> {answer_text}</p>', f'<p><b>Source:</b> {answer_source}</p>']
        if reasoning_steps:
            html.append('<p><b>Reasoning Steps:</b></p><ol>')
            for item in reasoning_steps[:6]:
                html.append(f'<li>{escape(str(item))}</li>')
            html.append('</ol>')
        if recommendations:
            html.append('<p><b>Recommendations:</b></p><ul>')
            for item in recommendations[:4]:
                html.append(f'<li>{escape(str(item))}</li>')
            html.append('</ul>')

        self._append_ai_html_message('assistant', 'AI Assistant', ''.join(html))
        self.ai_query_input.clear()

    def _export_ai_excel_report(self):
        if self.ai_service is None:
            QMessageBox.warning(self, 'گزارش AI', 'سرویس AI در دسترس نیست.')
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            'انتخاب محل ذخیره گزارش حرفه ای Excel',
            '',
            'Excel Files (*.xlsx)',
        )
        if not file_path:
            return
        try:
            destination = self.ai_service.generate_professional_report(
                self._current_dashboard_export_payload,
                'excel',
                Path(file_path),
            )
        except Exception as exc:
            QMessageBox.warning(self, 'گزارش AI', str(exc))
            return
        QMessageBox.information(self, 'گزارش AI', f'گزارش Excel ذخیره شد\n{destination}')

    def _export_ai_pdf_report(self):
        if self.ai_service is None:
            QMessageBox.warning(self, 'گزارش AI', 'سرویس AI در دسترس نیست.')
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            'انتخاب محل ذخیره گزارش حرفه ای PDF',
            '',
            'PDF Files (*.pdf)',
        )
        if not file_path:
            return
        try:
            destination = self.ai_service.generate_professional_report(
                self._current_dashboard_export_payload,
                'pdf',
                Path(file_path),
            )
        except Exception as exc:
            QMessageBox.warning(self, 'گزارش AI', str(exc))
            return
        QMessageBox.information(self, 'گزارش AI', f'گزارش PDF ذخیره شد\n{destination}')

    def _open_monthly_export_dialog(self):
        if self.ai_service is None:
            QMessageBox.warning(self, 'خروجی ماهانه', 'سرویس تحلیل محلی در دسترس نیست.')
            return

        years = sorted(self._collect_years())
        today = today_jalali()

        if not years:
            years = [today.year]

        dialog = QDialog(self)
        dialog.setWindowTitle('خروجی ماهانه')
        dialog.setModal(True)

        root = QVBoxLayout(dialog)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        hint = QLabel('ماه موردنظر را انتخاب کنید و فرمت خروجی را تعیین کنید.')
        hint.setWordWrap(True)
        root.addWidget(hint)

        period_row = QHBoxLayout()
        period_row.addWidget(QLabel('سال'))
        year_combo = QComboBox(dialog)
        for year in years:
            year_combo.addItem(str(year), year)
        current_year = self.year_filter.currentData() if self.year_filter.currentData() is not None else years[-1]
        for idx in range(year_combo.count()):
            if year_combo.itemData(idx) == current_year:
                year_combo.setCurrentIndex(idx)
                break

        period_row.addWidget(year_combo)
        period_row.addWidget(QLabel('ماه'))
        month_combo = QComboBox(dialog)
        for month in range(1, 13):
            month_combo.addItem(f'{month:02d}', month)
        current_month = self.month_filter.currentData() if self.month_filter.currentData() is not None else today.month
        if 1 <= int(current_month) <= 12:
            month_combo.setCurrentIndex(int(current_month) - 1)
        period_row.addWidget(month_combo)
        root.addLayout(period_row)

        fmt_row = QHBoxLayout()
        cb_excel = QCheckBox('Excel', dialog)
        cb_excel.setChecked(True)
        cb_pdf = QCheckBox('PDF', dialog)
        cb_pdf.setChecked(True)
        fmt_row.addWidget(cb_excel)
        fmt_row.addWidget(cb_pdf)
        fmt_row.addStretch()
        root.addLayout(fmt_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dialog)
        root.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() != QDialog.Accepted:
            return

        if not cb_excel.isChecked() and not cb_pdf.isChecked():
            QMessageBox.warning(dialog, 'خروجی ماهانه', 'حداقل یک فرمت خروجی انتخاب کنید.')
            return

        year = int(year_combo.currentData())
        month = int(month_combo.currentData())
        try:
            paths = self.ai_service.export_monthly_reports(
                self._current_dashboard_export_payload,
                year,
                month,
                export_excel=cb_excel.isChecked(),
                export_pdf=cb_pdf.isChecked(),
            )
        except Exception as exc:
            QMessageBox.warning(self, 'خروجی ماهانه', str(exc))
            return

        rendered = '\n'.join(str(path) for path in paths)
        QMessageBox.information(
            self,
            'خروجی ماهانه',
            f'گزارش ماه {year}/{month:02d} با موفقیت ذخیره شد\n{rendered}',
        )

    def _render_structured_report_html(self, result: dict) -> str:
        report = result.get('report') or {}
        key_metrics = report.get('key_metrics') or {}
        risks = report.get('risks') or []
        trends = report.get('trends') or []
        recommendations = report.get('recommendations') or []
        reasoning_steps = report.get('reasoning_steps') or []
        api_commentary = (result.get('api_commentary') or '').strip()
        source = escape(str(result.get('source', 'LOCAL')))

        parts = [
            '<h3>Summary</h3>',
            f'<p><b>Source:</b> {source}</p>',
            f"<p>{escape(str(report.get('summary', '-')))}</p>",
            '<h3>Key Metrics</h3>',
            '<table border="0" cellspacing="0" cellpadding="4">',
        ]
        for key, value in key_metrics.items():
            parts.append(
                f"<tr><td><b>{escape(str(key))}</b></td><td>{escape(str(value))}</td></tr>"
            )
        parts.append('</table>')

        parts.append('<h3>Risks</h3><ul>')
        for risk in risks:
            parts.append(
                f"<li><b>{escape(str(risk.get('title', '-')))}</b> | "
                f"Severity: {escape(str(risk.get('severity', '-')))} | "
                f"Count: {escape(str(risk.get('count', 0)))}</li>"
            )
        parts.append('</ul>')

        parts.append('<h3>Trends</h3><ul>')
        for trend in trends:
            parts.append(
                f"<li>{escape(str(trend.get('metric', '-')))}: "
                f"{escape(str(trend.get('change_pct', 0)))}%</li>"
            )
        parts.append('</ul>')

        parts.append('<h3>Recommendations</h3><ul>')
        for item in recommendations:
            parts.append(f'<li>{escape(str(item))}</li>')
        parts.append('</ul>')

        parts.append('<h3>Reasoning</h3><ol>')
        for item in reasoning_steps:
            parts.append(f'<li>{escape(str(item))}</li>')
        parts.append('</ol>')

        if api_commentary:
            parts.append('<h3>GapCode Commentary</h3>')
            parts.append(f'<p>{escape(api_commentary)}</p>')

        return ''.join(parts)

    def _append_ai_html_message(self, role: str, title: str, body_html: str):
        if role == 'user':
            bg = '#eef6ff'
            border = '#bfdbfe'
        else:
            bg = '#f8fafc'
            border = '#d1d5db'

        card = (
            f'<div style="margin:8px 0;padding:10px;border:1px solid {border};'
            f'border-radius:10px;background:{bg};">'
            f'<div style="font-weight:700;margin-bottom:6px;">{escape(title)}</div>'
            f'{body_html}'
            '</div>'
        )
        self._ai_html_feed.append(card)
        self.ai_insights_text.setHtml(''.join(self._ai_html_feed))
        self.ai_insights_text.verticalScrollBar().setValue(
            self.ai_insights_text.verticalScrollBar().maximum()
        )

    def _set_ai_controls_enabled(self, enabled: bool, reason: str = ''):
        self.btn_generate_ai.setEnabled(enabled)
        self.btn_ai_query.setEnabled(enabled)
        self.ai_query_input.setEnabled(enabled)
        self.btn_export_ai_excel.setEnabled(enabled)
        self.btn_export_ai_pdf.setEnabled(enabled)
        self.btn_monthly_export.setEnabled(enabled)

        if enabled:
            self.ai_status_badge.setText('AI Status: Local Engine Ready')
            self.ai_connection_banner.hide()
            return

        self.ai_status_badge.setText('AI Status: Local Engine Unavailable')
        if reason:
            self.ai_connection_banner.setText(f'AI Guard: {escape(str(reason))}')
            self.ai_connection_banner.show()
        else:
            self.ai_connection_banner.hide()

    def _date_matches_period(self, value, year, month):
        if year is None:
            return True

        parts = self._extract_date_parts(value)
        if not parts:
            return False

        if parts[0] != int(year):
            return False
        if month is None:
            return True
        return parts[1] == int(month)

    @staticmethod
    def _extract_date_parts(value):
        if not value:
            return None
        try:
            normalized = normalize_jalali_date_text(value)
        except ValueError:
            return None

        parts = normalized.split('/')
        if len(parts) != 3:
            return None

        try:
            return int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return None

    @staticmethod
    def _growth_text(current, previous):
        if previous == 0:
            return 'تغییر: -' if current == 0 else 'تغییر: +100%'
        delta = ((current - previous) / abs(previous)) * 100
        sign = '+' if delta >= 0 else ''
        return f'تغییر: {sign}{delta:.1f}%'

    @staticmethod
    def _apply_growth_style(label: QLabel, text: str):
        label.setText(text)
        if text.startswith('تغییر: +'):
            label.setObjectName('moduleGrowthUp')
        elif text.startswith('تغییر: -') and text != 'تغییر: -':
            label.setObjectName('moduleGrowthDown')
        else:
            label.setObjectName('moduleGrowthNeutral')
        label.style().unpolish(label)
        label.style().polish(label)

    def _apply_status_style(self, item: QTableWidgetItem, status_key: str):
        fg, bg = self.STATUS_COLORS.get(status_key, ('#475569', '#f8fafc'))
        item.setForeground(QColor(fg))
        item.setBackground(QColor(bg))

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        try:
            normalized = normalize_jalali_date_text(value)
            return jalali_to_gregorian(normalized)
        except ValueError:
            return None
