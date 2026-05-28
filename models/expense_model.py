from dataclasses import dataclass
from typing import Optional


@dataclass
class Expense:
    id: Optional[int]
    title: str
    amount: int
    expense_date: str
    category_id: int
    payment_method: str = 'CASH'
    category_name: str = ''
    reference_check_id: Optional[int] = None
    vendor: str = ''
    notes: str = ''
