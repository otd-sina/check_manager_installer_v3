import logging

from config import (
    AI_AUTO_MONTHLY_EXPORT_ENABLED,
    AI_AUTO_MONTHLY_EXPORT_FORMATS,
    AI_AUTO_MONTHLY_EXPORT_MONTH_OFFSET,
    AI_AUTORECONNECT_ENABLED,
    AI_HEALTHCHECK_TTL_SEC,
    AI_MAX_RETRIES,
    AI_RECONNECT_BACKOFF_MAX_SEC,
    AI_RECONNECT_INTERVAL_SEC,
    AI_RETRY_BACKOFF_SEC,
    AI_TIMEOUT_SEC,
    APP_DATA_DIR,
    DB_PATH,
    LOG_LEVEL,
    LOG_DIR,
)
from core.logging_config import setup_logging
from database.db import Database
from services.ai_service import AIService
from services.backup_service import BackupService
from services.check_service import CheckService
from services.debt_service import DebtService
from services.expense_service import ExpenseService
from services.export_service import ExportService
from services.registration_service import RegistrationService


RESTART_REQUIRED_MESSAGE = (
    'Database restore completed, but reloading application state failed. '
    'Please restart the application.'
)


class _RestartRequiredDatabaseProxy:
    """Fails fast after a restore-reload failure so stale state is never used."""

    def __init__(self, message: str):
        self._message = message

    def __getattr__(self, _name: str):
        raise RuntimeError(self._message)


class AppContext:
    """Central place for application services and shared dependencies."""

    def __init__(self):
        setup_logging(LOG_DIR, level=LOG_LEVEL)
        self.logger = logging.getLogger(__name__)
        self.logger.info(
            'App context init started | data_dir=%s | db_path=%s | log_dir=%s',
            APP_DATA_DIR,
            DB_PATH,
            LOG_DIR,
        )

        self.db = Database(DB_PATH)
        self.check_service = CheckService(self.db)
        self.debt_service = DebtService(self.db)
        self.expense_service = ExpenseService(self.db)
        self.registration_service = RegistrationService(self.db)
        self.export_service = ExportService(
            self.check_service,
            self.expense_service,
            self.registration_service,
            self.debt_service,
        )
        self.ai_service = AIService(
            self.check_service,
            self.expense_service,
            self.registration_service,
            self.export_service,
            timeout_sec=AI_TIMEOUT_SEC,
            healthcheck_ttl_sec=AI_HEALTHCHECK_TTL_SEC,
            max_retries=AI_MAX_RETRIES,
            retry_backoff_sec=AI_RETRY_BACKOFF_SEC,
            autoreconnect_enabled=AI_AUTORECONNECT_ENABLED,
            reconnect_interval_sec=AI_RECONNECT_INTERVAL_SEC,
            reconnect_backoff_max_sec=AI_RECONNECT_BACKOFF_MAX_SEC,
        )
        self.backup_service = BackupService(DB_PATH)

        try:
            self.ai_service.force_reconnect()
            self.logger.info(
                'Local analysis engine initialized: state=%s',
                self.ai_service.get_connection_state(),
            )
        except Exception as exc:
            self.logger.exception('Local analysis engine failed to initialize: %s', exc)

        try:
            if AI_AUTO_MONTHLY_EXPORT_ENABLED:
                bootstrap_payload = self._build_dashboard_payload_for_auto_export()
                exported_paths = self.ai_service.run_auto_monthly_export(
                    bootstrap_payload,
                    enabled=True,
                    formats_text=AI_AUTO_MONTHLY_EXPORT_FORMATS,
                    month_offset=AI_AUTO_MONTHLY_EXPORT_MONTH_OFFSET,
                )
                if exported_paths:
                    self.logger.info(
                        'Startup auto monthly export saved: %s',
                        ', '.join(str(path.name) for path in exported_paths),
                    )
                else:
                    self.logger.info('Startup auto monthly export skipped (already up to date or no data).')
            else:
                self.logger.info('Startup auto monthly export is disabled by configuration.')
        except Exception as exc:
            self.logger.exception('Startup auto monthly export failed: %s', exc)

        self.logger.info('App context initialized successfully.')

    def _release_database_handles(self):
        close_connections = getattr(self.db, 'close_open_connections', None)
        if callable(close_connections):
            close_connections()

    def prepare_for_backup(self):
        self._release_database_handles()

    def prepare_for_restore(self):
        self._release_database_handles()

    def reload_database(self):
        close_connections = getattr(self.db, 'close_open_connections', None)
        if callable(close_connections):
            close_connections()

        self.db = Database(DB_PATH)
        self.check_service.db = self.db
        self.debt_service.db = self.db
        self.expense_service.db = self.db
        self.registration_service.db = self.db
        self.registration_service.customer_service.db = self.db

    def reload_database_after_restore(self):
        try:
            self.reload_database()
        except Exception:
            self.logger.exception('Database restore succeeded but state reload failed.')
            invalid_db = _RestartRequiredDatabaseProxy(RESTART_REQUIRED_MESSAGE)
            self.db = invalid_db
            self.check_service.db = invalid_db
            self.debt_service.db = invalid_db
            self.expense_service.db = invalid_db
            self.registration_service.db = invalid_db
            self.registration_service.customer_service.db = invalid_db
            raise RuntimeError(RESTART_REQUIRED_MESSAGE)

    def shutdown(self):
        self.logger.info('Application context shutdown completed.')

    def _build_dashboard_payload_for_auto_export(self) -> dict:
        checks = self.check_service.list_checks()
        expenses = self.expense_service.list_expenses()
        registrations = self.registration_service.list_all()

        summary = {
            'incomes': sum(int(getattr(item, 'income_total', 0) or 0) for item in registrations),
            'expenses': sum(int(getattr(item, 'amount', 0) or 0) for item in expenses),
            'net': 0,
            'registrations_count': len(registrations),
            'checks_count': len(checks),
            'checks_amount': sum(int(getattr(item, 'amount', 0) or 0) for item in checks),
        }
        summary['net'] = int(summary['incomes']) - int(summary['expenses'])

        monthly_totals: dict[str, dict[str, int]] = {}
        for registration in registrations:
            date_text = str(getattr(registration, 'registration_date', '') or '').strip()
            period = date_text[:7] if len(date_text) >= 7 else ''
            if not period:
                continue
            cell = monthly_totals.setdefault(period, {'income': 0, 'expense': 0, 'registrations': 0, 'checks_count': 0, 'checks_amount': 0})
            cell['income'] += int(getattr(registration, 'income_total', 0) or 0)
            cell['registrations'] += 1

        for expense in expenses:
            date_text = str(getattr(expense, 'expense_date', '') or '').strip()
            period = date_text[:7] if len(date_text) >= 7 else ''
            if not period:
                continue
            cell = monthly_totals.setdefault(period, {'income': 0, 'expense': 0, 'registrations': 0, 'checks_count': 0, 'checks_amount': 0})
            cell['expense'] += int(getattr(expense, 'amount', 0) or 0)

        for check in checks:
            date_text = str(getattr(check, 'due_date', '') or '').strip()
            period = date_text[:7] if len(date_text) >= 7 else ''
            if not period:
                continue
            cell = monthly_totals.setdefault(period, {'income': 0, 'expense': 0, 'registrations': 0, 'checks_count': 0, 'checks_amount': 0})
            cell['checks_count'] += 1
            cell['checks_amount'] += int(getattr(check, 'amount', 0) or 0)

        monthly_analytics = []
        for period in sorted(monthly_totals.keys()):
            row = monthly_totals[period]
            monthly_analytics.append(
                {
                    'period': period,
                    'income': int(row['income']),
                    'expense': int(row['expense']),
                    'net': int(row['income']) - int(row['expense']),
                    'registrations': int(row['registrations']),
                    'checks_count': int(row['checks_count']),
                    'checks_amount': int(row['checks_amount']),
                }
            )

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

        def _serialize_expense(expense):
            return {
                'id': getattr(expense, 'id', None),
                'title': getattr(expense, 'title', ''),
                'expense_date': getattr(expense, 'expense_date', ''),
                'category_name': getattr(expense, 'category_name', ''),
                'amount': int(getattr(expense, 'amount', 0) or 0),
            }

        def _serialize_registration(registration):
            return {
                'id': getattr(registration, 'id', None),
                'customer_name': getattr(registration, 'customer_name', ''),
                'registration_date': getattr(registration, 'registration_date', ''),
                'course_name': getattr(registration, 'course_name', ''),
                'income_total': int(getattr(registration, 'income_total', 0) or 0),
                'total_fee': int(getattr(registration, 'total_fee', 0) or 0),
            }

        return {
            'period_label': 'نمای کلی',
            'filters': {'year': None, 'month': None},
            'summary': summary,
            'growth': {
                'incomes': '-',
                'expenses': '-',
                'registrations': '-',
                'checks': '-',
            },
            'monthly_analytics': monthly_analytics,
            'category_breakdown': [],
            'monthly_comparison': [],
            'upcoming_risks': [],
            'checks': [_serialize_check(item) for item in checks],
            'expenses_rows': [_serialize_expense(item) for item in expenses],
            'registrations_rows': [_serialize_registration(item) for item in registrations],
        }
