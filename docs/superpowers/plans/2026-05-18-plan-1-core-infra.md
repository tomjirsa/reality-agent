# Core Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap the project skeleton — Docker Compose, shared SQLAlchemy models, Alembic migrations, and service Dockerfiles.

**Architecture:** Four Docker services (`db`, `scraper`, `analyzer`, `dashboard`) share a common `shared/` Python package containing models, DB session factory, and config. Each service Dockerfile builds with the project root as context, copies `shared/` alongside service-specific code.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x, Alembic, pydantic-settings 2.x, PostgreSQL 16, Docker Compose

---

## File Map

| File | Responsibility |
|------|---------------|
| `docker-compose.yml` | Orchestrate all 4 services with health checks |
| `.env.example` | Document all required env vars |
| `.gitignore` | Exclude `.env`, `__pycache__`, `.pytest_cache` |
| `shared/__init__.py` | Empty package marker |
| `shared/config.py` | `Settings` class via pydantic-settings; module-level `settings` singleton |
| `shared/models.py` | All 5 SQLAlchemy 2.x ORM models |
| `shared/db.py` | `engine`, `SessionLocal`, `get_db()` generator |
| `alembic.ini` | Alembic config pointing at `migrations/` |
| `migrations/env.py` | Alembic env wiring `settings.postgres_url` and `Base.metadata` |
| `migrations/script.py.mako` | Default Alembic template |
| `migrations/versions/0001_initial_schema.py` | DDL for all 5 tables |
| `scraper/Dockerfile` | Python 3.12-slim, copies shared/ + scraper/ |
| `scraper/requirements.txt` | sqlalchemy, psycopg2-binary, pydantic-settings, httpx, apscheduler |
| `analyzer/Dockerfile` | Python 3.12-slim, copies shared/ + analyzer/ |
| `analyzer/requirements.txt` | sqlalchemy, psycopg2-binary, pydantic-settings, apscheduler, fastapi, uvicorn |
| `dashboard/Dockerfile` | Python 3.12-slim, copies shared/ + dashboard/ |
| `dashboard/requirements.txt` | sqlalchemy, psycopg2-binary, pydantic-settings, fastapi, uvicorn, jinja2, httpx |
| `requirements-dev.txt` | pytest, pytest-asyncio, httpx, sqlalchemy, pydantic-settings, alembic |
| `tests/__init__.py` | Empty |
| `tests/conftest.py` | SQLite in-memory engine, `db` session fixture |
| `tests/shared/__init__.py` | Empty |
| `tests/shared/test_config.py` | Verify Settings defaults and env override |
| `tests/shared/test_models.py` | Create/query each model via SQLite |

---

### Task 1: Project skeleton

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `shared/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/shared/__init__.py`
- Create: `scraper/__init__.py`
- Create: `analyzer/__init__.py`
- Create: `dashboard/__init__.py`
- Create: `dashboard/routers/__init__.py`
- Create: `dashboard/templates/.gitkeep`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p shared scraper analyzer dashboard/routers dashboard/templates \
         migrations/versions tests/shared tests/scraper tests/analyzer tests/dashboard
touch shared/__init__.py scraper/__init__.py analyzer/__init__.py \
      dashboard/__init__.py dashboard/routers/__init__.py \
      tests/__init__.py tests/shared/__init__.py tests/scraper/__init__.py \
      tests/analyzer/__init__.py tests/dashboard/__init__.py
```

- [ ] **Step 2: Write `.gitignore`**

```
.env
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
*.egg-info/
dist/
build/
.venv/
```

- [ ] **Step 3: Write `.env.example`**

```
POSTGRES_URL=postgresql://user:pass@db:5432/reality

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=app-password-here
ALERT_EMAIL=you@gmail.com

SCRAPE_INTERVAL_HOURS=6
BARGAIN_SCORE_THRESHOLD=70
HOT_OFFER_MAX_DAYS=7

ANALYZER_URL=http://analyzer:8081
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore .env.example shared/__init__.py scraper/__init__.py \
        analyzer/__init__.py dashboard/__init__.py dashboard/routers/__init__.py \
        tests/__init__.py tests/shared/__init__.py tests/scraper/__init__.py \
        tests/analyzer/__init__.py tests/dashboard/__init__.py
git commit -m "chore: project skeleton with directory structure"
```

---

### Task 2: shared/config.py + tests

**Files:**
- Create: `shared/config.py`
- Create: `tests/shared/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/shared/test_config.py
import os
import pytest

def test_settings_defaults():
    from shared.config import Settings
    s = Settings(postgres_url="postgresql://localhost/test")
    assert s.scrape_interval_hours == 6
    assert s.bargain_score_threshold == 70.0
    assert s.hot_offer_max_days == 7
    assert s.smtp_port == 587

def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgresql://localhost/test")
    monkeypatch.setenv("HOT_OFFER_MAX_DAYS", "14")
    monkeypatch.setenv("SCRAPE_INTERVAL_HOURS", "12")
    from importlib import reload
    import shared.config as cfg_module
    reload(cfg_module)
    assert cfg_module.settings.hot_offer_max_days == 14
    assert cfg_module.settings.scrape_interval_hours == 12
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/shared/test_config.py -v
```
Expected: `ImportError: No module named 'shared.config'`

- [ ] **Step 3: Write `shared/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_url: str = "postgresql://user:pass@db:5432/reality"
    analyzer_url: str = "http://analyzer:8081"

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email: str = ""

    scrape_interval_hours: int = 6
    bargain_score_threshold: float = 70.0
    hot_offer_max_days: int = 7


settings = Settings()
```

- [ ] **Step 4: Install pydantic-settings**

```bash
pip install pydantic-settings==2.2.1
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/shared/test_config.py -v
```
Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add shared/config.py tests/shared/test_config.py
git commit -m "feat: shared config via pydantic-settings"
```

---

### Task 3: shared/models.py + tests

**Files:**
- Create: `shared/models.py`
- Create: `tests/shared/test_models.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write `tests/conftest.py`**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="session")
def test_engine():
    from shared.models import Base
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db(test_engine):
    Session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.rollback()
    session.close()
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/shared/test_models.py
from datetime import datetime, timezone
import pytest


UTC = timezone.utc


def test_create_search_config(db):
    from shared.models import SearchConfig
    config = SearchConfig(
        name="Praha byty prodej",
        category_main_cb=1,
        category_type_cb=1,
        created_at=datetime.now(UTC),
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    assert config.id is not None
    assert config.active is True
    assert config.no_auction is True


def test_create_listing(db):
    from shared.models import Listing
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=9999000001,
        name="Byt 3+kk 80m²",
        price_czk=5_900_000,
        area_m2=80,
        price_per_m2=73_750.0,
        category_main_cb=1,
        category_type_cb=1,
        is_active=True,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    assert listing.hash_id == 9999000001
    assert listing.is_new_flag is False


def test_create_price_history(db):
    from shared.models import Listing, ListingPriceHistory
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=9999000002,
        name="Byt 2+kk",
        price_czk=4_000_000,
        category_main_cb=1,
        category_type_cb=1,
        is_active=True,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(listing)
    db.flush()
    history = ListingPriceHistory(
        hash_id=9999000002,
        price_czk=4_200_000,
        price_per_m2=52_500.0,
        recorded_at=now,
    )
    db.add(history)
    db.commit()
    results = db.query(ListingPriceHistory).filter_by(hash_id=9999000002).all()
    assert len(results) == 1
    assert results[0].price_czk == 4_200_000


def test_create_listing_score(db):
    from shared.models import Listing, ListingScore
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=9999000003,
        name="Byt 1+kk",
        price_czk=3_000_000,
        category_main_cb=1,
        category_type_cb=1,
        is_active=True,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(listing)
    db.flush()
    score = ListingScore(
        hash_id=9999000003,
        price_percentile=15.0,
        price_per_m2_percentile=20.0,
        days_on_market=3,
        had_price_drop=False,
        is_hot=True,
        combined_score=82.5,
        computed_at=now,
    )
    db.add(score)
    db.commit()
    result = db.query(ListingScore).filter_by(hash_id=9999000003).one()
    assert result.is_hot is True
    assert result.combined_score == pytest.approx(82.5)


def test_create_scrape_run(db):
    from shared.models import SearchConfig, ScrapeRun
    now = datetime.now(UTC)
    config = SearchConfig(
        name="Test Config",
        category_main_cb=1,
        category_type_cb=1,
        created_at=now,
    )
    db.add(config)
    db.flush()
    run = ScrapeRun(
        search_config_id=config.id,
        started_at=now,
        listings_found=10,
        listings_new=2,
        listings_updated=1,
        listings_removed=0,
        status="success",
    )
    db.add(run)
    db.commit()
    result = db.query(ScrapeRun).filter_by(search_config_id=config.id).one()
    assert result.status == "success"
    assert result.listings_found == 10
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/shared/test_models.py -v
```
Expected: `ImportError: No module named 'shared.models'`

- [ ] **Step 4: Write `shared/models.py`**

```python
from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, Boolean, Float, Integer, Text, ForeignKey
from sqlalchemy.types import JSON, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SearchConfig(Base):
    __tablename__ = "search_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category_main_cb: Mapped[int] = mapped_column(Integer, nullable=False)
    category_type_cb: Mapped[int] = mapped_column(Integer, nullable=False)
    category_sub_cb: Mapped[Optional[str]] = mapped_column(Text)
    locality_region_id: Mapped[Optional[int]] = mapped_column(Integer)
    locality_district_id: Mapped[Optional[int]] = mapped_column(Integer)
    czk_price_min: Mapped[Optional[int]] = mapped_column(Integer)
    czk_price_max: Mapped[Optional[int]] = mapped_column(Integer)
    usable_area_min: Mapped[Optional[int]] = mapped_column(Integer)
    usable_area_max: Mapped[Optional[int]] = mapped_column(Integer)
    ownership: Mapped[Optional[int]] = mapped_column(Integer)
    no_auction: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class Listing(Base):
    __tablename__ = "listings"

    hash_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price_czk: Mapped[Optional[int]] = mapped_column(Integer)
    area_m2: Mapped[Optional[int]] = mapped_column(Integer)
    price_per_m2: Mapped[Optional[float]] = mapped_column(Float)
    locality: Mapped[Optional[str]] = mapped_column(Text)
    locality_district_id: Mapped[Optional[int]] = mapped_column(Integer)
    locality_region_id: Mapped[Optional[int]] = mapped_column(Integer)
    floor: Mapped[Optional[str]] = mapped_column(Text)
    building_type: Mapped[Optional[str]] = mapped_column(Text)
    ownership: Mapped[Optional[str]] = mapped_column(Text)
    condition: Mapped[Optional[str]] = mapped_column(Text)
    category_main_cb: Mapped[int] = mapped_column(Integer, nullable=False)
    category_type_cb: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_new_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    removed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    days_to_sell: Mapped[Optional[int]] = mapped_column(Integer)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON)


class ListingPriceHistory(Base):
    __tablename__ = "listing_price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hash_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.hash_id"), nullable=False
    )
    price_czk: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_m2: Mapped[Optional[float]] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class ListingScore(Base):
    __tablename__ = "listing_scores"

    hash_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.hash_id"), primary_key=True
    )
    price_percentile: Mapped[Optional[float]] = mapped_column(Float)
    price_per_m2_percentile: Mapped[Optional[float]] = mapped_column(Float)
    days_on_market: Mapped[Optional[int]] = mapped_column(Integer)
    had_price_drop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    price_drop_pct: Mapped[Optional[float]] = mapped_column(Float)
    is_hot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    combined_score: Mapped[Optional[float]] = mapped_column(Float)
    alerted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    computed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("search_configs.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    listings_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_removed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="running", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
```

- [ ] **Step 5: Install sqlalchemy**

```bash
pip install sqlalchemy==2.0.30
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/shared/test_models.py -v
```
Expected: 5 PASSED

- [ ] **Step 7: Commit**

```bash
git add shared/models.py tests/conftest.py tests/shared/test_models.py
git commit -m "feat: SQLAlchemy models for all 5 tables + tests"
```

---

### Task 4: shared/db.py

**Files:**
- Create: `shared/db.py`

No separate test needed — `tests/conftest.py` already validates session creation. `db.py` is a thin wrapper; it'll be exercised by integration tests in Plans 2–4.

- [ ] **Step 1: Write `shared/db.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from shared.config import settings

engine = create_engine(settings.postgres_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 2: Commit**

```bash
git add shared/db.py
git commit -m "feat: shared DB session factory"
```

---

### Task 5: Alembic setup + initial migration

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/0001_initial_schema.py`

- [ ] **Step 1: Install alembic**

```bash
pip install alembic==1.13.1
```

- [ ] **Step 2: Write `alembic.ini`**

```ini
[alembic]
script_location = migrations
prepend_sys_path = .
version_path_separator = os

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 3: Write `migrations/env.py`**

```python
import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from shared.config import settings
from shared.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.postgres_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Write `migrations/script.py.mako`**

```
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 5: Write `migrations/versions/0001_initial_schema.py`**

```python
"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-18
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category_main_cb", sa.Integer(), nullable=False),
        sa.Column("category_type_cb", sa.Integer(), nullable=False),
        sa.Column("category_sub_cb", sa.Text(), nullable=True),
        sa.Column("locality_region_id", sa.Integer(), nullable=True),
        sa.Column("locality_district_id", sa.Integer(), nullable=True),
        sa.Column("czk_price_min", sa.Integer(), nullable=True),
        sa.Column("czk_price_max", sa.Integer(), nullable=True),
        sa.Column("usable_area_min", sa.Integer(), nullable=True),
        sa.Column("usable_area_max", sa.Integer(), nullable=True),
        sa.Column("ownership", sa.Integer(), nullable=True),
        sa.Column("no_auction", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "listings",
        sa.Column("hash_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("price_czk", sa.Integer(), nullable=True),
        sa.Column("area_m2", sa.Integer(), nullable=True),
        sa.Column("price_per_m2", sa.Float(), nullable=True),
        sa.Column("locality", sa.Text(), nullable=True),
        sa.Column("locality_district_id", sa.Integer(), nullable=True),
        sa.Column("locality_region_id", sa.Integer(), nullable=True),
        sa.Column("floor", sa.Text(), nullable=True),
        sa.Column("building_type", sa.Text(), nullable=True),
        sa.Column("ownership", sa.Text(), nullable=True),
        sa.Column("condition", sa.Text(), nullable=True),
        sa.Column("category_main_cb", sa.Integer(), nullable=False),
        sa.Column("category_type_cb", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_new_flag", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("removed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("days_to_sell", sa.Integer(), nullable=True),
        sa.Column("raw_json", JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("hash_id"),
    )
    op.create_index("ix_listings_is_active", "listings", ["is_active"])
    op.create_index(
        "ix_listings_peer_group",
        "listings",
        ["category_main_cb", "category_type_cb", "locality_district_id"],
    )
    op.create_table(
        "listing_price_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("hash_id", sa.BigInteger(), nullable=False),
        sa.Column("price_czk", sa.Integer(), nullable=False),
        sa.Column("price_per_m2", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hash_id"], ["listings.hash_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "listing_scores",
        sa.Column("hash_id", sa.BigInteger(), nullable=False),
        sa.Column("price_percentile", sa.Float(), nullable=True),
        sa.Column("price_per_m2_percentile", sa.Float(), nullable=True),
        sa.Column("days_on_market", sa.Integer(), nullable=True),
        sa.Column("had_price_drop", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("price_drop_pct", sa.Float(), nullable=True),
        sa.Column("is_hot", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("combined_score", sa.Float(), nullable=True),
        sa.Column("alerted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hash_id"], ["listings.hash_id"]),
        sa.PrimaryKeyConstraint("hash_id"),
    )
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("search_config_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("listings_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("listings_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("listings_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("listings_removed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["search_config_id"], ["search_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("scrape_runs")
    op.drop_table("listing_scores")
    op.drop_table("listing_price_history")
    op.drop_index("ix_listings_peer_group", table_name="listings")
    op.drop_index("ix_listings_is_active", table_name="listings")
    op.drop_table("listings")
    op.drop_table("search_configs")
```

- [ ] **Step 6: Verify alembic can parse the migration (dry run)**

```bash
alembic upgrade head --sql
```
Expected: SQL DDL printed to stdout (no errors). This does NOT require a running DB.

- [ ] **Step 7: Commit**

```bash
git add alembic.ini migrations/
git commit -m "feat: alembic setup + initial schema migration"
```

---

### Task 6: Docker Compose + Dockerfiles

**Files:**
- Create: `docker-compose.yml`
- Create: `scraper/requirements.txt`
- Create: `scraper/Dockerfile`
- Create: `analyzer/requirements.txt`
- Create: `analyzer/Dockerfile`
- Create: `dashboard/requirements.txt`
- Create: `dashboard/Dockerfile`
- Create: `requirements-dev.txt`

- [ ] **Step 1: Write `scraper/requirements.txt`**

```
sqlalchemy==2.0.30
psycopg2-binary==2.9.9
pydantic-settings==2.2.1
httpx==0.27.0
apscheduler==3.10.4
alembic==1.13.1
```

- [ ] **Step 2: Write `scraper/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY shared/ ./shared/
COPY scraper/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY scraper/ ./scraper/
CMD ["python", "-m", "scraper.main"]
```

- [ ] **Step 3: Write `analyzer/requirements.txt`**

```
sqlalchemy==2.0.30
psycopg2-binary==2.9.9
pydantic-settings==2.2.1
apscheduler==3.10.4
fastapi==0.111.0
uvicorn[standard]==0.29.0
httpx==0.27.0
alembic==1.13.1
```

- [ ] **Step 4: Write `analyzer/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY shared/ ./shared/
COPY analyzer/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY analyzer/ ./analyzer/
CMD ["python", "-m", "analyzer.main"]
```

- [ ] **Step 5: Write `dashboard/requirements.txt`**

```
sqlalchemy==2.0.30
psycopg2-binary==2.9.9
pydantic-settings==2.2.1
fastapi==0.111.0
uvicorn[standard]==0.29.0
jinja2==3.1.4
httpx==0.27.0
```

- [ ] **Step 6: Write `dashboard/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY shared/ ./shared/
COPY dashboard/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY dashboard/ ./dashboard/
CMD ["uvicorn", "dashboard.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 7: Write `requirements-dev.txt`**

```
pytest==8.2.0
pytest-asyncio==0.23.6
httpx==0.27.0
sqlalchemy==2.0.30
pydantic-settings==2.2.1
alembic==1.13.1
```

- [ ] **Step 8: Write `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: reality
      POSTGRES_USER: ${POSTGRES_USER:-user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-pass}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-user}"]
      interval: 5s
      timeout: 5s
      retries: 10

  scraper:
    build:
      context: .
      dockerfile: scraper/Dockerfile
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  analyzer:
    build:
      context: .
      dockerfile: analyzer/Dockerfile
    env_file: .env
    ports:
      - "8081:8081"
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  dashboard:
    build:
      context: .
      dockerfile: dashboard/Dockerfile
    env_file: .env
    ports:
      - "8080:8080"
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

volumes:
  pgdata:
```

- [ ] **Step 9: Verify docker-compose.yml is valid**

```bash
docker compose config --quiet
```
Expected: no errors

- [ ] **Step 10: Commit**

```bash
git add docker-compose.yml scraper/Dockerfile scraper/requirements.txt \
        analyzer/Dockerfile analyzer/requirements.txt \
        dashboard/Dockerfile dashboard/requirements.txt \
        requirements-dev.txt
git commit -m "feat: Docker Compose and service Dockerfiles"
```

---

### Task 7: Run full test suite

- [ ] **Step 1: Install dev dependencies**

```bash
pip install -r requirements-dev.txt
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/ -v
```
Expected: 7 PASSED (2 config + 5 models)

- [ ] **Step 3: Commit if any fixes were needed**

```bash
git add -p
git commit -m "fix: test suite green"
```
