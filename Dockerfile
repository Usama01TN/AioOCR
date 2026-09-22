FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY ocrroute ./ocrroute
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir -e ".[api,local]"

ENV OCRROUTE_HOME=/data
ENV OCRROUTE_HOST=0.0.0.0
ENV OCRROUTE_PORT=20256
VOLUME ["/data"]
EXPOSE 20256

CMD ["ocrroute", "serve", "--host", "0.0.0.0", "--port", "20256"]
