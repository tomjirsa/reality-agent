from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session

from shared.db import get_db
from shared.models import (
    Listing, ListingDistance, ListingPriceHistory, ListingScore,
    ListingSearchConfig, SearchConfig,
)
from dashboard.deps import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def listings_feed(
    request: Request,
    db: Session = Depends(get_db),
    search_config_id: int | None = None,
    category_main_cb: int | None = None,
    locality_district_id: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_score: float | None = None,
    hot_only: bool = False,
    order_by: str | None = None,
    page: int = 1,
):
    PAGE_SIZE = 50
    configs = db.query(SearchConfig).order_by(SearchConfig.name).all()

    if search_config_id:
        query = (
            db.query(Listing, ListingScore, ListingDistance)
            .join(ListingScore, Listing.hash_id == ListingScore.hash_id)
            .join(
                ListingSearchConfig,
                and_(
                    ListingSearchConfig.hash_id == Listing.hash_id,
                    ListingSearchConfig.search_config_id == search_config_id,
                ),
            )
            .outerjoin(
                ListingDistance,
                and_(
                    ListingDistance.hash_id == Listing.hash_id,
                    ListingDistance.search_config_id == search_config_id,
                ),
            )
            .filter(Listing.is_active == True)
        )
    else:
        query = (
            db.query(Listing, ListingScore)
            .join(ListingScore, Listing.hash_id == ListingScore.hash_id)
            .filter(Listing.is_active == True)
        )

    if category_main_cb is not None:
        query = query.filter(Listing.category_main_cb == category_main_cb)
    if locality_district_id is not None:
        query = query.filter(Listing.locality_district_id == locality_district_id)
    if min_price is not None:
        query = query.filter(Listing.price_czk >= min_price)
    if max_price is not None:
        query = query.filter(Listing.price_czk <= max_price)
    if min_score is not None:
        query = query.filter(ListingScore.combined_score >= min_score)
    if hot_only:
        query = query.filter(ListingScore.is_hot == True)

    total = query.count()

    if order_by == "distance" and search_config_id:
        query = query.order_by(ListingDistance.distance_m.asc())
    else:
        query = query.order_by(ListingScore.combined_score.desc())

    raw = query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    if search_config_id:
        listings = raw
    else:
        listings = [(lst, score, None) for lst, score in raw]

    return templates.TemplateResponse(
        request,
        "listings.html",
        {
            "listings": listings,
            "total": total,
            "page": page,
            "page_size": PAGE_SIZE,
            "configs": configs,
            "filters": {
                "search_config_id": search_config_id,
                "category_main_cb": category_main_cb,
                "locality_district_id": locality_district_id,
                "min_price": min_price,
                "max_price": max_price,
                "min_score": min_score,
                "hot_only": hot_only,
                "order_by": order_by,
            },
        },
    )


@router.get("/listing/{hash_id}", response_class=HTMLResponse)
def listing_detail(request: Request, hash_id: int, db: Session = Depends(get_db)):
    result = (
        db.query(Listing, ListingScore)
        .outerjoin(ListingScore, Listing.hash_id == ListingScore.hash_id)
        .filter(Listing.hash_id == hash_id)
        .first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    listing, score = result
    history = (
        db.query(ListingPriceHistory)
        .filter_by(hash_id=hash_id)
        .order_by(ListingPriceHistory.recorded_at.asc())
        .all()
    )
    distances = (
        db.query(ListingDistance, SearchConfig)
        .join(SearchConfig, ListingDistance.search_config_id == SearchConfig.id)
        .filter(ListingDistance.hash_id == hash_id)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "detail.html",
        {"listing": listing, "score": score, "history": history, "distances": distances},
    )
