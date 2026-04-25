from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.product import Product
from app.deps import get_current_user
from app.core.permissions import require_role
from app.models.freebie import Freebie
from app.models.freebie_visibility import FreebieVisibility



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
    freebies = db.query(Freebie).order_by(Freebie.id.asc()).all()
    visibility_rows = db.query(FreebieVisibility).all()
    is_active_by_id = {row.freebie_id: bool(row.is_active) for row in visibility_rows}

    result = []
    for freebie in freebies:
        # Default visibility is shown when not explicitly configured.
        is_active = is_active_by_id.get(freebie.id, True)
        if not include_inactive and not is_active:
            continue
        result.append(
            {
                "id": freebie.id,
                "name": freebie.name,
                "is_active": is_active,
            }
        )

    return result

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

    row = db.query(FreebieVisibility).filter(FreebieVisibility.freebie_id == freebie_id).first()
    if row:
        row.is_active = is_active
    else:
        row = FreebieVisibility(freebie_id=freebie_id, is_active=is_active)
        db.add(row)

    db.commit()
    return {"id": freebie.id, "name": freebie.name, "is_active": bool(is_active)}
