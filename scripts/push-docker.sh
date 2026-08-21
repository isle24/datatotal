#!/usr/bin/env bash
set -Eeuo pipefail

# Push already-built architecture images and publish multi-arch manifests.
# Usage: ./scripts/push-docker.sh
# Optional: DOCKER_IMAGE=isle204/nas-traffic-lens DOCKER_CONTEXT=orbstack DRY_RUN=1 ./scripts/push-docker.sh
# The default host proxy is http://127.0.0.1:10808. Override it with
# DOCKER_PUSH_PROXY, or set DOCKER_PUSH_PROXY_ENABLED=false to disable it.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${DOCKER_IMAGE:-isle204/nas-traffic-lens}"
CONTEXT="${DOCKER_CONTEXT:-orbstack}"
DRY_RUN="${DRY_RUN:-0}"
PROXY_ENABLED="${DOCKER_PUSH_PROXY_ENABLED:-true}"
PUSH_PROXY="${DOCKER_PUSH_PROXY:-http://127.0.0.1:10808}"
VERSION="$(tr -d '[:space:]' < "${ROOT_DIR}/VERSION")"

if [[ -z "${VERSION}" ]]; then
  echo "VERSION is empty" >&2
  exit 1
fi

docker_cmd=(docker --context "${CONTEXT}")
proxy_env=(
  "HTTP_PROXY=${PUSH_PROXY}"
  "HTTPS_PROXY=${PUSH_PROXY}"
  "ALL_PROXY=${PUSH_PROXY}"
  "http_proxy=${PUSH_PROXY}"
  "https_proxy=${PUSH_PROXY}"
  "all_proxy=${PUSH_PROXY}"
)
docker_exec() {
  if [[ "${PROXY_ENABLED}" == "true" ]]; then
    env "${proxy_env[@]}" "$@"
  else
    "$@"
  fi
}
run() {
  printf '+ '
  printf '%q ' "$@"
  printf '\n'
  if [[ "${DRY_RUN}" != "1" ]]; then
    docker_exec "$@"
  fi
}

if ! docker_exec "${docker_cmd[@]}" version >/dev/null 2>&1; then
  echo "Docker context '${CONTEXT}' is not available or the daemon is not running." >&2
  echo "Start OrbStack, or run with DOCKER_CONTEXT=<your-context>." >&2
  exit 1
fi

echo "Image: ${IMAGE}"
echo "Version: ${VERSION}"
echo "Docker context: ${CONTEXT}"
if [[ "${PROXY_ENABLED}" == "true" ]]; then
  echo "Host proxy: ${PUSH_PROXY}"
  echo "Note: this exports the proxy to Docker CLI/buildx. The Docker daemon may also need an OrbStack proxy setting using the host gateway."
else
  echo "Host proxy: disabled"
fi

for arch in amd64 arm64; do
  local_tag="${IMAGE}:${VERSION}-${arch}"
  if [[ "${DRY_RUN}" != "1" ]] && ! docker_exec "${docker_cmd[@]}" image inspect "${local_tag}" >/dev/null 2>&1; then
    echo "Missing local image: ${local_tag}" >&2
    echo "Build it first, for example:" >&2
    echo "  docker --context ${CONTEXT} buildx build --platform linux/${arch} --load -t ${local_tag} -t ${IMAGE}:latest-${arch} -t ${IMAGE}:${arch} ." >&2
    exit 1
  fi
done

for arch in amd64 arm64; do
  run "${docker_cmd[@]}" push "${IMAGE}:${VERSION}-${arch}"
  run "${docker_cmd[@]}" push "${IMAGE}:latest-${arch}"
  run "${docker_cmd[@]}" push "${IMAGE}:${arch}"
done

run "${docker_cmd[@]}" buildx imagetools create \
  --tag "${IMAGE}:${VERSION}" \
  "${IMAGE}:${VERSION}-amd64" "${IMAGE}:${VERSION}-arm64"
run "${docker_cmd[@]}" buildx imagetools create \
  --tag "${IMAGE}:latest" \
  "${IMAGE}:${VERSION}-amd64" "${IMAGE}:${VERSION}-arm64"

if [[ "${DRY_RUN}" != "1" ]]; then
  echo
  echo "Published manifests:"
  docker_exec "${docker_cmd[@]}" buildx imagetools inspect "${IMAGE}:${VERSION}"
  echo
  docker_exec "${docker_cmd[@]}" buildx imagetools inspect "${IMAGE}:latest"
else
  echo
  echo "Dry run complete. Set DRY_RUN=0 to push."
fi
