from pydantic import BaseModel
from datetime import date
from typing import Optional

class OrderCreate(BaseModel):
    customer_name: str
    customer_phone: str
    shipping_address: str
    shipping_date: Optional[date] = None
    payment_method: Optional[str] = None
    shipping_method: Optional[str] = None  # Normal (default) | Special
    invoice_text: Optional[str] = None
    note: Optional[str] = None
    shipping_note: Optional[str] = None
    pageName: Optional[str] = None
    installment_type: Optional[str] = None
    installment_months: Optional[int] = None