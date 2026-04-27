from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.product import Product
from app.deps import get_current_user
from app.core.permissions import require_role
from app.models.freebie import Freebie
from app.models.freebie_visibility import FreebieVisibility


def _load_freebie_visibility_map(db: Session) -> Optional[dict[int, bool]]:
    """If the visibility table is missing (first deploy / migration not run), return None = treat all as shown."""
    try:
        rows = db.query(FreebieVisibility).all()
        return {row.freebie_id: bool(row.is_active) for row in rows}
    except Exception:
        return None


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
    include_inactive: bool = False,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Product)
    if not include_inactive:
        query = query.filter(Product.is_active == True)
    products = query.order_by(Product.id.asc()).all()
    return products


@router.put("/{product_id}/active")
def set_product_active(
    product_id: int,
    is_active: bool,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, ["manager"])
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.is_active = is_active
    db.commit()
    db.refresh(product)
    return {"id": product.id, "name": product.name, "is_active": bool(product.is_active)}

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
    is_active_by_id = _load_freebie_visibility_map(db)

    result = []
    for freebie in freebies:
        # Default visibility is shown when not explicitly configured.
        if is_active_by_id is None:
            is_active = True
        else:
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

    try:
        row = db.query(FreebieVisibility).filter(FreebieVisibility.freebie_id == freebie_id).first()
        if row:
            row.is_active = is_active
        else:
            row = FreebieVisibility(freebie_id=freebie_id, is_active=is_active)
            db.add(row)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Cannot update freebie visibility (database table not ready). Redeploy the backend or run migrations.",
        ) from e
    return {"id": freebie.id, "name": freebie.name, "is_active": bool(is_active)}
