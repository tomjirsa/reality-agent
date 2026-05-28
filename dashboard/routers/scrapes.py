from datetime import datetime, timedelta, timezone
import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from shared.config import settings
from shared.db import get_db
from shared.models import ScrapeRun, SearchConfig
from dashboard.deps import templates

router = APIRouter()

UTC = timezone.utc


def group_runs(rows: list[tuple]) -> list[dict]:
    groups: dict[str, dict] = {}
    for run, config_name in rows:
        if config_name not in groups:
            groups[config_name] = {"config_name": config_name, "runs": []}
        duration = None
        if run.finished_at and run.started_at:
            duration = int((run.finished_at - run.started_at).total_seconds())
        groups[config_name]["runs"].append({
            "started_at": run.started_at,
            "listings_found": run.listings_found,
            "listings_new": run.listings_new,
            "listings_updated": run.listings_updated,
            "listings_removed": run.listings_removed,
            "duration": duration,
            "status": run.status,
            "error_message": run.error_message,
        })
    return list(groups.values())


@router.get("/scrapes", response_class=HTMLResponse)
def scrape_log(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(ScrapeRun, SearchConfig.name)
        .join(SearchConfig, ScrapeRun.search_config_id == SearchConfig.id)
        .order_by(ScrapeRun.started_at.desc())
        .all()
    )
    groups = group_runs(rows)

    last_run = db.query(ScrapeRun).order_by(ScrapeRun.started_at.desc()).first()
    next_run = None
    if last_run:
        next_run = last_run.started_at + timedelta(hours=settings.scrape_interval_hours)

    return templates.TemplateResponse(request, "scrapes.html", {
        "groups": groups,
        "next_run": next_run,
        "now": datetime.now(UTC),
        "interval_hours": settings.scrape_interval_hours,
    })


@router.post("/scrapes/run")
def trigger_run():
    try:
        httpx.post(f"{settings.scraper_url}/run", timeout=5)
    except Exception:
        pass
    return RedirectResponse("/scrapes?triggered=1", status_code=303)
