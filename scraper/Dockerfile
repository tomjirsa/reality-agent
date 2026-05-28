FROM python:3.12-slim
WORKDIR /app
COPY shared/ ./shared/
COPY enricher/ ./enricher/
COPY migrations/ ./migrations/
COPY alembic.ini ./alembic.ini
COPY scraper/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps
COPY scraper/ ./scraper/
CMD ["python", "-m", "scraper.main"]
