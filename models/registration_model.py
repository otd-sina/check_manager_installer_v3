from dataclasses import dataclass
from typing import Optional


@dataclass
class Registration:
    id: Optional[int] = None
    customer_id: int = 0
    customer_name: str = ""
    national_code: str = ""
    phone: str = ""
    course_name: str = ""
    registration_date: str = ""
    total_fee: int = 0
    initial_payment: int = 0
    payment_method: str = "CASH"
    description: str = ""
    income_total: int = 0
    check_income_total: int = 0
    non_check_income_total: int = 0
    check_count: int = 0
    payment_count: int = 0
    created_at: str = ""
    updated_at: str = ""
