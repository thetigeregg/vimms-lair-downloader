FROM python:3.11-slim AS extract-xiso-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --branch build-202505152050 --depth 1 https://github.com/XboxDev/extract-xiso.git /src \
    && cmake -S /src -B /src/build \
    && cmake --build /src/build --target extract-xiso


FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        aria2 \
        p7zip-full \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=extract-xiso-builder /src/build/extract-xiso /usr/local/bin/extract-xiso

WORKDIR /app
COPY pyproject.toml README.md ./
COPY vimms_downloader ./vimms_downloader
RUN pip install --no-cache-dir .

CMD ["sleep", "infinity"]
