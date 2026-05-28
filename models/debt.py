from dataclasses import dataclass
from typing import Optional


@dataclass
class Debt:
    id: Optional[int]
    debtor_name: str
    phone: str
    purchase_date: str
    due_date: str
    total_amount: int
    paid_amount: int
    remaining_balance: int
    status: str
    description: str = ''
