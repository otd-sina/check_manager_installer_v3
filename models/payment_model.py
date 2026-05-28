from dataclasses import dataclass
from typing import Optional


@dataclass
class Payment:
    id: Optional[int] = None
    registration_id: int = 0
    amount: int = 0
    payment_method: str = "CASH_INCOME"
    payment_date: str = ""
    notes: str = ""
    check_id: Optional[int] = None
    created_at: str = ""
