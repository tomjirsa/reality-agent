# Deployment Guide

The stack runs as four Docker Compose services: `db` (PostgreSQL 16), `scraper`, `analyzer`, and `dashboard`.

## Prerequisites

- Docker and Docker Compose installed on the NAS
- A [mapy.cz API key](https://developer.mapy.cz/) for travel distance enrichment (optional but recommended)

## First-time setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/tomjirsa/reality-agent.git
   cd reality-agent
   ```

2. **Create `.env`** from the template and fill in your values:
   ```bash
   cp .env.example .env
   ```
   Required values to set:
   ```env
   POSTGRES_PASSWORD=yourpassword
   SREALITY_USERNAME=your-seznam-email@seznam.cz
   SREALITY_PASSWORD=your-seznam-password
   SMTP_PASSWORD=your-smtp-app-password
   ```

3. **Build and start all services:**
   ```bash
   docker compose up -d --build
   ```

4. **Run database migrations:**
   ```bash
   docker compose exec scraper alembic upgrade head
   ```

The dashboard is available at `http://<nas-ip>:446`.

## Updating to a new version

1. **Pull latest code:**
   ```bash
   git pull
   ```

2. **Rebuild and restart:**
   ```bash
   docker compose up -d --build
   ```

3. **Apply any new migrations:**
   ```bash
   docker compose exec scraper alembic upgrade head
   ```

Migrations are always safe on existing data (additive only).

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `POSTGRES_URL` | yes | Full SQLAlchemy connection string (e.g. `postgresql://user:pass@db:5432/reality`) |
| `POSTGRES_PASSWORD` | yes | PostgreSQL password (also used by the `db` container) |
| `SREALITY_USERNAME` | yes | Seznam account email used to authenticate with the Sreality v1 API |
| `SREALITY_PASSWORD` | yes | Password for the Seznam account above |
| `SMTP_HOST` | no | SMTP server for price-drop alerts |
| `SMTP_USER` | no | SMTP login |
| `SMTP_PASSWORD` | no | SMTP app password |
| `ALERT_EMAIL` | no | Address to send alerts to |
| `MAPY_API_KEY` | no | mapy.cz API key for travel distance enrichment. Leave empty to skip enrichment. |

## Ports

| Port | Service |
|---|---|
| `446` | Dashboard (web UI) |
| `8081` | Analyzer (internal API, not needed externally) |

## Useful commands

```bash
# View logs for a specific service
docker compose logs -f scraper

# Restart a single service
docker compose restart dashboard

# Stop everything
docker compose down

# Stop and remove all data (destructive)
docker compose down -v
```
