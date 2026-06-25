# Stage 0: Go collector build (libpcap + CGO)
FROM golang:1.25-bookworm AS go-build
ARG GOPROXY=https://goproxy.cn,direct
ARG DEBIAN_MIRROR=https://mirrors.aliyun.com/debian
ENV GOPROXY=${GOPROXY} \
    PATH=/usr/local/go/bin:${PATH}
RUN sed -i "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g; s|http://deb.debian.org/debian-security|${DEBIAN_MIRROR}-security|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends libpcap-dev gcc ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY server/go-collector/go.mod server/go-collector/go.sum* ./
RUN go mod download
COPY server/go-collector/ ./
RUN CGO_ENABLED=1 go build -ldflags="-s -w" -o /go-collector .

# Stage 1: Frontend build
FROM node:20-slim AS frontend-build
WORKDIR /src/front-end
COPY front-end/package.json front-end/package-lock.json* ./
RUN npm ci
COPY front-end ./
RUN npm run build

# Stage 2: Final runtime image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIR=/app/front-end/dist \
    GO_COLLECTOR_BIN=/app/bin/go-collector

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpcap0.8 pciutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt

COPY server /app/server
COPY --from=frontend-build /src/front-end/dist /app/front-end/dist
COPY --from=go-build /go-collector /app/bin/go-collector
COPY VERSION /app/VERSION

RUN chmod +x /app/bin/go-collector /app/server/entrypoint.sh

EXPOSE 8088 18088

CMD ["/app/server/entrypoint.sh"]
