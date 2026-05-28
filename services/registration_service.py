from __future__ import annotations

import logging
from typing import Optional

from database.db import Database
from models.check_model import Check
from models.registration_model import Registration
from services.customer_service import CustomerService
from utils.date_utils import normalize_jalali_date_text


ALLOWED_PAYMENT_METHODS = {
    'CHECK',
    'CASH',
    'CARD',
    'TRANSFER',
}

logger = logging.getLogger(__name__)


class RegistrationService:
    PAYMENT_METHOD_LABELS = {
        'CHECK': 'چک',
        'CASH': 'نقدی',
        'CARD': 'کارت',
        'TRANSFER': 'انتقال',
    }

    def __init__(self, db: Database):
        self.db = db
        self.customer_service = CustomerService(db)

    def create(self, registration: Registration, selected_check_ids: list[int] | None = None) -> int:
        payload, check_ids = self._validate_payload(registration, selected_check_ids)
        registration_id = self.db.create_registration_with_income(payload, check_ids)
        logger.info(
            'Registration created: id=%s customer_id=%s total_fee=%s checks=%s',
            registration_id,
            payload['customer_id'],
            payload['total_fee'],
            len(check_ids),
        )
        return registration_id

    def update(self, registration: Registration, selected_check_ids: list[int] | None = None):
        if registration.id is None:
            raise ValueError('شناسه ثبت نام برای ویرایش الزامی است.')
        payload, check_ids = self._validate_payload(
            registration,
            selected_check_ids,
        )
        self.db.update_registration_with_income(int(registration.id), payload, check_ids)
        logger.info(
            'Registration updated: id=%s customer_id=%s total_fee=%s checks=%s',
            int(registration.id),
            payload['customer_id'],
            payload['total_fee'],
            len(check_ids),
        )

    def get(self, registration_id: int) -> Optional[Registration]:
        row = self.db.get_registration(int(registration_id))
        if row is None:
            return None
        return self._row_to_model(row)

    def list_all(self, search_text: str = '') -> list[Registration]:
        rows = self.db.list_registrations(search_text=search_text)
        return [self._row_to_model(row) for row in rows]

    def list_by_customer(self, customer_id: int) -> list[Registration]:
        rows = self.db.list_registrations_by_customer(int(customer_id))
        return [self._row_to_model(row) for row in rows]

    def list_payments(self, registration_id: int):
        return self.db.list_payments_by_registration(int(registration_id))

    def list_selected_check_ids(self, registration_id: int) -> list[int]:
        return self.db.list_check_ids_by_registration(int(registration_id))

    def list_available_checks(self, registration_id: int | None = None) -> list[Check]:
        rows = self.db.list_available_checks_for_registration(registration_id)
        return [
            Check(
                id=int(row['id']) if row['id'] is not None else None,
                serial_18=row['serial_18'] or '',
                serial_7=row['serial_7'] or '',
                registrant_name=row['registrant_name'] or '',
                bank_name=row['bank_name'] or '',
                account_owner=row['account_owner'] or '',
                amount=int(row['amount'] or 0),
                issue_date=row['issue_date'] or '',
                due_date=row['due_date'] or '',
                payee_name=row['payee_name'] or '',
                status=row['status'] or 'PENDING',
                notes=row['notes'] or '',
            )
            for row in rows
        ]

    def build_financial_report(self) -> dict[str, int]:
        return self.db.get_financial_snapshot()

    def delete(self, registration_id: int):
        self.db.delete_registration(int(registration_id))
        logger.info('Registration deleted: id=%s', int(registration_id))

    @staticmethod
    def _normalize_amount(value) -> int:
        text = str(value if value is not None else '').replace(',', '').strip()
        if not text or not text.isdigit():
            raise ValueError('مبلغ کل باید عدد صحیح باشد.')
        amount = int(text)
        if amount < 0:
            raise ValueError('مبلغ کل نمی تواند منفی باشد.')
        return amount

    @staticmethod
    def _normalize_payment_method(value: str) -> str:
        method = (value or '').strip().upper()
        if method == 'POS':
            return 'CARD'
        if method == 'CARD_TO_CARD':
            return 'TRANSFER'
        if method == 'CASH_INCOME':
            return 'CASH'
        if method == 'CHECK':
            return 'CHECK'
        if method not in ALLOWED_PAYMENT_METHODS:
            raise ValueError('روش پرداخت نامعتبر است.')
        return method

    def _validate_payload(
        self,
        registration: Registration,
        selected_check_ids: list[int] | None,
    ) -> tuple[dict[str, object], list[int]]:
        customer_id = self._resolve_customer_id(registration)

        course_name = (registration.course_name or '').strip()
        if not course_name:
            raise ValueError('نام دوره الزامی است.')

        registration_date = normalize_jalali_date_text(registration.registration_date or '')
        if not registration_date:
            raise ValueError('تاریخ ثبت نام الزامی است.')

        total_fee = self._normalize_amount(registration.total_fee)
        if total_fee <= 0:
            raise ValueError('مبلغ کل باید بزرگ تر از صفر باشد.')
        initial_payment = self._normalize_amount(registration.initial_payment)
        if initial_payment > total_fee:
            raise ValueError('پرداخت اولیه نمی تواند بیشتر از شهریه کل باشد.')

        payment_method = self._normalize_payment_method(registration.payment_method)
        description = (registration.description or '').strip()

        check_ids = [int(cid) for cid in (selected_check_ids or []) if int(cid) > 0]
        if len(set(check_ids)) != len(check_ids):
            raise ValueError('چک تکراری انتخاب شده است.')

        check_amounts = self.db.get_check_amounts_by_ids(check_ids)
        if len(check_amounts) != len(set(check_ids)):
            raise ValueError('یک یا چند چک انتخاب شده معتبر نیست.')

        checks_total = sum(check_amounts[int(cid)] for cid in check_ids)
        if checks_total > total_fee:
            raise ValueError('جمع مبالغ چک ها نمی تواند بیشتر از مبلغ کل ثبت نام باشد.')

        covered_amount = checks_total + initial_payment
        if covered_amount > total_fee:
            raise ValueError('جمع پرداخت اولیه و چک ها نمی تواند بیشتر از شهریه کل ثبت نام باشد.')
        if initial_payment > 0 and payment_method == 'CHECK':
            raise ValueError('برای پرداخت اولیه باید روش پرداخت غیرچک انتخاب شود.')
        if covered_amount == 0 and payment_method == 'CHECK' and not check_ids:
            raise ValueError('برای روش پرداخت چک، حداقل یک چک باید انتخاب شود.')

        effective_payment_method = 'CHECK' if check_ids and covered_amount == total_fee and initial_payment == 0 else payment_method

        payload = {
            'customer_id': customer_id,
            'course_name': course_name,
            'registration_date': registration_date,
            'total_fee': total_fee,
            'initial_payment': initial_payment,
            'payment_method': effective_payment_method,
            'description': description,
        }
        return payload, check_ids

    def _resolve_customer_id(self, registration: Registration) -> int:
        customer_name = (registration.customer_name or '').strip()
        if not customer_name:
            raise ValueError('نام و نام خانوادگی الزامی است.')

        national_code = ''.join(ch for ch in str(registration.national_code or '') if ch.isdigit())
        if len(national_code) != 10:
            raise ValueError('کد ملی باید 10 رقم باشد.')

        phone = ''.join(ch for ch in str(registration.phone or '') if ch.isdigit())
        if len(phone) < 10:
            raise ValueError('شماره تماس معتبر نیست.')

        return int(
            self.customer_service.create_or_update(
                customer_id=None,
                name=customer_name,
                national_code=national_code,
                phone=phone,
            )
        )

    @staticmethod
    def _row_to_model(row) -> Registration:
        return Registration(
            id=int(row['id']) if row['id'] is not None else None,
            customer_id=int(row['customer_id']) if row['customer_id'] is not None else 0,
            customer_name=row['customer_name'] or '',
            national_code=row['national_code'] or '',
            phone=row['phone'] or '',
            course_name=row['course_name'] or '',
            registration_date=row['registration_date'] or '',
            total_fee=int(row['total_fee'] or 0),
            initial_payment=int(row['initial_payment'] or 0),
            payment_method=(row['payment_method'] or 'CASH').upper(),
            description=row['description'] or '',
            income_total=int(row['income_total'] or 0),
            check_income_total=int(row['check_income_total'] or 0),
            non_check_income_total=int(row['non_check_income_total'] or 0),
            check_count=int(row['check_count'] or 0),
            payment_count=int(row['payment_count'] or 0),
            created_at=row['created_at'] or '',
            updated_at=row['updated_at'] or '',
        )
