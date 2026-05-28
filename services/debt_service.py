from __future__ import annotations

import logging
from typing import Optional

from database.db import DEBT_STATUSES, Database
from models.debt import Debt
from utils.date_utils import normalize_jalali_date_text, today_jalali


logger = logging.getLogger(__name__)


class DebtService:
    STATUS_LABELS = {
        'PAID': 'تسویه شده',
        'UNPAID': 'پرداخت نشده',
        'PARTIAL': 'پرداخت ناقص',
    }

    def __init__(self, db: Database):
        self.db = db

    def add_debt(self, debt: Debt) -> int:
        normalized = self._validate_and_normalize(debt)
        debt_id = self.db.create_debt(self._to_payload(normalized))
        logger.info('Debt created: id=%s debtor=%s remaining=%s', debt_id, normalized.debtor_name, normalized.remaining_balance)
        return debt_id

    def update_debt(self, debt: Debt):
        if debt.id is None:
            raise ValueError('شناسه بدهی برای ویرایش الزامی است.')
        self._ensure_debt_exists(debt.id)

        normalized = self._validate_and_normalize(debt)
        self.db.update_debt(int(debt.id), self._to_payload(normalized))
        logger.info('Debt updated: id=%s status=%s remaining=%s', debt.id, normalized.status, normalized.remaining_balance)

    def delete_debt(self, debt_id: int):
        self._ensure_debt_exists(debt_id)
        self.db.delete_debt(int(debt_id))
        logger.info('Debt deleted: id=%s', debt_id)

    def get_debt(self, debt_id: int) -> Optional[Debt]:
        row = self.db.get_debt(int(debt_id))
        if row is None:
            return None
        return self._row_to_model(row)

    def list_debts(
        self,
        status: str = '',
        from_due_date: str = '',
        to_due_date: str = '',
    ) -> list[Debt]:
        normalized_status = self._normalize_status(status) if status else None
        normalized_from = self._normalize_date(from_due_date) if from_due_date else None
        normalized_to = self._normalize_date(to_due_date) if to_due_date else None

        rows = self.db.list_debts(
            status=normalized_status,
            from_due_date=normalized_from,
            to_due_date=normalized_to,
        )
        return [self._row_to_model(row) for row in rows]

    def get_total_outstanding_receivables(self) -> int:
        return int(self.db.get_total_outstanding_receivables())

    def get_unpaid_debts_count(self) -> int:
        return int(self.db.get_unpaid_debts_count())

    def _row_to_model(self, row) -> Debt:
        total_amount = self._normalize_amount(row['total_amount'])
        paid_amount = self._normalize_amount(row['paid_amount'])
        if paid_amount > total_amount:
            paid_amount = total_amount
        remaining_balance = total_amount - paid_amount

        purchase_date = self._safe_normalize_date(row['purchase_date'])
        if not purchase_date:
            purchase_date = today_jalali().strftime('%Y/%m/%d')

        return Debt(
            id=int(row['id']) if row['id'] is not None else None,
            debtor_name=(row['debtor_name'] or '').strip(),
            phone=self._normalize_phone(row['phone']),
            purchase_date=purchase_date,
            due_date=self._safe_normalize_date(row['due_date']),
            total_amount=total_amount,
            paid_amount=paid_amount,
            remaining_balance=remaining_balance,
            status=self._derive_status(remaining_balance, total_amount),
            description=(row['description'] or '').strip(),
        )

    def _validate_and_normalize(self, debt: Debt) -> Debt:
        debtor_name = (debt.debtor_name or '').strip()
        if not debtor_name:
            raise ValueError('نام بدهکار الزامی است.')

        phone = self._normalize_phone(debt.phone)
        if len(phone) != 11:
            raise ValueError('تلفن همراه باید دقیقا 11 رقم باشد.')

        total_amount = self._normalize_amount(debt.total_amount)
        paid_amount = self._normalize_amount(debt.paid_amount)

        if total_amount <= 0:
            raise ValueError('مبلغ بدهی باید بزرگ تر از صفر باشد.')

        if paid_amount > total_amount:
            raise ValueError('مبلغ پرداخت شده نمی تواند بیشتر از مبلغ بدهی باشد.')

        purchase_date = self._normalize_date(debt.purchase_date) if debt.purchase_date else today_jalali().strftime('%Y/%m/%d')
        due_date = self._normalize_date(debt.due_date) if debt.due_date else ''
        description = (debt.description or '').strip()

        remaining_balance = total_amount - paid_amount
        status = self._derive_status(remaining_balance, total_amount)

        return Debt(
            id=debt.id,
            debtor_name=debtor_name,
            phone=phone,
            purchase_date=purchase_date,
            due_date=due_date,
            total_amount=total_amount,
            paid_amount=paid_amount,
            remaining_balance=remaining_balance,
            status=status,
            description=description,
        )

    def _ensure_debt_exists(self, debt_id: int):
        if not self.db.debt_exists(int(debt_id)):
            raise ValueError('رکورد بدهی مورد نظر یافت نشد.')

    @staticmethod
    def _to_payload(debt: Debt) -> dict[str, object]:
        return {
            'debtor_name': debt.debtor_name,
            'phone': debt.phone,
            'purchase_date': debt.purchase_date,
            'due_date': debt.due_date,
            'total_amount': debt.total_amount,
            'paid_amount': debt.paid_amount,
            'remaining_balance': debt.remaining_balance,
            'status': debt.status,
            'description': debt.description,
        }

    @staticmethod
    def _normalize_amount(value: int | str | None) -> int:
        if value is None or isinstance(value, bool):
            raise ValueError('مبلغ باید عدد معتبر باشد.')

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

    @staticmethod
    def _normalize_phone(value: object) -> str:
        return ''.join(ch for ch in str(value or '') if ch.isdigit())

    @staticmethod
    def _normalize_date(value: str) -> str:
        return normalize_jalali_date_text(str(value or ''))

    @staticmethod
    def _safe_normalize_date(value: str | None) -> str:
        if not value:
            return ''
        try:
            return normalize_jalali_date_text(str(value))
        except ValueError:
            return ''

    @staticmethod
    def _derive_status(remaining_balance: int, total_amount: int) -> str:
        if total_amount <= 0:
            return 'UNPAID'
        if remaining_balance <= 0:
            return 'PAID'
        if remaining_balance == total_amount:
            return 'UNPAID'
        return 'PARTIAL'

    @staticmethod
    def _normalize_status(value: str | None) -> str:
        status = (value or '').strip().upper()
        if status not in DEBT_STATUSES:
            raise ValueError('وضعیت بدهی نامعتبر است.')
        return status
