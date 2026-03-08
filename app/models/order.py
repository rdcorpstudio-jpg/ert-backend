from sqlalchemy import Column, Integer, String, Date, Boolean, Text, Numeric
from app.database import Base
from sqlalchemy.orm import relationship
from sqlalchemy import DateTime
from sqlalchemy.sql import func


class Order(Base):
    __tablename__ = "orders"
    
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )


    id = Column(Integer, primary_key=True)
    order_code = Column(String(30), unique=True)

    sale_id = Column(Integer)

    customer_name = Column(String(100))
    customer_phone = Column(String(20))
    shipping_address_text = Column(String(255))

    shipping_date = Column(Date, nullable=True)

    order_status = Column(String(20), default="Pending")
    tracking_number = Column(String(255), nullable=True)
    payment_status = Column(String(20), default="Unchecked")
    # When order first becomes Checked, we store net total; product edit in Checked/Packing allowed only if current net == this.
    net_total_at_check = Column(Numeric(10, 2), nullable=True)

    invoice_required = Column(Boolean, default=False)
    invoice_name = Column(String(255), nullable=True)
    invoice_tax_id = Column(String(255), nullable=True)
    invoice_address = Column(String(255), nullable=True)
    invoice_text = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    shipping_note = Column(Text, nullable=True)
    pageName = Column(Text , nullable=True)
    installment_type = Column(String(20), nullable=True)   # full / installment
    installment_months = Column(Integer, nullable=True)    # 6 or 10

items = relationship("OrderItem", backref="order")
