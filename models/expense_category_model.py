from dataclasses import dataclass
from typing import Optional


@dataclass
class ExpenseCategory:
    id: Optional[int]
    name: str
    description: str = ''
