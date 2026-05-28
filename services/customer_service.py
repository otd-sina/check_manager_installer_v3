from __future__ import annotations

from typing import Optional

from database.db import Database
from models.customer_model import Customer


class CustomerService:
    def __init__(self, db: Database):
        self.db = db

    def create(self, customer: Customer) -> int:
        normalized = self._normalize(customer)
        return self.db.execute(
            '''
            INSERT INTO customers(name, national_code, phone, notes)
            VALUES(?, ?, ?, ?)
            ''',
            (normalized.name, normalized.national_code, normalized.phone, normalized.notes),
        )

    def update(self, customer: Customer) -> None:
        if customer.id is None:
            raise ValueError('شناسه مشتری برای ویرایش الزامی است.')
        normalized = self._normalize(customer)

        exists = self.db.fetchone('SELECT id FROM customers WHERE id = ? LIMIT 1', (int(customer.id),))
        if exists is None:
            raise ValueError('مشتری مورد نظر یافت نشد.')

        self.db.execute(
            '''
            UPDATE customers
            SET name = ?, national_code = ?, phone = ?, notes = ?
            WHERE id = ?
            ''',
            (
                normalized.name,
                normalized.national_code,
                normalized.phone,
                normalized.notes,
                int(customer.id),
            ),
        )

    def create_or_update(
        self,
        *,
        customer_id: Optional[int],
        name: str,
        national_code: str,
        phone: str,
        notes: str = '',
    ) -> int:
        normalized = self._normalize(
            Customer(
                id=customer_id,
                name=name,
                national_code=national_code,
                phone=phone,
                notes=notes,
            )
        )

        if customer_id is not None:
            self.update(
                Customer(
                    id=int(customer_id),
                    name=normalized.name,
                    national_code=normalized.national_code,
                    phone=normalized.phone,
                    notes=normalized.notes,
                )
            )
            return int(customer_id)

        existing = self.get_by_national_code(normalized.national_code)
        if existing is not None:
            self.update(
                Customer(
                    id=existing.id,
                    name=normalized.name,
                    national_code=normalized.national_code,
                    phone=normalized.phone,
                    notes=normalized.notes,
                )
            )
            return int(existing.id or 0)

        return self.create(normalized)

    def get_by_id(self, customer_id: int) -> Optional[Customer]:
        row = self.db.fetchone('SELECT * FROM customers WHERE id = ?', (int(customer_id),))
        return self._row_to_customer(row) if row is not None else None

    def get_by_national_code(self, national_code: str) -> Optional[Customer]:
        normalized = ''.join(ch for ch in str(national_code or '') if ch.isdigit())
        if len(normalized) != 10:
            return None
        row = self.db.fetchone(
            'SELECT * FROM customers WHERE national_code = ? ORDER BY id DESC LIMIT 1',
            (normalized,),
        )
        return self._row_to_customer(row) if row is not None else None

    def list_all(self) -> list[Customer]:
        rows = self.db.fetchall(
            '''
            SELECT * FROM customers
            ORDER BY created_at DESC, id DESC
            '''
        )
        return [self._row_to_customer(row) for row in rows]

    def delete(self, customer_id: int):
        self.db.execute('DELETE FROM customers WHERE id = ?', (int(customer_id),))

    @staticmethod
    def _normalize(customer: Customer) -> Customer:
        name = (customer.name or '').strip()
        if not name:
            raise ValueError('نام و نام خانوادگی الزامی است.')

        national_code = ''.join(ch for ch in str(customer.national_code or '') if ch.isdigit())
        if len(national_code) != 10:
            raise ValueError('کد ملی باید 10 رقم باشد.')

        phone = ''.join(ch for ch in str(customer.phone or '') if ch.isdigit())
        if len(phone) < 10:
            raise ValueError('شماره تماس معتبر نیست.')

        notes = (customer.notes or '').strip()

        return Customer(
            id=customer.id,
            name=name,
            national_code=national_code,
            phone=phone,
            notes=notes,
            created_at=customer.created_at,
        )

    @staticmethod
    def _row_to_customer(row) -> Customer:
        return Customer(
            id=int(row['id']) if row['id'] is not None else None,
            name=row['name'] or '',
            national_code=row['national_code'] or '',
            phone=row['phone'] or '',
            notes=row['notes'] or '',
            created_at=row['created_at'] or '',
        )
