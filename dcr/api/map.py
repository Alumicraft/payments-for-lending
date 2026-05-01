"""Map API endpoints for workspace heatmap and address autofill."""

import hashlib
import math
import re
from datetime import datetime, timedelta

import frappe
import requests
from frappe import _

FACTORY_SUPPLIER_GROUP = "Factory"


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
    """Return HBRs from the trailing 12 months, grouped by address+space.

    Cancelled HBRs (docstatus=2 OR a cancelled PO with no active PO/PR) are
    filtered server-side and never reach the map. Draft (docstatus=0) maps
    to status="Pending" — there is no separate Draft pin.
    """
    cutoff = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
    rows = frappe.db.sql(
        """
        SELECT
            hbr.name,
            hbr.community_name,
            hbr.delivery_address,
            hbr.city,
            hbr.state,
            hbr.zip,
            hbr.space_number,
            hbr.latitude,
            hbr.longitude,
            hbr.customer,
            cust.customer_name AS customer_name,
            hbr.factory,
            fact.supplier_name AS factory_name,
            hbr.creation,
            hbr.docstatus,
            EXISTS (
                SELECT 1 FROM `tabPurchase Receipt Item` pri
                JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
                JOIN `tabPurchase Order` po ON po.name = pri.purchase_order
                WHERE po.custom_home_build_request = hbr.name
                  AND pr.docstatus = 1
            ) AS has_pr,
            EXISTS (
                SELECT 1 FROM `tabPurchase Order` po
                WHERE po.custom_home_build_request = hbr.name
                  AND po.docstatus = 1
            ) AS has_active_po,
            EXISTS (
                SELECT 1 FROM `tabPurchase Order` po
                WHERE po.custom_home_build_request = hbr.name
                  AND po.docstatus = 2
            ) AS has_cancelled_po
        FROM `tabHome Build Request` hbr
        LEFT JOIN `tabCustomer` cust ON cust.name = hbr.customer
        LEFT JOIN `tabSupplier` fact ON fact.name = hbr.factory
        WHERE hbr.creation >= %s
          AND hbr.docstatus != 2
        """,
        (cutoff,),
        as_dict=True,
    )
    # Filter out rows whose only PO is cancelled (no active PO, no PR).
    rows = [
        r for r in rows
        if not (r.get("has_cancelled_po") and not r.get("has_active_po") and not r.get("has_pr"))
    ]
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
        "block_zoom": settings.get("block_zoom") or 4.5,
        "puck_full_zoom_threshold": settings.get("puck_full_zoom_threshold") or 12,
        "map_style_url": settings.map_style_url or "mapbox://styles/mapbox/streets-v12",
    }


@frappe.whitelist()
def get_factory_locations():
    """Return factory suppliers with non-zero coordinates.

    Used by the map block to render factory icons. Coordinates are populated
    by the Supplier on_update hook (`geocode_supplier`).
    """
    rows = frappe.get_all(
        "Supplier",
        filters={
            "supplier_group": FACTORY_SUPPLIER_GROUP,
            "disabled": 0,
        },
        fields=["name", "supplier_name", "latitude", "longitude"],
    )
    return [
        {
            "name": r["name"],
            "supplier_name": r.get("supplier_name") or r["name"],
            "latitude": r.get("latitude") or 0,
            "longitude": r.get("longitude") or 0,
        }
        for r in rows
        if (r.get("latitude") or 0) and (r.get("longitude") or 0)
    ]


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


# Stack color priority — higher (lower index) wins when a pin combines
# homes with different statuses.
STATUS_PRIORITY = ["Ordered", "Pending", "Delivered"]


def _aggregate_locations(rows):
    """Group HBR rows by (coords, address, space_number) and return features.

    Each row may carry derived-status flags from `get_heatmap_data`'s SQL.
    Rows lacking those flags (legacy callers / tests for static lat-lng
    grouping) get a "Pending" status by default.
    """
    groups = {}
    for row in rows:
        lat = row.get("latitude") or 0
        lng = row.get("longitude") or 0
        if not lat and not lng:
            continue

        space = row.get("space_number") or None
        addr = row.get("delivery_address") or ""
        key = (
            round(lat, 4),
            round(lng, 4),
            _normalize_address(addr),
            space,
        )
        if key not in groups:
            groups[key] = {
                "community_name": row.get("community_name") or "",
                "address": addr,                  # raw street; no city tail
                "city": row.get("city") or "",
                "state": row.get("state") or "",
                "zip": row.get("zip") or "",
                "space_number": space,
                "latitude": lat,
                "longitude": lng,
                "hbr_count": 0,
                "status": None,
                "homes": [],
            }
        status = _derive_status(row)
        groups[key]["hbr_count"] += 1
        groups[key]["homes"].append({
            "name": row.get("name"),
            "status": status,
            "customer": row.get("customer"),
            "customer_name": row.get("customer_name") or row.get("customer") or "",
            "factory": row.get("factory"),
            "factory_name": row.get("factory_name") or row.get("factory") or "",
            "creation_iso": row.get("creation").isoformat() if row.get("creation") else None,
        })
        cur = groups[key]["status"]
        if cur is None or STATUS_PRIORITY.index(status) < STATUS_PRIORITY.index(cur):
            groups[key]["status"] = status

    out = list(groups.values())
    _apply_jitter(out)
    return out


def _derive_status(row):
    """Derive deal status from PO/PR flags. Draft folds into Pending."""
    if row.get("has_pr"):
        return "Delivered"
    if row.get("has_active_po"):
        return "Ordered"
    return "Pending"  # covers docstatus=0 (Draft) and docstatus=1 with no PO


def _normalize_address(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.strip().lower())


def _apply_jitter(groups):
    """Spread groups that share rounded coords with deterministic offsets.

    Mapbox geocoding often resolves every space in a manufactured-home park
    to the same lat/lng (the park entrance). Without jitter, distinct
    spaces stack atop each other and the user can only ever click one.
    Offsets are seeded from the address+space so the same group lands in
    the same spot across reloads.
    """
    cells = {}
    for g in groups:
        cell = (round(g["latitude"], 4), round(g["longitude"], 4))
        cells.setdefault(cell, []).append(g)
    for members in cells.values():
        if len(members) <= 1:
            continue
        for g in members:
            seed = "|".join([
                g.get("address") or "",
                str(g.get("space_number") or ""),
            ])
            h = hashlib.sha1(seed.encode("utf-8")).digest()
            dx = (h[0] - 128) / 128.0  # roughly -1..1
            dy = (h[1] - 128) / 128.0
            # ~5m max offset so pins separate but stay clearly co-located
            d_lat = dy * (5.0 / 111000.0)
            cos_lat = max(0.1, math.cos(math.radians(g["latitude"])))
            d_lng = dx * (5.0 / (111000.0 * cos_lat))
            g["latitude"] = g["latitude"] + d_lat
            g["longitude"] = g["longitude"] + d_lng


# --- Supplier (factory) geocoding -------------------------------------------


def geocode_supplier(doc, method=None):
    """Doc hook: geocode a Supplier in the Factory group when its primary
    address resolves to coordinates that differ from the cache.

    Wired via hooks.py `doc_events["Supplier"]["on_update"]`.
    Idempotent — it only writes when the resolved lat/lng changes.
    """
    if doc.get("supplier_group") != FACTORY_SUPPLIER_GROUP:
        return
    address = _get_supplier_primary_address(doc.name)
    if not address:
        return
    coords = _geocode_address(address)
    if not coords:
        return
    new_lat, new_lng = coords
    cur_lat = doc.get("latitude") or 0
    cur_lng = doc.get("longitude") or 0
    if _coords_equal(cur_lat, new_lat) and _coords_equal(cur_lng, new_lng):
        return
    # Write directly to DB to avoid triggering on_update recursion.
    frappe.db.set_value("Supplier", doc.name, {
        "latitude": new_lat,
        "longitude": new_lng,
    }, update_modified=False)


def geocode_address_suppliers(doc, method=None):
    """Doc hook: when an Address is updated, refresh coords for any Factory
    Supplier linked to it.

    Wired via hooks.py `doc_events["Address"]["on_update"]`.
    """
    links = doc.get("links") or []
    for link in links:
        if link.get("link_doctype") != "Supplier":
            continue
        supplier_name = link.get("link_name")
        if not supplier_name:
            continue
        if frappe.db.get_value("Supplier", supplier_name, "supplier_group") != FACTORY_SUPPLIER_GROUP:
            continue
        # Re-fetch via the supplier so we use whatever Address ERPNext
        # currently considers primary (may not be this one).
        supplier_doc = frappe.get_doc("Supplier", supplier_name)
        geocode_supplier(supplier_doc)


def _get_supplier_primary_address(supplier_name):
    """Return the supplier's primary address as a single query string, or None."""
    rows = frappe.db.sql(
        """
        SELECT a.address_line1, a.address_line2, a.city, a.state, a.pincode, a.country,
               a.is_primary_address
        FROM `tabAddress` a
        JOIN `tabDynamic Link` dl ON dl.parent = a.name
            AND dl.parenttype = 'Address'
            AND dl.link_doctype = 'Supplier'
            AND dl.link_name = %s
        ORDER BY a.is_primary_address DESC, a.modified DESC
        LIMIT 1
        """,
        (supplier_name,),
        as_dict=True,
    )
    if not rows:
        return None
    a = rows[0]
    parts = [
        a.get("address_line1"),
        a.get("address_line2"),
        a.get("city"),
        a.get("state"),
        a.get("pincode"),
        a.get("country"),
    ]
    return ", ".join(p for p in parts if p)


def _geocode_address(query):
    """Geocode a free-text address via Mapbox Search Box `forward`.

    Returns (lat, lng) or None.
    """
    if not query:
        return None
    settings = frappe.get_single("Map Settings")
    token = settings.get_password("mapbox_access_token")
    if not token:
        return None
    try:
        resp = requests.get(
            "https://api.mapbox.com/search/geocode/v6/forward",
            params={
                "q": query,
                "access_token": token,
                "limit": 1,
                "country": "US",
            },
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    features = data.get("features", [])
    if not features:
        return None
    coords = (features[0].get("geometry") or {}).get("coordinates") or []
    if len(coords) < 2:
        return None
    lng, lat = coords[0], coords[1]
    return (lat, lng)


def _coords_equal(a, b, tol=1e-6):
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return False
