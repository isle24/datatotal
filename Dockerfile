# Stage 0: Go collector build (libpcap + CGO)
FROM golang:1.24-alpine AS go-build
RUN apk add --no-cache libpcap-dev gcc musl-dev
WORKDIR /src
COPY server/go-collector/go.mod server/go-collector/go.sum* ./
RUN go mod download 2>/dev/null || true
COPY server/go-collector/ ./
RUN CGO_ENABLED=1 go build -ldflags="-s -w" -o /go-collector .

# Stage 1: eBPF program compilation (only for Linux amd64/arm64)
FROM golang:1.24-alpine AS ebpf-build
RUN apk add --no-cache clang llvm libbpf-dev linux-headers gcc musl-dev
WORKDIR /src
COPY server/go-collector/go.mod server/go-collector/go.sum* ./
RUN go mod download 2>/dev/null || true
COPY server/go-collector/ ./
# Generate eBPF Go bindings and build ebpf-capable binary
RUN go generate ./ebpf/... 2>/dev/null || true
RUN CGO_ENABLED=1 go build -tags=ebpf -ldflags="-s -w" -o /go-collector-ebpf ./cmd/ebpf-collector/

# Stage 2: Frontend build
FROM node:20-slim AS frontend-build
WORKDIR /src/front-end
COPY front-end/package.json front-end/package-lock.json* ./
RUN npm ci
COPY front-end ./
RUN npm run build

# Stage 3: Final runtime image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIR=/app/front-end/dist \
    GO_COLLECTOR_BIN=/app/bin/go-collector \
    GO_COLLECTOR_EBPF_BIN=/app/bin/go-collector-ebpf

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpcap0.8 pciutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt

COPY server /app/server
COPY --from=frontend-build /src/front-end/dist /app/front-end/dist
COPY --from=go-build /go-collector /app/bin/go-collector
COPY --from=ebpf-build /go-collector-ebpf /app/bin/go-collector-ebpf 2>/dev/null || true
COPY VERSION /app/VERSION

RUN chmod +x /app/bin/go-collector /app/bin/go-collector-ebpf /app/server/entrypoint.sh 2>/dev/null || true

EXPOSE 8088 18088

CMD ["/app/server/entrypoint.sh"]
