FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        aria2 \
        p7zip-full \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY vimms_downloader ./vimms_downloader
RUN pip install --no-cache-dir .

CMD ["sleep", "infinity"]
