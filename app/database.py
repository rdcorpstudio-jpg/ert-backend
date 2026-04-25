import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Use DATABASE_URL in production (e.g. Railway); fallback for local dev.
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:1234@localhost:3306/ert_db?charset=utf8mb4")

# Railway/MySQL can keep half-dead TCP connections around.
# These options prevent long per-request stalls (~10-15s) by validating/recycling connections.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()
