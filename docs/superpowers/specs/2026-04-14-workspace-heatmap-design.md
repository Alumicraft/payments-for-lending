# Workspace Heatmap — Design Spec

## Overview

A Mapbox-powered heatmap and cluster map embedded in DCR workspace pages via a Custom HTML Block. Shows Home Build Request density across Park communities in the Southwest US.

## Embedding Method

**Custom HTML Block** added to the **Overview** and **Deals** workspace pages. Full-bleed CSS (negative margins + width override) to fill the workspace content area edge-to-edge. Map height fills the viewport minus the navbar.

The same block is created once and added to both workspaces.

## Map Layers

Both layers are always visible simultaneously:

- **Heatmap layer** — intensity based on HBR count per Park location. Provides the big-picture density view.
- **Cluster marker layer** — circle markers that group when overlapping, showing count numbers on clusters. Individual markers visible at full zoom.

## Click Interaction

Clicking a marker or cluster opens a popup showing:
- Park name
- Address
- HBR count

The popup includes a link to `/app/home-build-request?park={park_name}` to drill down into the filtered HBR list for that park.

## Data Model Changes

### Park DocType — New Fields

| Field         | Type  | Properties                        |
|---------------|-------|-----------------------------------|
| `latitude`    | Float | Read-only, in "Geolocation" section |
| `longitude`   | Float | Read-only, in "Geolocation" section |

### Map Settings — New Single DocType

| Field                  | Type     | Default                                  |
|------------------------|----------|------------------------------------------|
| `mapbox_access_token`  | Password | —                                        |
| `default_latitude`     | Float    | 34.0 (Southwest US)                      |
| `default_longitude`    | Float    | -115.0 (Southwest US)                    |
| `default_zoom`         | Int      | 6                                        |
| `map_style_url`        | Data     | `mapbox://styles/mapbox/streets-v12`     |

## API Endpoint

**`dcr.api.map.get_park_heatmap_data`** (whitelisted)

Returns all Parks with coordinates and HBR counts in a single lightweight JSON response. Called by the map JS on page load.

Response shape:
```json
[
  {
    "park_name": "Oak Forest MHP",
    "address": "123 Main St, Westlake Village, CA 93065",
    "latitude": 34.1416,
    "longitude": -118.8209,
    "hbr_count": 12
  }
]
```

## Geocoding Flow

### On Park Save (`before_save` hook)

1. Check if address fields changed (`address_line1`, `city`, `state`, `zip`) or if `latitude`/`longitude` are empty
2. Build a search string from the address fields
3. Call Mapbox Geocoding API server-side using token from Map Settings
4. Store returned lat/lng on the Park record
5. If geocoding fails (bad address, API error), save succeeds but lat/lng stay empty — the park won't appear on the map

### Backfill Script

A one-time whitelisted method (`dcr.api.map.backfill_park_coordinates`) to geocode all existing Parks that have addresses but no coordinates. Called manually from the browser console (`frappe.call(...)`) after the first deployment that includes this feature.

## Map Rendering

### Mapbox GL JS Loading

The Custom HTML Block's JavaScript section dynamically injects the Mapbox GL JS script and CSS, then initializes the map after the script loads.

### Configuration

Map reads center, zoom, style, and access token from Map Settings via API on load.

### Full-Bleed CSS

Negative margins and `width: calc(100% + Npx)` to break out of the workspace content container padding. Exact pixel values determined by inspecting the live DOM. Map height: `calc(100vh - ~120px)` to account for the navbar.

## Settings Access

- The geocoding hook on Park reads the Mapbox token from Map Settings
- The map JS reads all settings (token, center, zoom, style) from Map Settings on load
- Map style is designed in Mapbox Studio and referenced by URL in settings

## Scope

- No filtering — shows all Parks with coordinates
- No real-time updates — data fetched fresh on each page load
- Southwest US default view
- Only Parks with valid coordinates appear (Private Property HBRs are excluded since they lack structured addresses)
