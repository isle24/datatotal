"""Bundled, dependency-free Docker service icons and name matching."""

import re
from urllib.parse import quote


def _icon_data(label: str, color: str, accent: str = "#ffffff") -> str:
    """Create a small local SVG monogram without a runtime image dependency."""
    letters = "".join(part[0] for part in label.split() if part)[:2].upper() or "?"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
        f'<rect width="96" height="96" rx="18" fill="{color}"/>'
        f'<circle cx="74" cy="22" r="8" fill="{accent}" opacity=".85"/>'
        f'<text x="48" y="58" fill="{accent}" font-family="Arial,sans-serif" '
        f'font-size="28" font-weight="700" text-anchor="middle">{letters}</text>'
        "</svg>"
    )
    return "data:image/svg+xml," + quote(svg, safe="")


_ICON_DEFINITIONS = (
    ("qbittorrent", "qBittorrent", ("qbittorrent", "qb"), "#2f80ed", "#ffffff"),
    ("redis", "Redis", ("redis",), "#d82c20", "#ffffff"),
    ("mysql", "MySQL", ("mysql",), "#00758f", "#ffffff"),
    ("mariadb", "MariaDB", ("mariadb",), "#003545", "#ffffff"),
    ("postgresql", "PostgreSQL", ("postgresql", "postgres", "pgsql"), "#336791", "#ffffff"),
    ("moviepilot", "MoviePilot", ("moviepilot", "moviepolite"), "#5b4bdb", "#ffffff"),
    ("nginx", "Nginx", ("nginx",), "#009639", "#ffffff"),
    ("mongodb", "MongoDB", ("mongodb", "mongo"), "#47a248", "#ffffff"),
    ("prometheus", "Prometheus", ("prometheus",), "#e6522c", "#ffffff"),
    ("grafana", "Grafana", ("grafana",), "#f46800", "#ffffff"),
    ("linuxserver", "LinuxServer", ("linuxserver", "linux-server"), "#009639", "#ffffff"),
    ("docker", "Docker", ("docker",), "#2496ed", "#ffffff"),
)


DOCKER_ICON_REGISTRY = {
    key: {
        "key": key,
        "label": label,
        "aliases": tuple(aliases),
        "dataUrl": _icon_data(label, color, accent),
        "source": "builtin",
    }
    for key, label, aliases, color, accent in _ICON_DEFINITIONS
}


def normalize_icon_match_text(value: str) -> str:
    """Normalize image/name strings while retaining word boundaries for matching."""
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _alias_matches(candidate: str, alias: str) -> bool:
    normalized_candidate = f" {normalize_icon_match_text(candidate)} "
    normalized_alias = f" {normalize_icon_match_text(alias)} "
    return bool(normalized_alias.strip()) and normalized_alias in normalized_candidate


def match_docker_icon(name: str = "", image: str = "", compose_service: str = "") -> dict:
    """Return the strongest built-in match for one Docker container summary."""
    candidates = (
        (str(name or ""), 300),
        (str(compose_service or ""), 200),
        (str(image or ""), 100),
    )
    best = None
    for key, item in DOCKER_ICON_REGISTRY.items():
        for candidate, source_weight in candidates:
            normalized_candidate = normalize_icon_match_text(candidate)
            if not normalized_candidate:
                continue
            for alias in item["aliases"]:
                normalized_alias = normalize_icon_match_text(alias)
                if not _alias_matches(normalized_candidate, normalized_alias):
                    continue
                score = source_weight + len(normalized_alias)
                if best is None or score > best[0]:
                    best = (score, key, item)
    if best is None:
        return {}
    item = best[2]
    return {"key": item["key"], "label": item["label"], "dataUrl": item["dataUrl"], "source": item["source"]}


def get_docker_icon(key: str) -> dict:
    item = DOCKER_ICON_REGISTRY.get(str(key or "").strip().lower())
    if not item:
        return {}
    return {"key": item["key"], "label": item["label"], "dataUrl": item["dataUrl"], "source": item["source"]}


def list_docker_icons() -> list[dict]:
    """Return bounded copies suitable for the authenticated icon-picker endpoint."""
    return [
        {
            "key": item["key"],
            "label": item["label"],
            "dataUrl": item["dataUrl"],
            "source": item["source"],
        }
        for item in DOCKER_ICON_REGISTRY.values()
    ]
