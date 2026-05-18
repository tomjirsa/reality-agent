FROM python:3.12-slim
WORKDIR /app
COPY shared/ ./shared/
COPY analyzer/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY analyzer/ ./analyzer/
CMD ["python", "-m", "analyzer.main"]
