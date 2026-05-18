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

router = APIRouter()
logger = logging.getLogger(__name__)
UTC = timezone.utc


@router.get("/configs", response_class=HTMLResponse)
def list_configs(request: Request, db: Session = Depends(get_db)):
    configs = db.query(SearchConfig).order_by(SearchConfig.id).all()
    return templates.TemplateResponse(request, "configs.html", {"configs": configs})


@router.post("/configs")
def create_config(
    db: Session = Depends(get_db),
    name: str = Form(...),
    category_main_cb: int = Form(...),
    category_type_cb: int = Form(...),
    category_sub_cb: str = Form(None),
    locality_region_id: int = Form(None),
    locality_district_id: int = Form(None),
    czk_price_min: int = Form(None),
    czk_price_max: int = Form(None),
    usable_area_min: int = Form(None),
    usable_area_max: int = Form(None),
    ownership: int = Form(None),
    no_auction: bool = Form(True),
):
    config = SearchConfig(
        name=name,
        category_main_cb=category_main_cb,
        category_type_cb=category_type_cb,
        category_sub_cb=category_sub_cb,
        locality_region_id=locality_region_id,
        locality_district_id=locality_district_id,
        czk_price_min=czk_price_min,
        czk_price_max=czk_price_max,
        usable_area_min=usable_area_min,
        usable_area_max=usable_area_max,
        ownership=ownership,
        no_auction=no_auction,
        active=True,
        created_at=datetime.now(UTC),
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
    config = db.query(SearchConfig).filter_by(id=config_id).first()
    if config:
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
