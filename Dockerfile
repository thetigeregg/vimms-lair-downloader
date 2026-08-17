FROM python:3.11-slim AS tools-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        pkg-config \
        libzstd-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --branch build-202505152050 --depth 1 https://github.com/XboxDev/extract-xiso.git /src/extract-xiso \
    && cmake -S /src/extract-xiso -B /src/extract-xiso/build \
    && cmake --build /src/extract-xiso/build --target extract-xiso

RUN git clone --branch v0.1.2 --depth 1 https://github.com/Exzap/ZArchive.git /src/zarchive \
    && cmake -S /src/zarchive -B /src/zarchive/build \
    && cmake --build /src/zarchive/build --target zarchiveTool


FROM python:3.11-slim

ARG FZF_VERSION=0.74.3

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        aria2 \
        p7zip-full \
        libzstd1 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL "https://github.com/junegunn/fzf/releases/download/v${FZF_VERSION}/fzf-${FZF_VERSION}-linux_${ARCH}.tar.gz" \
        | tar -xz -C /usr/local/bin fzf

COPY --from=tools-builder /src/extract-xiso/build/extract-xiso /usr/local/bin/extract-xiso
COPY --from=tools-builder /src/zarchive/build/zarchive /usr/local/bin/zarchive

WORKDIR /app
COPY pyproject.toml README.md ./
COPY vimms_downloader ./vimms_downloader
RUN pip install --no-cache-dir .

CMD ["sleep", "infinity"]
