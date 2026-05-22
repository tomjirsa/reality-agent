import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from shared.config import settings
from shared.db import get_db
from shared.models import SearchConfig
from dashboard.deps import templates
from enricher.client import geocode

router = APIRouter()
logger = logging.getLogger(__name__)
UTC = timezone.utc


@router.get("/configs", response_class=HTMLResponse)
def list_configs(request: Request, db: Session = Depends(get_db)):
    configs = db.query(SearchConfig).order_by(SearchConfig.id).all()
    return templates.TemplateResponse(request, "configs.html", {"configs": configs})


def _to_int(v: str | None) -> int | None:
    return int(v) if v else None


@router.post("/configs")
def create_config(
    db: Session = Depends(get_db),
    name: str = Form(...),
    category_main_cb: int = Form(...),
    category_type_cb: int = Form(...),
    category_sub_cb: str = Form(None),
    locality_region_id: str = Form(None),
    locality_district_id: list[str] = Form(None),
    czk_price_min: str = Form(None),
    czk_price_max: str = Form(None),
    usable_area_min: str = Form(None),
    usable_area_max: str = Form(None),
    ownership: str = Form(None),
    no_auction: bool = Form(True),
    destination_address: str = Form(None),
    travel_mode: str = Form(None),
):
    destination_label = None
    destination_lat = None
    destination_lon = None

    if destination_address:
        if not settings.mapy_api_key:
            return HTMLResponse(
                content=(
                    "<p>Geocoding unavailable: <code>MAPY_API_KEY</code> is not configured.</p>"
                    "<p><a href='/configs'>← Go back</a></p>"
                ),
                status_code=503,
            )
        coords = geocode(destination_address, settings.mapy_api_key)
        if coords is None:
            return HTMLResponse(
                content=(
                    f"<p>Could not geocode destination: <em>{destination_address}</em>. "
                    "Please check the address and try again.</p>"
                    "<p><a href='/configs'>← Go back</a></p>"
                ),
                status_code=422,
            )
        destination_lat, destination_lon = coords
        destination_label = destination_address

    district_value = "|".join(locality_district_id) if locality_district_id else None
    config = SearchConfig(
        name=name,
        category_main_cb=category_main_cb,
        category_type_cb=category_type_cb,
        category_sub_cb=category_sub_cb or None,
        locality_region_id=_to_int(locality_region_id),
        locality_district_id=district_value,
        czk_price_min=_to_int(czk_price_min),
        czk_price_max=_to_int(czk_price_max),
        usable_area_min=_to_int(usable_area_min),
        usable_area_max=_to_int(usable_area_max),
        ownership=_to_int(ownership),
        no_auction=no_auction,
        active=True,
        created_at=datetime.now(UTC),
        destination_label=destination_label,
        destination_lat=destination_lat,
        destination_lon=destination_lon,
        travel_mode=travel_mode or None,
    )
    db.add(config)
    db.commit()
    return RedirectResponse(url="/configs", status_code=303)


@router.post("/configs/{config_id}/toggle")
def toggle_config(config_id: int, db: Session = Depends(get_db)):
    config = db.query(SearchConfig).filter_by(id=config_id).first()
    if config:
        config.active = not config.active
        db.commit()
    return RedirectResponse(url="/configs", status_code=303)


@router.post("/configs/{config_id}/delete")
def delete_config(config_id: int, db: Session = Depends(get_db)):
    from shared.models import ScrapeRun
    config = db.query(SearchConfig).filter_by(id=config_id).first()
    if config:
        db.query(ScrapeRun).filter_by(search_config_id=config_id).delete()
        db.delete(config)
        db.commit()
    return RedirectResponse(url="/configs", status_code=303)


@router.post("/trigger")
def trigger_analysis():
    try:
        resp = httpx.post(f"{settings.analyzer_url}/run", timeout=10)
        resp.raise_for_status()
        logger.info("Analysis triggered successfully")
    except Exception:
        logger.exception("Failed to trigger analysis")
    return RedirectResponse(url="/configs", status_code=303)
