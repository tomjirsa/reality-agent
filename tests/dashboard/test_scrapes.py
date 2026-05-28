from datetime import datetime, timezone
from dashboard.routers.scrapes import group_runs
from shared.models import ScrapeRun

UTC = timezone.utc


def _make_run(started_at, finished_at=None, status="success", **kwargs):
    run = ScrapeRun(
        search_config_id=1,
        started_at=started_at,
        finished_at=finished_at,
        listings_found=kwargs.get("listings_found", 5),
        listings_new=kwargs.get("listings_new", 1),
        listings_updated=kwargs.get("listings_updated", 0),
        listings_removed=kwargs.get("listings_removed", 0),
        status=status,
        error_message=kwargs.get("error_message"),
    )
    return run


def test_group_runs_groups_by_config_name():
    t = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t_end = datetime(2026, 1, 1, 10, 1, tzinfo=UTC)
    rows = [
        (_make_run(t, t_end), "Config A"),
        (_make_run(t, t_end), "Config A"),
        (_make_run(t, t_end), "Config B"),
    ]
    groups = group_runs(rows)
    names = [g["config_name"] for g in groups]
    assert "Config A" in names
    assert "Config B" in names
    assert len(groups) == 2


def test_group_runs_run_count():
    t = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t_end = datetime(2026, 1, 1, 10, 1, tzinfo=UTC)
    rows = [
        (_make_run(t, t_end), "Config A"),
        (_make_run(t, t_end), "Config A"),
    ]
    groups = group_runs(rows)
    assert len(groups[0]["runs"]) == 2


def test_group_runs_duration_seconds():
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 10, 1, 30, tzinfo=UTC)
    rows = [(_make_run(start, end), "Config A")]
    groups = group_runs(rows)
    assert groups[0]["runs"][0]["duration"] == 90


def test_group_runs_duration_none_when_running():
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    rows = [(_make_run(start, None, status="running"), "Config A")]
    groups = group_runs(rows)
    assert groups[0]["runs"][0]["duration"] is None


def test_group_runs_empty():
    assert group_runs([]) == []
