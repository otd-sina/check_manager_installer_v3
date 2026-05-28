from dataclasses import dataclass
from typing import Optional

@dataclass
class Customer:
    id: Optional[int]
    name: str
    national_code: str = ""
    phone: str = ""
    notes: str = ""
    created_at: str = ""
