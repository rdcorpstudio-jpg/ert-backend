from fastapi import APIRouter, Depends, HTTPException
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

@router.delete("/freebies/{freebie_id}")
def delete_product_freebie(
    freebie_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(user, ["manager"])

    freebie = db.query(Freebie).filter(Freebie.id == freebie_id).first()

    if not freebie:
        raise HTTPException(status_code=404, detail="Freebie not found")

    db.delete(freebie)
    db.commit()

    return {"message": "Freebie deleted"}



@router.get("/freebies")
def list_freebies(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Freebie)
    if not include_inactive:
        query = query.filter(Freebie.is_active == True)
    return query.order_by(Freebie.id.asc()).all()

@router.post("/freebies")
def create_freebie(
    name: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, ["manager"])
    freebie = Freebie(name=name)
    db.add(freebie)
    db.commit()
    db.refresh(freebie)
    return freebie


@router.put("/freebies/{freebie_id}/active")
def set_freebie_active(
    freebie_id: int,
    is_active: bool,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, ["manager"])
    freebie = db.query(Freebie).filter(Freebie.id == freebie_id).first()
    if not freebie:
        raise HTTPException(status_code=404, detail="Freebie not found")
    freebie.is_active = is_active
    db.commit()
    db.refresh(freebie)
    return freebie
