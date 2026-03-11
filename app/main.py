from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine

# Import all models so they register with Base.metadata before create_all.
# Otherwise tables like order_freebies are never created.
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
import app.models.line_notification_config

Base.metadata.create_all(bind=engine)

from app.routers import auth, orders, products, line_notification



app = FastAPI(title="ERT Backend")


# CORS: allow frontend origin. In production set CORS_ORIGINS (e.g. https://your-app.vercel.app).
import os
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# รวม router
app.include_router(auth.router, tags=["Auth"])
app.include_router(orders.router, tags=["Orders"])
app.include_router(products.router, tags=["Products"])
app.include_router(line_notification.router, tags=["LineNotification"])
