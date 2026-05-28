from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from shared.db import get_db
from shared.models import ScrapeRun, SearchConfig
from dashboard.deps import templates

router = APIRouter()


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
    return templates.TemplateResponse(request, "scrapes.html", {"groups": groups})
