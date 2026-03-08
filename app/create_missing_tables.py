"""
Run once to create any missing DB tables (e.g. order_freebies).
Usage (from project root): python -m app.create_missing_tables
"""
from app.database import Base, engine

# Register all models with Base.metadata before create_all
import app.models.user
import app.models.product
import app.models.freebie
import app.models.order
import app.models.order_payment
import app.models.order_item
import app.models.order_item_freebie
import app.models.order_freebie
import app.models.order_alert
import app.models.order_log
import app.models.order_file

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("create_all done. Missing tables (e.g. order_freebies) should now exist.")
