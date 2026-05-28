from __future__ import annotations

import logging
from typing import Iterator, Optional

from database.db import CHECK_STATUSES, Database
from models.check_model import Check
from utils.date_utils import jalali_to_gregorian, normalize_jalali_date_text


logger = logging.getLogger(__name__)


class CheckService:
    def __init__(self, db: Database):
        self.db = db

    def add_check(self, check: Check) -> int:
        normalized = self._validate_and_normalize(check)
        self._ensure_serial_unique(normalized.serial_18, normalized.serial_7)

        check_id = self.db.create_check(self._check_to_payload(normalized))
        logger.info(
            'Check created: id=%s serial_7=%s due_date=%s status=%s',
            check_id,
            normalized.serial_7,
            normalized.due_date,
            normalized.status,
        )
        return check_id

    def update_check(self, check: Check):
        if check.id is None:
            raise ValueError('Check id is required for update.')

        self._ensure_check_exists(check.id)
        normalized = self._validate_and_normalize(check)
        self._ensure_serial_unique(
            normalized.serial_18,
            normalized.serial_7,
            exclude_id=check.id,
        )

        self.db.update_check(check.id, self._check_to_payload(normalized))
        logger.info('Check updated: id=%s status=%s', check.id, normalized.status)

    def delete_check(self, check_id: int):
        self._ensure_check_exists(check_id)
        self.db.delete_check(check_id)
        logger.info('Check deleted: id=%s', check_id)

    def get_check(self, check_id: int) -> Optional[Check]:
        row = self.db.get_check(check_id)
        if row is None:
            return None
        return self._row_to_check(row)

    def list_checks(
        self,
        status: Optional[str] = None,
        from_due_date: Optional[str] = None,
        to_due_date: Optional[str] = None,
    ) -> list[Check]:
        return list(self.iter_checks(status=status, from_due_date=from_due_date, to_due_date=to_due_date))

    def iter_checks(
        self,
        status: Optional[str] = None,
        from_due_date: Optional[str] = None,
        to_due_date: Optional[str] = None,
        batch_size: int = 500,
    ) -> Iterator[Check]:
        normalized_status = self._normalize_status(status) if status else None
        normalized_from = self._normalize_db_date(from_due_date) if from_due_date else None
        normalized_to = self._normalize_db_date(to_due_date) if to_due_date else None

        for row in self.db.iter_checks(
            status=normalized_status,
            from_due_date=normalized_from,
            to_due_date=normalized_to,
            batch_size=batch_size,
        ):
            yield self._row_to_check(row)

    def _row_to_check(self, row) -> Check:
        return Check(
            id=int(row['id']) if row['id'] is not None else None,
            serial_18=row['serial_18'] or '',
            serial_7=row['serial_7'] or '',
            registrant_name=row['registrant_name'] or '',
            bank_name=row['bank_name'] or '',
            account_owner=row['account_owner'] or '',
            amount=self._normalize_amount(row['amount']),
            issue_date=self._safe_normalize_date(row['issue_date']),
            due_date=self._safe_normalize_date(row['due_date']),
            payee_name=row['payee_name'] or '',
            status=row['status'] or 'PENDING',
            notes=row['notes'] or '',
        )

    def _validate_and_normalize(self, check: Check) -> Check:
        serial_18 = (check.serial_18 or '').strip()
        serial_7 = str(check.serial_7 or '')
        registrant_name = (check.registrant_name or '').strip()
        bank_name = (check.bank_name or '').strip()
        account_owner = (check.account_owner or '').strip()
        payee_name = (check.payee_name or '').strip()
        notes = (check.notes or '').strip()

        if not (serial_18.isdigit() and len(serial_18) == 16):
            raise ValueError('serial_18 must contain exactly 16 digits.')

        if not serial_7.strip():
            raise ValueError('serial_7 is required.')

        if not self._is_alpha_name(registrant_name):
            raise ValueError('registrant_name must contain Persian or English letters only.')

        if not self._is_alpha_name(bank_name):
            raise ValueError('bank_name must contain Persian or English letters only.')

        if not self._is_alpha_name(account_owner):
            raise ValueError('account_owner must contain Persian or English letters only.')

        if payee_name and not self._is_alpha_name(payee_name):
            raise ValueError('payee_name must contain Persian or English letters only.')

        amount = self._normalize_amount(check.amount)
        if amount <= 0:
            raise ValueError('amount must be a positive number.')

        issue_date = self._normalize_db_date(check.issue_date)
        due_date = self._normalize_db_date(check.due_date)
        if issue_date and due_date:
            if jalali_to_gregorian(due_date) < jalali_to_gregorian(issue_date):
                raise ValueError('due_date cannot be before issue_date.')

        status = self._normalize_status(check.status)

        return Check(
            id=check.id,
            serial_18=serial_18,
            serial_7=serial_7,
            registrant_name=registrant_name,
            bank_name=bank_name,
            account_owner=account_owner,
            amount=amount,
            issue_date=issue_date,
            due_date=due_date,
            payee_name=payee_name,
            status=status,
            notes=notes,
        )

    def _check_to_payload(self, check: Check) -> dict[str, object]:
        return {
            'serial_18': check.serial_18,
            'serial_7': check.serial_7,
            'registrant_name': check.registrant_name,
            'bank_name': check.bank_name,
            'account_owner': check.account_owner,
            'amount': check.amount,
            'issue_date': check.issue_date,
            'due_date': check.due_date,
            'payee_name': check.payee_name,
            'status': check.status,
            'notes': check.notes,
        }

    def _ensure_serial_unique(
        self,
        serial_18: str,
        serial_7: str,
        exclude_id: int | None = None,
    ):
        if self.db.serial_exists(
            serial_18=serial_18,
            serial_7=serial_7,
            exclude_id=exclude_id,
        ):
            raise ValueError('A check with the same serial already exists.')

    def _ensure_check_exists(self, check_id: int):
        if not self.db.check_exists(check_id):
            raise ValueError('Check not found.')

    @staticmethod
    def _is_alpha_name(value: str) -> bool:
        cleaned = value.strip()
        if not cleaned:
            return False
        return all(char.isalpha() or char.isspace() for char in cleaned)

    @staticmethod
    def _normalize_amount(value: int | str | None) -> int:
        if value is None or isinstance(value, bool):
            raise ValueError('amount must be a valid number.')

        if isinstance(value, int):
            amount = value
        else:
            text = str(value).replace(',', '').strip()
            if not text or not text.isdigit():
                raise ValueError('amount must contain digits only.')
            amount = int(text)

        if amount < 0:
            raise ValueError('amount must be non-negative.')
        return amount

    @staticmethod
    def _normalize_db_date(value: str | None) -> str:
        if value is None:
            return ''
        return normalize_jalali_date_text(str(value))

    @staticmethod
    def _safe_normalize_date(value: str | None) -> str:
        if not value:
            return ''
        try:
            return normalize_jalali_date_text(str(value))
        except ValueError:
            return ''

    @staticmethod
    def _normalize_status(value: str | None) -> str:
        status = (value or '').strip().upper()
        if not status:
            return 'PENDING'
        if status not in CHECK_STATUSES:
            raise ValueError(f'Invalid check status: {value}')
        return status
