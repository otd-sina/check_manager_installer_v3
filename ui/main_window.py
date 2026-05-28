import logging
import sys
from pathlib import Path

from PySide6.QtCore import QIODevice, QFile, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.error_handler import report_exception
from services.debt_service import DebtService
from ui.add_check_dialog import AddCheckDialog
from ui.backup_import_page import BackupImportPage
from ui.check_alerts import CheckAlertManager
from ui.checks_table_widget import ChecksTableWidget
from ui.dashboard_page import DashboardPage
from ui.debt_page import DebtPage
from ui.expenses_page import ExpensesPage
from ui.navigation_map import (
    NAVIGATION_ITEMS,
    PAGE_BACKUP,
    PAGE_CHECKS,
    PAGE_DASHBOARD,
    PAGE_DEBTS,
    PAGE_EXPENSES,
    PAGE_REGISTRATIONS,
)
from ui.registrations_page import RegistrationsPage


logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self.check_service = context.check_service
        self.debt_service = DebtService(self.check_service.db)
        self.expense_service = context.expense_service
        self.export_service = context.export_service
        self.ai_service = context.ai_service
        self.backup_service = context.backup_service
        self._navigation_items = []
        self._page_index_by_key = {}
        self._page_key_by_index = {}
        self._page_action_map = {}

        self.setWindowTitle('مدیریت چک')
        self._setup_ui()
        self._setup_refresh_scheduler()
        self._setup_shortcuts()
        self._setup_alerts()
        self._apply_local_styles()
        self.refresh_views()

    @staticmethod
    def base_path() -> Path:
        if getattr(sys, 'frozen', False):
            return Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))
        return Path(__file__).resolve().parent.parent

    @classmethod
    def resource_path(cls, *parts: str) -> Path:
        return cls.base_path().joinpath(*parts)

    def _load_stylesheet(self, relative_path: str) -> str:
        resource_path = f":/{relative_path.lstrip('/')}"
        file = QFile(resource_path)
        if file.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
            try:
                return bytes(file.readAll()).decode('utf-8')
            finally:
                file.close()

        path = self.resource_path(relative_path)
        if not path.exists():
            return ''
        return path.read_text(encoding='utf-8')

    def _apply_local_styles(self):
        local_qss = self._load_stylesheet('styles/main.qss')
        if local_qss:
            self.setStyleSheet(local_qss)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        shell_layout = QHBoxLayout(central)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName('navigationSidebar')
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 20, 16, 20)
        sidebar_layout.setSpacing(8)

        self.btn_nav_dashboard = QPushButton('داشبورد')
        self.btn_nav_registrations = QPushButton('ثبت نام / درآمد')
        self.btn_nav_checks = QPushButton('چک ها')
        self.btn_nav_expenses = QPushButton('هزینه ها')
        self.btn_nav_debts = QPushButton('بدهی ها')
        self.btn_nav_backup = QPushButton('پشتیبان گیری')
        self.btn_nav_dashboard.setCheckable(True)
        self.btn_nav_registrations.setCheckable(True)
        self.btn_nav_checks.setCheckable(True)
        self.btn_nav_expenses.setCheckable(True)
        self.btn_nav_debts.setCheckable(True)
        self.btn_nav_backup.setCheckable(True)

        sidebar_layout.addWidget(self.btn_nav_dashboard)
        sidebar_layout.addWidget(self.btn_nav_registrations)
        sidebar_layout.addWidget(self.btn_nav_checks)
        sidebar_layout.addWidget(self.btn_nav_expenses)
        sidebar_layout.addWidget(self.btn_nav_debts)
        sidebar_layout.addWidget(self.btn_nav_backup)
        sidebar_layout.addStretch()

        shell_layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        shell_layout.addWidget(self.stack, 1)

        self.dashboard_page = DashboardPage(
            self.check_service,
            self.expense_service,
            self.context.registration_service,
            self.export_service,
            self.ai_service,
            self.debt_service,
        )
        self.checks_page = QWidget()
        self.registrations_page = RegistrationsPage(
            self.context.registration_service,
            self.expense_service,
            self.export_service,
        )
        self.expenses_page = ExpensesPage(self.expense_service, self.export_service)
        self.debts_page = DebtPage(self.debt_service)
        self.backup_page = BackupImportPage(
            self.backup_service,
            before_backup_callback=self.context.prepare_for_backup,
            before_restore_callback=self.context.prepare_for_restore,
            after_restore_callback=self.context.reload_database_after_restore,
        )
        self._setup_checks_page()
        self._setup_navigation_map()
        self._setup_page_action_map()
        self.backup_page.backupImported.connect(self._on_backup_imported)
        self._show_page(PAGE_DASHBOARD)

    def _setup_navigation_map(self):
        pages_by_key = {
            PAGE_DASHBOARD: self.dashboard_page,
            PAGE_REGISTRATIONS: self.registrations_page,
            PAGE_CHECKS: self.checks_page,
            PAGE_EXPENSES: self.expenses_page,
            PAGE_DEBTS: self.debts_page,
            PAGE_BACKUP: self.backup_page,
        }
        self._navigation_items = [
            (
                item.page_key,
                getattr(self, item.button_attr),
                pages_by_key[item.page_key],
                item.shortcut,
            )
            for item in NAVIGATION_ITEMS
        ]
        self._page_index_by_key.clear()
        self._page_key_by_index.clear()

        for page_key, button, page_widget, _ in self._navigation_items:
            page_index = self.stack.addWidget(page_widget)
            self._page_index_by_key[page_key] = page_index
            self._page_key_by_index[page_index] = page_key
            button.clicked.connect(lambda _checked=False, key=page_key: self._show_page(key))

    def _setup_page_action_map(self):
        self._page_action_map = {
            PAGE_CHECKS: {
                'add': self.on_add_check,
                'edit': self.checks_table_widget.edit_selected,
                'delete': self.checks_table_widget.delete_selected,
                'export': self.on_export_excel,
                'mark_returned': self.checks_table_widget.mark_selected_returned,
            },
            PAGE_REGISTRATIONS: {
                'add': self.registrations_page.trigger_add_registration,
                'edit': self.registrations_page.trigger_edit_registration,
                'delete': self.registrations_page.trigger_delete_registration,
                'export': self.registrations_page.trigger_export_registrations,
            },
            PAGE_EXPENSES: {
                'add': self.expenses_page.trigger_add_expense,
                'edit': self.expenses_page.expenses_table_widget.edit_selected,
                'delete': self.expenses_page.expenses_table_widget.delete_selected,
                'export': self.expenses_page.trigger_export_expenses,
            },
            PAGE_DEBTS: {
                'add': self.debts_page.trigger_add_debt,
                'edit': self.debts_page.trigger_edit_debt,
                'delete': self.debts_page.trigger_delete_debt,
            },
        }

    def _setup_checks_page(self):
        main_layout = QVBoxLayout(self.checks_page)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        header_panel = QFrame(self.checks_page)
        header_panel.setObjectName('pageTopFixedPanel')
        header_layout = QVBoxLayout(header_panel)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(10)

        title = QLabel('مدیریت چک ها')
        title.setObjectName('pageTitle')
        subtitle = QLabel('ثبت، ویرایش، پیگیری و خروجی گیری رکوردهای چک')
        subtitle.setObjectName('pageSubtitle')
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        self.btn_add = QPushButton('افزودن چک')
        self.btn_edit = QPushButton('ویرایش')
        self.btn_delete = QPushButton('حذف')
        self.btn_mark_returned = QPushButton('برگشتی')
        self.btn_export = QPushButton('خروجی اکسل')

        self.btn_add.setToolTip('Ctrl+N')
        self.btn_edit.setToolTip('Ctrl+E')
        self.btn_delete.setToolTip('Delete')
        self.btn_export.setToolTip('Ctrl+Shift+E')

        button_layout.addWidget(self.btn_add)
        button_layout.addWidget(self.btn_edit)
        button_layout.addWidget(self.btn_delete)
        button_layout.addWidget(self.btn_mark_returned)
        button_layout.addStretch()
        button_layout.addWidget(self.btn_export)
        header_layout.addLayout(button_layout)
        main_layout.addWidget(header_panel)

        self.checks_table_widget = ChecksTableWidget(self.check_service)
        main_layout.addWidget(self.checks_table_widget, 1)

        self.btn_add.clicked.connect(self.on_add_check)
        self.btn_edit.clicked.connect(self.checks_table_widget.edit_selected)
        self.btn_delete.clicked.connect(self.checks_table_widget.delete_selected)
        self.btn_mark_returned.clicked.connect(self.checks_table_widget.mark_selected_returned)
        self.btn_export.clicked.connect(self.on_export_excel)

        self.checks_table_widget.checksChanged.connect(self.request_refresh)
        self.checks_table_widget.checksChanged.connect(self._on_checks_changed)
        self.registrations_page.registrationsChanged.connect(self.request_refresh)
        self.expenses_page.expensesChanged.connect(self.request_refresh)
        self.debts_page.debtsChanged.connect(self.request_refresh)

    def _setup_refresh_scheduler(self):
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(self.refresh_views)

    def _setup_shortcuts(self):
        for page_key, _button, _page_widget, shortcut in self._navigation_items:
            QShortcut(QKeySequence(shortcut), self, activated=lambda key=page_key: self._show_page(key))
        QShortcut(QKeySequence('Ctrl+N'), self, activated=self._shortcut_add)
        QShortcut(QKeySequence('Ctrl+E'), self, activated=self._shortcut_edit)
        QShortcut(QKeySequence('Delete'), self, activated=self._shortcut_delete)
        QShortcut(QKeySequence('Ctrl+Shift+E'), self, activated=self._shortcut_export)
        QShortcut(QKeySequence('Ctrl+R'), self, activated=self._shortcut_mark_returned)
        QShortcut(QKeySequence('F5'), self, activated=self.refresh_views)

    def _setup_alerts(self):
        self.alert_manager = CheckAlertManager(self.check_service, self)
        self.alert_manager.navigateToCheck.connect(self.navigate_to_check)
        self.alert_manager.start()

    def _on_checks_changed(self):
        self.alert_manager.scan_now()

    def _on_backup_imported(self):
        self.refresh_views()
        self.alert_manager.scan_now()

    def _show_page(self, page_key: str):
        page_index = self._page_index_by_key.get(page_key)
        if page_index is None:
            logger.warning('Unknown page key requested: %s', page_key)
            return

        self.stack.setCurrentIndex(page_index)
        for key, button, _page_widget, _shortcut in self._navigation_items:
            button.setChecked(key == page_key)

    def _current_page_key(self) -> str | None:
        return self._page_key_by_index.get(self.stack.currentIndex())

    def _trigger_page_action(self, action_name: str) -> bool:
        page_key = self._current_page_key()
        if not page_key:
            return False

        page_actions = self._page_action_map.get(page_key, {})
        action = page_actions.get(action_name)
        if not action:
            return False

        action()
        return True

    def request_refresh(self):
        self._refresh_timer.start()

    def refresh_views(self):
        self.checks_table_widget.refresh()
        self.registrations_page.refresh()
        self.expenses_page.refresh()
        self.debts_page.refresh()
        self.dashboard_page.refresh()

    def navigate_to_check(self, check_id: int):
        self._show_page(PAGE_CHECKS)
        self.checks_table_widget.refresh()
        focused = self.checks_table_widget.focus_check(check_id)
        self.raise_()
        self.activateWindow()

        if not focused:
            QMessageBox.information(self, 'هشدار', 'چک مربوط به یادآوری یافت نشد.')

    def on_add_check(self):
        dialog = AddCheckDialog(self)
        if not dialog.exec():
            return

        try:
            self.check_service.add_check(dialog.get_check())
        except Exception as exc:
            report_exception(
                self,
                exc,
                title='خطای ثبت چک',
                context='Add check failed',
                logger_=logger,
            )
            return

        self.request_refresh()
        self.alert_manager.scan_now()

    def on_export_excel(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            'انتخاب محل ذخیره خروجی اکسل',
            '',
            'Excel Files (*.xlsx)',
        )
        if not file_path:
            return

        try:
            result_path = self.export_service.export_checks_to_excel(Path(file_path))
        except Exception as exc:
            report_exception(
                self,
                exc,
                title='خروجی اکسل',
                context='Check export failed',
                logger_=logger,
            )
            return

        QMessageBox.information(
            self,
            'خروجی اکسل',
            f'خروجی با موفقیت ذخیره شد\n{result_path}',
        )

    def _shortcut_add(self):
        if self._trigger_page_action('add'):
            return
        self._show_page(PAGE_CHECKS)
        self._trigger_page_action('add')

    def _shortcut_edit(self):
        self._trigger_page_action('edit')

    def _shortcut_delete(self):
        self._trigger_page_action('delete')

    def _shortcut_export(self):
        self._trigger_page_action('export')

    def _shortcut_mark_returned(self):
        self._trigger_page_action('mark_returned')
