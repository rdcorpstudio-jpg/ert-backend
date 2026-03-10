"""
Seed products and freebies into the database (e.g. Railway production).
Uses DATABASE_URL from environment. Run from project root.

1. Create seed_data.json in this folder (or pass path) with:
   {
     "products": [
       { "category": "ตู้อบ", "name": "Product A", "price": 299 },
       { "category": "ผ้าห่ม", "name": "Product B", "price": 599 }
     ],
     "freebies": [
       { "name": "Freebie 1" },
       { "name": "Freebie 2" }
     ]
   }

2. Set DATABASE_URL to your Railway MySQL URL (from Railway -> Variables or Connect).
   If Railway gives mysql://..., change it to mysql+pymysql://... for this script.

3. Run:
   cd C:\ERT-Backend
   $env:DATABASE_URL = "your-railway-mysql-url"   # from Railway -> Variables
   python scripts/seed_products_freebies.py

   If Railway gives mysql://..., the script will use mysql+pymysql://... for Python.
"""
import json
import os
import sys

# Project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use Railway DATABASE_URL; ensure mysql+pymysql for Python
_db_url = os.getenv("DATABASE_URL", "")
if _db_url.startswith("mysql://"):
    os.environ["DATABASE_URL"] = _db_url.replace("mysql://", "mysql+pymysql://", 1)

from app.database import SessionLocal
from app.models.product import Product
from app.models.freebie import Freebie


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(script_dir, "seed_data.json")
    if len(sys.argv) > 1:
        data_path = sys.argv[1]
    if not os.path.isfile(data_path):
        print("Create seed_data.json with products and freebies, or pass path:")
        print("  python scripts/seed_products_freebies.py [path/to/seed_data.json]")
        print()
        print("Example seed_data.json:")
        print(json.dumps({
            "products": [
                {"category": "ตู้อบ", "name": "Product 1", "price": 299},
                {"category": "ผ้าห่ม", "name": "Product 2", "price": 599}
            ],
            "freebies": [
                {"name": "Freebie 1"},
                {"name": "Freebie 2"}
            ]
        }, indent=2, ensure_ascii=False))
        sys.exit(1)

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    db = SessionLocal()
    try:
        products = data.get("products", [])
        freebies = data.get("freebies", [])

        for p in products:
            existing = db.query(Product).filter(Product.name == p.get("name")).first()
            if existing:
                print("Product already exists:", p.get("name"))
                continue
            db.add(Product(
                category=p.get("category", ""),
                name=p.get("name", ""),
                price=float(p.get("price", 0)),
                is_active=True,
            ))
        for fb in freebies:
            existing = db.query(Freebie).filter(Freebie.name == fb.get("name")).first()
            if existing:
                print("Freebie already exists:", fb.get("name"))
                continue
            db.add(Freebie(name=fb.get("name", "")))

        db.commit()
        print("Done. Products added:", len(products), "Freebies added:", len(freebies))
    finally:
        db.close()


if __name__ == "__main__":
    main()
