# Per-Config Run Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-config "Run now" button to the scrapes page so users can trigger a scrape for one search config instead of all configs at once.

**Architecture:** Extend `run_pipeline` with an optional `config_id` param; expose it via a query param on the scraper's `/run` endpoint; add a new dashboard route `/scrapes/run/{config_id}`; thread `config_id` through `group_runs` so the template can render a per-row form button.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2/Bootstrap, pytest

---

## File Map

| File | Change |
|------|--------|
| `scraper/main.py` | `run_pipeline` gains optional `config_id`; `/run` endpoint accepts query param |
| `dashboard/routers/scrapes.py` | `group_runs` carries `config_id`; DB query selects `SearchConfig.id`; new `/scrapes/run/{config_id}` route |
| `dashboard/templates/scrapes.html` | Per-row "Run" button in each accordion header |
| `tests/scraper/test_main.py` | Two new tests for `run_pipeline(config_id=...)` |
| `tests/dashboard/test_scrapes.py` | Update existing `group_runs` call-sites to 3-tuples; add test for new dashboard route |

---

## Task 1: Extend `run_pipeline` and scraper `/run` endpoint

**Files:**
- Modify: `scraper/main.py:225-276`
- Test: `tests/scraper/test_main.py`

- [ ] **Step 1: Write two failing tests**

Add to the bottom of `tests/scraper/test_main.py`:

```python
def test_run_pipeline_with_config_id_scrapes_only_that_config():
    config_a = SearchConfig(name="PipelineOnlyA", category_main_cb=17, category_type_cb=17, active=True, created_at=datetime.now(UTC))
    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.all.return_value = [config_a]

    with patch("scraper.main.SessionLocal", return_value=mock_db), \
         patch("scraper.main.run_scrape") as mock_run_scrape, \
         patch("scraper.main.settings") as mock_settings:
        mock_settings.mapy_api_key = ""
        mock_settings.analyzer_url = "http://unused"
        run_pipeline(config_id=42)

    mock_run_scrape.assert_called_once()
    assert mock_run_scrape.call_args[0][1] is config_a


def test_run_pipeline_with_unknown_config_id_does_not_scrape():
    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.all.return_value = []

    with patch("scraper.main.SessionLocal", return_value=mock_db), \
         patch("scraper.main.run_scrape") as mock_run_scrape, \
         patch("scraper.main.settings") as mock_settings:
        mock_settings.mapy_api_key = ""
        mock_settings.analyzer_url = "http://unused"
        run_pipeline(config_id=99999)

    mock_run_scrape.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
poetry run pytest tests/scraper/test_main.py::test_run_pipeline_with_config_id_scrapes_only_that_config tests/scraper/test_main.py::test_run_pipeline_with_unknown_config_id_does_not_scrape -v
```

Expected: both FAIL (TypeError: run_pipeline() got an unexpected keyword argument 'config_id')

- [ ] **Step 3: Implement — update `run_pipeline` signature and query**

In `scraper/main.py`, replace:

```python
def run_pipeline() -> None:
    if not _scrape_lock.acquire(blocking=False):
        logger.info("Scrape already running, skipping")
        return
    db = SessionLocal()
    try:
        configs = db.query(SearchConfig).filter_by(active=True).all()
        for config in configs:
            run_scrape(db, config)
```

with:

```python
def run_pipeline(config_id: int | None = None) -> None:
    if not _scrape_lock.acquire(blocking=False):
        logger.info("Scrape already running, skipping")
        return
    db = SessionLocal()
    try:
        if config_id is not None:
            configs = db.query(SearchConfig).filter_by(active=True, id=config_id).all()
        else:
            configs = db.query(SearchConfig).filter_by(active=True).all()
        for config in configs:
            run_scrape(db, config)
```

- [ ] **Step 4: Update the `/run` endpoint to accept `config_id` query param**

In `scraper/main.py`, replace:

```python
@app.post("/run")
def trigger_run(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_pipeline)
    return {"status": "triggered"}
```

with:

```python
@app.post("/run")
def trigger_run(background_tasks: BackgroundTasks, config_id: int | None = None):
    background_tasks.add_task(run_pipeline, config_id)
    return {"status": "triggered"}
```

- [ ] **Step 5: Run new tests to confirm they pass**

```bash
poetry run pytest tests/scraper/test_main.py::test_run_pipeline_with_config_id_scrapes_only_that_config tests/scraper/test_main.py::test_run_pipeline_with_unknown_config_id_does_not_scrape -v
```

Expected: both PASS

- [ ] **Step 6: Run full test suite to confirm no regressions**

```bash
poetry run pytest tests/ -v
```

Expected: all 165 tests PASS

- [ ] **Step 7: Commit**

```bash
git add scraper/main.py tests/scraper/test_main.py
git commit -m "feat: run_pipeline accepts optional config_id to scrape a single config"
```

---

## Task 2: Thread `config_id` through `group_runs` and add dashboard endpoint

**Files:**
- Modify: `dashboard/routers/scrapes.py`
- Test: `tests/dashboard/test_scrapes.py`

- [ ] **Step 1: Update existing `group_runs` tests to use 3-tuples**

In `tests/dashboard/test_scrapes.py`, every call to `group_runs` passes 2-tuples `(run, "Config Name")`. Change all of them to 3-tuples `(run, "Config Name", <id>)`.

Replace every occurrence of this pattern (5 tests total):

```python
rows = [
    (_make_run(t, t_end), "Config A"),
    (_make_run(t, t_end), "Config A"),
    (_make_run(t, t_end), "Config B"),
]
```

with:

```python
rows = [
    (_make_run(t, t_end), "Config A", 1),
    (_make_run(t, t_end), "Config A", 1),
    (_make_run(t, t_end), "Config B", 2),
]
```

Full updated tests section (replace `test_group_runs_groups_by_config_name` through `test_group_runs_empty`):

```python
def test_group_runs_groups_by_config_name():
    t = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t_end = datetime(2026, 1, 1, 10, 1, tzinfo=UTC)
    rows = [
        (_make_run(t, t_end), "Config A", 1),
        (_make_run(t, t_end), "Config A", 1),
        (_make_run(t, t_end), "Config B", 2),
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
        (_make_run(t, t_end), "Config A", 1),
        (_make_run(t, t_end), "Config A", 1),
    ]
    groups = group_runs(rows)
    assert len(groups[0]["runs"]) == 2


def test_group_runs_duration_seconds():
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 10, 1, 30, tzinfo=UTC)
    rows = [(_make_run(start, end), "Config A", 1)]
    groups = group_runs(rows)
    assert groups[0]["runs"][0]["duration"] == 90


def test_group_runs_duration_none_when_running():
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    rows = [(_make_run(start, None, status="running"), "Config A", 1)]
    groups = group_runs(rows)
    assert groups[0]["runs"][0]["duration"] is None


def test_group_runs_empty():
    assert group_runs([]) == []


def test_group_runs_carries_config_id():
    t = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t_end = datetime(2026, 1, 1, 10, 1, tzinfo=UTC)
    rows = [(_make_run(t, t_end), "Config X", 99)]
    groups = group_runs(rows)
    assert groups[0]["config_id"] == 99
```

- [ ] **Step 2: Add test for the new `/scrapes/run/{config_id}` endpoint**

Also add at the bottom of `tests/dashboard/test_scrapes.py`:

```python
def test_trigger_run_single_config_calls_scraper_with_config_id(db_session):
    from unittest.mock import patch, MagicMock
    from shared.config import settings

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with patch("dashboard.routers.scrapes.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        client = TestClient(app, follow_redirects=False)
        response = client.post("/scrapes/run/42")
    app.dependency_overrides.clear()

    mock_post.assert_called_once_with(
        f"{settings.scraper_url}/run",
        params={"config_id": 42},
        timeout=5,
    )
    assert response.status_code == 303
    assert "/scrapes" in response.headers["location"]
```

- [ ] **Step 3: Run new and updated tests to confirm they fail**

```bash
poetry run pytest tests/dashboard/test_scrapes.py -v
```

Expected: `test_group_runs_carries_config_id` FAIL (KeyError: 'config_id'), `test_trigger_run_single_config_calls_scraper_with_config_id` FAIL (404), existing group_runs tests FAIL (too many values to unpack)

- [ ] **Step 4: Implement — update `group_runs` to unpack 3-tuples**

In `dashboard/routers/scrapes.py`, replace:

```python
def group_runs(rows: list[tuple]) -> list[dict]:
    groups: dict[str, dict] = {}
    for run, config_name in rows:
        if config_name not in groups:
            groups[config_name] = {"config_name": config_name, "runs": []}
```

with:

```python
def group_runs(rows: list[tuple]) -> list[dict]:
    groups: dict[str, dict] = {}
    for run, config_name, config_id in rows:
        if config_name not in groups:
            groups[config_name] = {"config_name": config_name, "config_id": config_id, "runs": []}
```

- [ ] **Step 5: Update the DB query to also select `SearchConfig.id`**

In `dashboard/routers/scrapes.py`, replace:

```python
    rows = (
        db.query(ScrapeRun, SearchConfig.name)
        .join(SearchConfig, ScrapeRun.search_config_id == SearchConfig.id)
        .order_by(ScrapeRun.started_at.desc())
        .all()
    )
    groups = group_runs(rows)
    grouped_names = {g["config_name"] for g in groups}
    for config in db.query(SearchConfig).order_by(SearchConfig.name).all():
        if config.name not in grouped_names:
            groups.append({"config_name": config.name, "runs": []})
```

with:

```python
    rows = (
        db.query(ScrapeRun, SearchConfig.name, SearchConfig.id)
        .join(SearchConfig, ScrapeRun.search_config_id == SearchConfig.id)
        .order_by(ScrapeRun.started_at.desc())
        .all()
    )
    groups = group_runs(rows)
    grouped_names = {g["config_name"] for g in groups}
    for config in db.query(SearchConfig).order_by(SearchConfig.name).all():
        if config.name not in grouped_names:
            groups.append({"config_name": config.name, "config_id": config.id, "runs": []})
```

- [ ] **Step 6: Add the new dashboard endpoint**

In `dashboard/routers/scrapes.py`, add after the existing `trigger_run` function:

```python
@router.post("/scrapes/run/{config_id}")
def trigger_run_config(config_id: int):
    try:
        httpx.post(f"{settings.scraper_url}/run", params={"config_id": config_id}, timeout=5)
    except Exception:
        pass
    return RedirectResponse("/scrapes?triggered=1", status_code=303)
```

- [ ] **Step 7: Run tests to confirm they pass**

```bash
poetry run pytest tests/dashboard/test_scrapes.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 8: Run full test suite**

```bash
poetry run pytest tests/ -v
```

Expected: all 167 tests PASS

- [ ] **Step 9: Commit**

```bash
git add dashboard/routers/scrapes.py tests/dashboard/test_scrapes.py
git commit -m "feat: add per-config run endpoint and thread config_id through group_runs"
```

---

## Task 3: Add per-config "Run" button to the scrapes template

**Files:**
- Modify: `dashboard/templates/scrapes.html`

No unit test for template markup; the integration test `test_scrape_log_includes_running_run` will catch regressions.

- [ ] **Step 1: Restructure each accordion header to include a "Run" button**

In `dashboard/templates/scrapes.html`, replace:

```html
    <h2 class="accordion-header">
      <button class="accordion-button collapsed" type="button"
              data-bs-toggle="collapse" data-bs-target="#{{ loop_id }}">
        {{ group.config_name }}
        <span class="ms-2 text-muted small">{{ group.runs | length }} run{{ 's' if group.runs | length != 1 }}</span>
        {% if group.runs %}
          {% set last = group.runs[0] %}
          {% if last.status == "success" %}
            <span class="badge bg-success ms-2">success</span>
          {% elif last.status == "error" %}
            <span class="badge bg-danger ms-2">error</span>
          {% else %}
            <span class="badge bg-warning text-dark ms-2">{{ last.status }}</span>
          {% endif %}
        {% else %}
          <span class="badge bg-secondary ms-2">no runs</span>
        {% endif %}
      </button>
    </h2>
```

with:

```html
    <h2 class="accordion-header d-flex align-items-stretch">
      <button class="accordion-button collapsed flex-grow-1" type="button"
              data-bs-toggle="collapse" data-bs-target="#{{ loop_id }}">
        {{ group.config_name }}
        <span class="ms-2 text-muted small">{{ group.runs | length }} run{{ 's' if group.runs | length != 1 }}</span>
        {% if group.runs %}
          {% set last = group.runs[0] %}
          {% if last.status == "success" %}
            <span class="badge bg-success ms-2">success</span>
          {% elif last.status == "error" %}
            <span class="badge bg-danger ms-2">error</span>
          {% else %}
            <span class="badge bg-warning text-dark ms-2">{{ last.status }}</span>
          {% endif %}
        {% else %}
          <span class="badge bg-secondary ms-2">no runs</span>
        {% endif %}
      </button>
      <form method="post" action="/scrapes/run/{{ group.config_id }}"
            class="d-flex align-items-center px-2 border-start">
        <button type="submit" class="btn btn-outline-primary btn-sm">Run</button>
      </form>
    </h2>
```

- [ ] **Step 2: Run full test suite**

```bash
poetry run pytest tests/ -v
```

Expected: all 167 tests PASS

- [ ] **Step 3: Commit**

```bash
git add dashboard/templates/scrapes.html
git commit -m "feat: add per-config Run button to scrapes page accordion header"
```
