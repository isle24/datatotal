FROM node:20-slim AS frontend-build

WORKDIR /src/front-end
COPY front-end/package.json front-end/package-lock.json* ./
RUN npm ci
COPY front-end ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIR=/app/front-end/dist

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpcap0.8 pciutils \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt

COPY server /app/server
COPY --from=frontend-build /src/front-end/dist /app/front-end/dist
COPY VERSION /app/VERSION
RUN chmod +x /app/server/entrypoint.sh

EXPOSE 8088

CMD ["/app/server/entrypoint.sh"]
