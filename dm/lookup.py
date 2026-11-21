"""Open5e SRD lookup for D&D 5e content. Used during character creation."""
import re
from urllib.parse import quote

import requests

BASE = "https://api.open5e.com/v1"
TIMEOUT = 8  # seconds — short so creation doesn't hang on a Pi without internet


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _get(path: str) -> dict | None:
    try:
        r = requests.get(f"{BASE}{path}", timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def _find(endpoint: str, name: str) -> dict | None:
    """Try exact slug first, then keyword search."""
    data = _get(f"/{endpoint}/{_slug(name)}/")
    if data and "name" in data:
        return data
    results = _get(f"/{endpoint}/?search={quote(name)}&limit=5")
    if results and results.get("results"):
        return results["results"][0]
    return None


def lookup(entity_type: str, name: str) -> dict | None:
    """
    Fetch D&D 5e SRD content by type and name.

    entity_type: "race" | "class" | "subclass" | "background"
    name:        for subclass, pass "<class> <subclass>" e.g. "cleric trickery domain"
    """
    if entity_type == "race":
        return _find("races", name)
    if entity_type == "class":
        return _find("classes", name)
    if entity_type == "subclass":
        # Try "{class}-{subclass}" combined slug first (e.g. "cleric-trickery-domain")
        parts = name.split(None, 1)
        if len(parts) == 2:
            combined = f"{_slug(parts[0])}-{_slug(parts[1])}"
            data = _get(f"/subclasses/{combined}/")
            if data and "name" in data:
                return data
        # Fall back to searching by just the subclass part
        sub_name = parts[-1] if len(parts) > 1 else name
        return _find("subclasses", sub_name)
    if entity_type == "background":
        return _find("backgrounds", name)
    return None
