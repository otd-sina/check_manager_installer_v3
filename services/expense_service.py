from __future__ import annotations

from datetime import date
import logging
from typing import Iterator, Optional

from database.db import Database
from models.expense_category_model import ExpenseCategory
from models.expense_model import Expense
from utils.date_utils import normalize_jalali_date_text, today_jalali


logger = logging.getLogger(__name__)


class ExpenseService:
    PAYMENT_METHODS = {
        'CASH': 'نقدی',
        'CARD': 'کارتخوان',
        'TRANSFER': 'انتقال بانکی',
        'CHEQUE': 'چک',
        'ONLINE': 'آنلاین',
        'OTHER': 'سایر',
    }

    def __init__(self, db: Database):
        self.db = db

    def add_category(self, name: str, description: str = '') -> int:
        normalized_name = self._normalize_name(name)
        description = (description or '').strip()
        self._ensure_category_unique(normalized_name)
        category_id = self.db.execute(
            'INSERT INTO expense_categories(name, description) VALUES(?, ?)',
            (normalized_name, description),
        )
        logger.info('Expense category created: id=%s name=%s', category_id, normalized_name)
        return category_id

    def update_category(self, category_id: int, name: str, description: str = ''):
        normalized_name = self._normalize_name(name)
        description = (description or '').strip()
        self._ensure_category_exists(category_id)
        self._ensure_category_unique(normalized_name, excluded_id=category_id)
        self.db.execute(
            'UPDATE expense_categories SET name = ?, description = ? WHERE id = ?',
            (normalized_name, description, category_id),
        )
        logger.info('Expense category updated: id=%s name=%s', category_id, normalized_name)

    def delete_category(self, category_id: int):
        self._ensure_category_exists(category_id)

        usage_rows = self.db.fetchall(
            'SELECT COUNT(*) FROM expenses WHERE category_id = ?',
            (category_id,),
        )
        if usage_rows[0][0] > 0:
            raise ValueError('این دسته بندی در هزینه ها استفاده شده و قابل حذف نیست.')

        category_rows = self.db.fetchall('SELECT COUNT(*) FROM expense_categories')
        if category_rows[0][0] <= 1:
            raise ValueError('حداقل یک دسته بندی باید در سیستم باقی بماند.')

        self.db.execute('DELETE FROM expense_categories WHERE id = ?', (category_id,))
        logger.info('Expense category deleted: id=%s', category_id)

    def get_category(self, category_id: int) -> Optional[ExpenseCategory]:
        rows = self.db.fetchall(
            'SELECT id, name, description FROM expense_categories WHERE id = ?',
            (category_id,),
        )
        if not rows:
            return None
        return ExpenseCategory(id=rows[0][0], name=rows[0][1] or '', description=rows[0][2] or '')

    def list_categories(self) -> list[ExpenseCategory]:
        rows = self.db.fetchall(
            'SELECT id, name, description FROM expense_categories ORDER BY name COLLATE NOCASE ASC'
        )
        return [
            ExpenseCategory(id=row[0], name=row[1] or '', description=row[2] or '')
            for row in rows
        ]

    def get_category_usage(self) -> dict[int, int]:
        rows = self.db.fetchall(
            """
            SELECT category_id, COUNT(*)
            FROM expenses
            GROUP BY category_id
            """
        )
        return {int(category_id): int(total or 0) for category_id, total in rows}

    def add_expense(self, expense: Expense) -> int:
        normalized = self._validate_and_normalize_expense(expense)
        query = """
            INSERT INTO expenses(
                title, amount, expense_date, category_id, payment_method,
                reference_check_id, vendor, notes, created_at, updated_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        params = (
            normalized.title,
            normalized.amount,
            normalized.expense_date,
            normalized.category_id,
            normalized.payment_method,
            normalized.reference_check_id,
            normalized.vendor,
            normalized.notes,
        )
        expense_id = self.db.execute(query, params)
        logger.info('Expense created: id=%s amount=%s date=%s', expense_id, normalized.amount, normalized.expense_date)
        return expense_id

    def update_expense(self, expense: Expense):
        if expense.id is None:
            raise ValueError('Expense id is required for update.')

        self._ensure_expense_exists(expense.id)
        normalized = self._validate_and_normalize_expense(expense)
        query = """
            UPDATE expenses
            SET title = ?, amount = ?, expense_date = ?, category_id = ?, payment_method = ?,
                reference_check_id = ?, vendor = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        params = (
            normalized.title,
            normalized.amount,
            normalized.expense_date,
            normalized.category_id,
            normalized.payment_method,
            normalized.reference_check_id,
            normalized.vendor,
            normalized.notes,
            expense.id,
        )
        self.db.execute(query, params)
        logger.info('Expense updated: id=%s amount=%s', expense.id, normalized.amount)

    def delete_expense(self, expense_id: int):
        self._ensure_expense_exists(expense_id)
        self.db.execute('DELETE FROM expenses WHERE id = ?', (expense_id,))
        logger.info('Expense deleted: id=%s', expense_id)

    def get_expense(self, expense_id: int) -> Optional[Expense]:
        rows = self.db.fetchall(
            """
            SELECT
                e.id, e.title, e.amount, e.expense_date, e.category_id,
                e.payment_method, c.name, e.reference_check_id, e.vendor, e.notes
            FROM expenses e
            JOIN expense_categories c ON c.id = e.category_id
            WHERE e.id = ?
            """,
            (expense_id,),
        )
        if not rows:
            return None
        return self._row_to_expense(rows[0])

    def list_expenses(
        self,
        search_text: str = '',
        category_id: Optional[int] = None,
        payment_method: str = '',
        from_date: str = '',
        to_date: str = '',
    ) -> list[Expense]:
        return list(
            self.iter_expenses(
                search_text=search_text,
                category_id=category_id,
                payment_method=payment_method,
                from_date=from_date,
                to_date=to_date,
            )
        )

    def iter_expenses(
        self,
        search_text: str = '',
        category_id: Optional[int] = None,
        payment_method: str = '',
        from_date: str = '',
        to_date: str = '',
        batch_size: int = 500,
    ) -> Iterator[Expense]:
        query, params = self._build_expense_query(
            search_text=search_text,
            category_id=category_id,
            payment_method=payment_method,
            from_date=from_date,
            to_date=to_date,
        )
        for row in self.db.iterate(query, tuple(params), batch_size=batch_size):
            yield self._row_to_expense(row)

    def _build_expense_query(
        self,
        search_text: str = '',
        category_id: Optional[int] = None,
        payment_method: str = '',
        from_date: str = '',
        to_date: str = '',
    ) -> tuple[str, list[object]]:
        query = """
            SELECT
                e.id, e.title, e.amount, e.expense_date, e.category_id,
                e.payment_method, c.name, e.reference_check_id, e.vendor, e.notes
            FROM expenses e
            JOIN expense_categories c ON c.id = e.category_id
            WHERE 1 = 1
        """
        params = []

        if category_id is not None:
            query += ' AND e.category_id = ?'
            params.append(category_id)

        normalized_method = self._normalize_payment_method(payment_method) if payment_method else ''
        if normalized_method:
            query += ' AND e.payment_method = ?'
            params.append(normalized_method)

        if from_date:
            query += ' AND e.expense_date >= ?'
            params.append(self._normalize_date(from_date))

        if to_date:
            query += ' AND e.expense_date <= ?'
            params.append(self._normalize_date(to_date))

        text = (search_text or '').strip().lower()
        if text:
            like = f'%{text}%'
            query += """
                AND (
                    lower(e.title) LIKE ?
                    OR lower(c.name) LIKE ?
                    OR lower(e.vendor) LIKE ?
                    OR lower(e.notes) LIKE ?
                    OR CAST(e.amount AS TEXT) LIKE ?
                    OR CAST(COALESCE(e.reference_check_id, '') AS TEXT) LIKE ?
                )
            """
            params.extend([like, like, like, like, like, like])

        query += ' ORDER BY e.expense_date DESC, e.id DESC'
        return query, params

    def build_report(self, from_date: str = '', to_date: str = '') -> dict:
        normalized_from = self._normalize_date(from_date) if from_date else ''
        normalized_to = self._normalize_date(to_date) if to_date else ''

        filters = []
        params: list[object] = []
        if normalized_from:
            filters.append('expense_date >= ?')
            params.append(normalized_from)
        if normalized_to:
            filters.append('expense_date <= ?')
            params.append(normalized_to)

        where_clause = 'WHERE ' + ' AND '.join(filters) if filters else ''

        total_rows = self.db.fetchall(
            f'SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM expenses {where_clause}',
            tuple(params),
        )
        total_amount = int(total_rows[0][0] or 0)
        records_count = int(total_rows[0][1] or 0)

        top_categories = self.db.fetchall(
            f"""
            SELECT c.name, COALESCE(SUM(e.amount), 0) AS total
            FROM expenses e
            JOIN expense_categories c ON c.id = e.category_id
            {where_clause}
            GROUP BY e.category_id, c.name
            ORDER BY total DESC, c.name ASC
            LIMIT 5
            """,
            tuple(params),
        )

        method_rows = self.db.fetchall(
            f"""
            SELECT payment_method, COALESCE(SUM(amount), 0)
            FROM expenses
            {where_clause}
            GROUP BY payment_method
            ORDER BY COALESCE(SUM(amount), 0) DESC
            """,
            tuple(params),
        )

        today_text = today_jalali().strftime('%Y/%m/%d')
        month_prefix = today_text[:7]
        today_rows = self.db.fetchall(
            'SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE expense_date = ?',
            (today_text,),
        )
        month_rows = self.db.fetchall(
            'SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE expense_date LIKE ?',
            (f'{month_prefix}%',),
        )

        unique_dates_rows = self.db.fetchall(
            f'SELECT COUNT(DISTINCT expense_date) FROM expenses {where_clause}',
            tuple(params),
        )
        active_days = int(unique_dates_rows[0][0] or 0)
        average_daily = int(total_amount / active_days) if active_days else 0

        return {
            'total_expense': total_amount,
            'records_count': records_count,
            'today_expense': int(today_rows[0][0] or 0),
            'month_expense': int(month_rows[0][0] or 0),
            'average_daily': average_daily,
            'top_categories': [(name, int(amount or 0)) for name, amount in top_categories],
            'methods': [
                (self.PAYMENT_METHODS.get(method, method), int(amount or 0))
                for method, amount in method_rows
            ],
        }

    def list_linkable_checks(self) -> list[dict]:
        rows = self.db.fetchall(
            """
            SELECT id, serial_7, serial_18, registrant_name, amount, status
            FROM checks
            ORDER BY id DESC
            LIMIT 300
            """
        )
        return [
            {
                'id': row[0],
                'serial_7': row[1] or '',
                'serial_18': row[2] or '',
                'registrant_name': row[3] or '',
                'amount': int(row[4] or 0),
                'status': row[5] or '',
            }
            for row in rows
        ]

    def _row_to_expense(self, row) -> Expense:
        return Expense(
            id=row[0],
            title=row[1] or '',
            amount=self._normalize_amount(row[2]),
            expense_date=self._normalize_date(row[3]),
            category_id=int(row[4] or 0),
            payment_method=self._normalize_payment_method(row[5]),
            category_name=row[6] or '',
            reference_check_id=row[7],
            vendor=row[8] or '',
            notes=row[9] or '',
        )

    def _validate_and_normalize_expense(self, expense: Expense) -> Expense:
        title = (expense.title or '').strip()
        vendor = (expense.vendor or '').strip()
        notes = (expense.notes or '').strip()
        amount = self._normalize_amount(expense.amount)
        expense_date = self._normalize_date(expense.expense_date)
        payment_method = self._normalize_payment_method(expense.payment_method)

        if not title:
            raise ValueError('عنوان هزینه نمی تواند خالی باشد.')
        if amount <= 0:
            raise ValueError('مبلغ هزینه باید بزرگ تر از صفر باشد.')
        if not expense_date:
            raise ValueError('تاریخ هزینه معتبر نیست.')

        self._ensure_category_exists(expense.category_id)

        reference_check_id = expense.reference_check_id
        if reference_check_id is not None:
            check_rows = self.db.fetchall('SELECT id FROM checks WHERE id = ?', (reference_check_id,))
            if not check_rows:
                raise ValueError('چک مرجع انتخاب شده معتبر نیست.')

        return Expense(
            id=expense.id,
            title=title,
            amount=amount,
            expense_date=expense_date,
            category_id=int(expense.category_id),
            payment_method=payment_method,
            category_name=expense.category_name,
            reference_check_id=reference_check_id,
            vendor=vendor,
            notes=notes,
        )

    def _ensure_category_exists(self, category_id: int):
        rows = self.db.fetchall(
            'SELECT id FROM expense_categories WHERE id = ?',
            (int(category_id),),
        )
        if not rows:
            raise ValueError('دسته بندی انتخاب شده معتبر نیست.')

    def _ensure_expense_exists(self, expense_id: int):
        rows = self.db.fetchall('SELECT id FROM expenses WHERE id = ?', (int(expense_id),))
        if not rows:
            raise ValueError('هزینه مورد نظر یافت نشد.')

    def _ensure_category_unique(self, name: str, excluded_id: Optional[int] = None):
        query = 'SELECT id FROM expense_categories WHERE lower(name) = lower(?)'
        params: list[object] = [name]
        if excluded_id is not None:
            query += ' AND id <> ?'
            params.append(excluded_id)

        rows = self.db.fetchall(query, tuple(params))
        if rows:
            raise ValueError('این نام دسته بندی قبلا ثبت شده است.')

    @staticmethod
    def _normalize_name(value: str) -> str:
        normalized = (value or '').strip()
        if not normalized:
            raise ValueError('نام دسته بندی نمی تواند خالی باشد.')
        return normalized

    @staticmethod
    def _normalize_date(value: str) -> str:
        return normalize_jalali_date_text(str(value or ''))

    @classmethod
    def _normalize_payment_method(cls, value: str) -> str:
        candidate = (value or '').strip().upper()
        if candidate not in cls.PAYMENT_METHODS:
            return 'OTHER'
        return candidate

    @staticmethod
    def _normalize_amount(value: int | str | None) -> int:
        if value is None or isinstance(value, bool):
            raise ValueError('مبلغ باید عددی معتبر باشد.')

        if isinstance(value, int):
            amount = value
        else:
            text = str(value).replace(',', '').strip()
            if not text or not text.isdigit():
                raise ValueError('مبلغ باید فقط شامل عدد باشد.')
            amount = int(text)

        if amount < 0:
            raise ValueError('مبلغ نمی تواند منفی باشد.')
        return amount
