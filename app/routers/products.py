from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.product import Product
from app.deps import get_current_user
from app.core.permissions import require_role
from app.models.freebie import Freebie



router = APIRouter(prefix="/products")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("")
def create_product(
    category: str,
    name: str,
    price: float,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(user, ["manager"])

    product = Product(
        category=category,
        name=name,
        price=price
    )

    db.add(product)
    db.commit()

    return {"message": "Product created"}


@router.get("")
def list_products(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    products = db.query(Product).filter(Product.is_active == True).all()
    return products

from app.deps import get_current_user
from app.core.permissions import require_role
from fastapi import HTTPException


@router.delete("/freebies/{freebie_id}")
def delete_product_freebie(
    freebie_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(user, ["manager"])

    freebie = db.query(ProductFreebie).filter(
        ProductFreebie.id == freebie_id
    ).first()

    if not freebie:
        raise HTTPException(status_code=404, detail="Freebie not found")

    db.delete(freebie)
    db.commit()

    return {"message": "Freebie deleted"}



@router.get("/freebies")
def list_freebies(db: Session = Depends(get_db)):
    return db.query(Freebie).order_by(Freebie.id.asc()).all()

@router.post("/freebies")
def create_freebie(name: str, db: Session = Depends(get_db)):
    freebie = Freebie(name=name)
    db.add(freebie)
    db.commit()
    return freebie
