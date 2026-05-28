from dataclasses import dataclass
from typing import Optional

@dataclass
class Check:
    id: Optional[int]
    serial_18: str
    serial_7: str
    registrant_name: str
    bank_name: str
    account_owner: str
    amount: int
    issue_date: str      # Jalali: YYYY/MM/DD
    due_date: str
    payee_name: str
    status: str         
    notes: str = ""
