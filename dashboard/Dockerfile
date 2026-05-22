FROM python:3.12-slim
WORKDIR /app
COPY shared/ ./shared/
COPY enricher/ ./enricher/
COPY dashboard/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY dashboard/ ./dashboard/
CMD ["uvicorn", "dashboard.main:app", "--host", "0.0.0.0", "--port", "8080"]
