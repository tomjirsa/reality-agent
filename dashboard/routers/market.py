from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.db import get_db
from shared.models import Listing
from dashboard.deps import templates

router = APIRouter()


@router.get("/market", response_class=HTMLResponse)
def market_overview(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(
            Listing.locality_district_id,
            Listing.category_main_cb,
            Listing.category_type_cb,
            func.count(Listing.hash_id).label("listing_count"),
            func.avg(Listing.price_per_m2).label("avg_price_per_m2"),
            func.min(Listing.price_per_m2).label("min_price_per_m2"),
            func.max(Listing.price_per_m2).label("max_price_per_m2"),
        )
        .filter(Listing.is_active == True, Listing.price_per_m2 != None)
        .group_by(
            Listing.locality_district_id,
            Listing.category_main_cb,
            Listing.category_type_cb,
        )
        .order_by(Listing.locality_district_id)
        .all()
    )
    summary = [
        {
            "district_id": r.locality_district_id,
            "category_main_cb": r.category_main_cb,
            "category_type_cb": r.category_type_cb,
            "listing_count": r.listing_count,
            "avg_price_per_m2": round(r.avg_price_per_m2 or 0, 0),
            "min_price_per_m2": round(r.min_price_per_m2 or 0, 0),
            "max_price_per_m2": round(r.max_price_per_m2 or 0, 0),
        }
        for r in rows
    ]
    return templates.TemplateResponse(
        request, "market.html", {"summary": summary}
    )
