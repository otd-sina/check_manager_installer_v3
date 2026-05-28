from __future__ import annotations

from database.db import Database
from models.payment_model import Payment


class PaymentService:
    def __init__(self, db: Database):
        self.db = db

    def list_by_registration(self, registration_id: int) -> list[Payment]:
        rows = self.db.list_payments_by_registration(int(registration_id))
        result: list[Payment] = []
        for row in rows:
            result.append(
                Payment(
                    id=int(row['id']) if row['id'] is not None else None,
                    registration_id=int(row['registration_id']) if row['registration_id'] is not None else 0,
                    amount=int(row['amount'] or 0),
                    payment_method=row['payment_method'] or 'CASH_INCOME',
                    payment_date=row['payment_date'] or '',
                    notes=row['notes'] or '',
                    check_id=int(row['check_id']) if row['check_id'] is not None else None,
                    created_at=row['created_at'] or '',
                )
            )
        return result
