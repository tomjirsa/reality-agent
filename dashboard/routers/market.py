from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.db import get_db
from shared.models import Listing, MarketSnapshot
from dashboard.deps import templates

router = APIRouter()

UTC = timezone.utc


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


@router.get("/market/snapshots")
def market_snapshots(db: Session = Depends(get_db)):
    cutoff = datetime.now(UTC) - timedelta(days=365)
    rows = (
        db.query(MarketSnapshot)
        .filter(MarketSnapshot.snapshot_at >= cutoff)
        .order_by(MarketSnapshot.snapshot_at.asc())
        .all()
    )
    result: dict[str, list] = {}
    for r in rows:
        key = f"{r.category_main_cb}_{r.category_type_cb}_{r.locality_district_id}"
        if key not in result:
            result[key] = []
        result[key].append({
            "t": r.snapshot_at.isoformat(),
            "median": r.median_price_m2,
            "p25": r.p25_price_m2,
            "p75": r.p75_price_m2,
        })
    return JSONResponse(result)
