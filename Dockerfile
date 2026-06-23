FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY data/ data/

RUN mkdir -p /app/data/market/packages

VOLUME ["/app/data"]

EXPOSE 8321

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8321/api/v1/health')"

CMD ["python", "-m", "uvicorn", "src.market.server:app", "--host", "0.0.0.0", "--port", "8321"]
