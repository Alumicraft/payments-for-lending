"""Map API endpoints for workspace heatmap and address autofill."""

import frappe
import requests
from frappe import _


@frappe.whitelist()
def search_address(query):
    """Search for addresses using Mapbox Search Box API.

    Called from HBR form's address autofill dropdown.
    Returns a list of structured address suggestions.
    """
    if not query or len(query) < 3:
        return []

    settings = frappe.get_single("Map Settings")
    token = settings.get_password("mapbox_access_token")
    if not token:
        return []

    url = "https://api.mapbox.com/search/searchbox/v1/suggest"
    params = {
        "q": query,
        "access_token": token,
        "language": "en",
        "country": "US",
        "types": "address",
        "limit": 5,
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    suggestions = data.get("suggestions", [])
    if not suggestions:
        return []

    # Retrieve full details for each suggestion
    results = []
    for s in suggestions:
        mapbox_id = s.get("mapbox_id")
        if not mapbox_id:
            continue

        try:
            detail_url = f"https://api.mapbox.com/search/searchbox/v1/retrieve/{mapbox_id}"
            detail_resp = requests.get(
                detail_url,
                params={"access_token": token},
                timeout=5
            )
            detail_resp.raise_for_status()
            detail_data = detail_resp.json()
        except Exception:
            continue

        features = detail_data.get("features", [])
        if features:
            results.append(_parse_mapbox_feature(features[0]))

    return results


@frappe.whitelist()
def get_heatmap_data():
    """Return all HBRs with coordinates, aggregated by location.

    Called by the workspace heatmap Custom HTML Block on load.
    """
    rows = frappe.get_all(
        "Home Build Request",
        filters={"docstatus": ["!=", 2]},
        fields=[
            "community_name", "delivery_address",
            "city", "state", "zip",
            "latitude", "longitude"
        ],
    )
    return _aggregate_locations(rows)


@frappe.whitelist()
def get_map_settings():
    """Return map configuration for the frontend.

    Returns the access token and default view settings.
    """
    settings = frappe.get_single("Map Settings")
    return {
        "access_token": settings.get_password("mapbox_access_token") or "",
        "default_latitude": settings.default_latitude or 34.0,
        "default_longitude": settings.default_longitude or -115.0,
        "default_zoom": settings.default_zoom or 6,
        "map_style_url": settings.map_style_url or "mapbox://styles/mapbox/streets-v12",
    }


def _parse_mapbox_feature(feature):
    """Extract structured address data from a Mapbox GeoJSON feature."""
    props = feature.get("properties", {})
    coords = feature.get("geometry", {}).get("coordinates", [0, 0])

    return {
        "full_address": props.get("full_address", ""),
        "address": props.get("address", ""),
        "city": props.get("place", ""),
        "state": props.get("region_code", "") or props.get("region", ""),
        "zip": props.get("postcode", ""),
        "latitude": coords[1] if len(coords) > 1 else 0,
        "longitude": coords[0] if len(coords) > 0 else 0,
    }


def _aggregate_locations(rows):
    """Group HBR rows by rounded coordinates and return aggregated data.

    Skips rows with zero/missing coordinates.
    """
    groups = {}
    for row in rows:
        lat = row.get("latitude") or 0
        lng = row.get("longitude") or 0
        if not lat and not lng:
            continue

        # Round to 4 decimals (~11m precision) for grouping
        key = (round(lat, 4), round(lng, 4))
        if key not in groups:
            groups[key] = {
                "community_name": row.get("community_name") or "",
                "address": (row.get("delivery_address") or "")
                    + ", " + (row.get("city") or "")
                    + ", " + (row.get("state") or "")
                    + " " + (row.get("zip") or ""),
                "latitude": lat,
                "longitude": lng,
                "hbr_count": 0,
            }
        groups[key]["hbr_count"] += 1

    return list(groups.values())
