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
from dashboard.scoring import compute_live_score, DEFAULT_WEIGHTS

router = APIRouter()


_SORT_COLS = {
    "price":      lambda: Listing.price_czk,
    "price_m2":   lambda: Listing.price_per_m2,
    "score":      lambda: ListingScore.combined_score,
    "days":       lambda: ListingScore.days_on_market,
    "price_pct":  lambda: ListingScore.price_percentile,
    "ppm2_pct":   lambda: ListingScore.price_per_m2_percentile,
    "distance":   lambda: ListingDistance.distance_m,
}


@router.get("/", response_class=HTMLResponse)
def listings_feed(
    request: Request,
    db: Session = Depends(get_db),
    search_config_id: str | None = None,
    category_main_cb: str | None = None,
    locality_district_id: str | None = None,
    min_price: str | None = None,
    max_price: str | None = None,
    min_score: str | None = None,
    hot_only: bool = False,
    status: str = "active",
    order_by: str = "score",
    order_dir: str = "desc",
    page: int = 1,
    condition: str | None = None,
    energy_class: str | None = None,
    building_type: str | None = None,
    has_parking: str | None = None,
    has_outdoor_space: str | None = None,
):
    PAGE_SIZE = 50
    sc_id = int(search_config_id) if search_config_id else None
    cat_cb = int(category_main_cb) if category_main_cb else None
    dist_id = int(locality_district_id) if locality_district_id else None
    min_p = int(min_price) if min_price else None
    max_p = int(max_price) if max_price else None
    min_s = float(min_score) if min_score else None
    configs = db.query(SearchConfig).order_by(SearchConfig.name).all()

    if sc_id:
        query = (
            db.query(Listing, ListingScore, ListingDistance)
            .outerjoin(ListingScore, Listing.hash_id == ListingScore.hash_id)
            .join(
                ListingSearchConfig,
                and_(
                    ListingSearchConfig.hash_id == Listing.hash_id,
                    ListingSearchConfig.search_config_id == sc_id,
                ),
            )
            .outerjoin(
                ListingDistance,
                and_(
                    ListingDistance.hash_id == Listing.hash_id,
                    ListingDistance.search_config_id == sc_id,
                ),
            )
        )
    else:
        query = (
            db.query(Listing, ListingScore)
            .outerjoin(ListingScore, Listing.hash_id == ListingScore.hash_id)
        )

    if status == "active":
        query = query.filter(Listing.is_active == True)
    elif status == "inactive":
        query = query.filter(Listing.is_active == False)

    if cat_cb is not None:
        query = query.filter(Listing.category_main_cb == cat_cb)
    if dist_id is not None:
        query = query.filter(Listing.locality_district_id == dist_id)
    if min_p is not None:
        query = query.filter(Listing.price_czk >= min_p)
    if max_p is not None:
        query = query.filter(Listing.price_czk <= max_p)
    if min_s is not None:
        query = query.filter(ListingScore.combined_score >= min_s)
    if hot_only:
        query = query.filter(ListingScore.is_hot == True)
    if condition:
        query = query.filter(Listing.condition == condition)
    if energy_class:
        query = query.filter(Listing.energy_class == energy_class)
    if building_type:
        query = query.filter(Listing.building_type == building_type)
    if has_parking == "true":
        query = query.filter(Listing.has_parking == True)
    elif has_parking == "false":
        query = query.filter(Listing.has_parking == False)
    if has_outdoor_space == "true":
        query = query.filter(Listing.has_outdoor_space == True)
    elif has_outdoor_space == "false":
        query = query.filter(Listing.has_outdoor_space == False)

    total = query.count()

    col_key = order_by if (order_by in _SORT_COLS and (order_by != "distance" or sc_id)) else "score"
    col_expr = _SORT_COLS[col_key]()
    sort_expr = col_expr.asc().nulls_last() if order_dir == "asc" else col_expr.desc().nulls_last()
    query = query.order_by(sort_expr)

    raw = query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()
    listings = raw if sc_id else [(lst, score, None) for lst, score in raw]

    weights = {}
    if sc_id:
        config_obj = db.query(SearchConfig).filter_by(id=sc_id).first()
        if config_obj and config_obj.scoring_weights:
            weights = config_obj.scoring_weights
    if not weights:
        weights = DEFAULT_WEIGHTS

    # Compute live scores for each listing
    live_scores = {}
    for item in listings:
        lst, score, distance = item
        live_score = compute_live_score(score, weights)
        live_scores[lst.hash_id] = live_score

    # Query string for sort links (all filters except order params)
    qs_parts = []
    if sc_id:         qs_parts.append(f"search_config_id={sc_id}")
    if cat_cb:        qs_parts.append(f"category_main_cb={cat_cb}")
    if dist_id:       qs_parts.append(f"locality_district_id={dist_id}")
    if min_p:         qs_parts.append(f"min_price={min_p}")
    if max_p:         qs_parts.append(f"max_price={max_p}")
    if min_s:         qs_parts.append(f"min_score={min_s}")
    if hot_only:            qs_parts.append("hot_only=1")
    if condition:           qs_parts.append(f"condition={condition}")
    if energy_class:        qs_parts.append(f"energy_class={energy_class}")
    if building_type:       qs_parts.append(f"building_type={building_type}")
    if has_parking:         qs_parts.append(f"has_parking={has_parking}")
    if has_outdoor_space:   qs_parts.append(f"has_outdoor_space={has_outdoor_space}")
    qs_parts.append(f"status={status}")
    filter_qs = "&".join(qs_parts)

    return templates.TemplateResponse(
        request,
        "listings.html",
        {
            "listings": listings,
            "live_scores": live_scores,
            "total": total,
            "page": page,
            "page_size": PAGE_SIZE,
            "configs": configs,
            "filter_qs": filter_qs,
            "has_distance_col": bool(sc_id),
            "weights": weights,
            "default_weights": DEFAULT_WEIGHTS,
            "filters": {
                "search_config_id": sc_id,
                "category_main_cb": cat_cb,
                "locality_district_id": dist_id,
                "min_price": min_p,
                "max_price": max_p,
                "min_score": min_s,
                "hot_only": hot_only,
                "status": status,
                "order_by": col_key,
                "order_dir": order_dir,
                "condition": condition,
                "energy_class": energy_class,
                "building_type": building_type,
                "has_parking": has_parking,
                "has_outdoor_space": has_outdoor_space,
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
