# Workspace Heatmap & HBR Address Overhaul — Design Spec

## Overview

Two tightly coupled changes:

1. **Remove the Park DocType** — move all park-related fields directly onto Home Build Request. Replace the Park link field with a Mapbox Address Autofill-powered address entry. No data migration needed (company data will be wiped).

2. **Mapbox heatmap and cluster map** — embedded in workspace pages via a Custom HTML Block. Shows HBR density across communities in the Southwest US.

## HBR Data Model Changes

### Fields Removed

- `park` (Link to Park) — replaced by direct address fields
- `property_type` (Select: Park / Private Property) — no longer needed
- All `park_*` fetch_from fields (`park_address_line1`, `park_address_line2`, `park_city`, `park_state`, `park_zip`, `park_contact_name`, `park_phone`, `park_gated`, `park_access_code`, `park_space_rent`)

### Fields Added / Replaced

**Delivery Location section:**

| Field              | Type     | Notes                                              |
|--------------------|----------|----------------------------------------------------|
| `community_name`   | Data     | Freeform text — name of the park/community         |
| `delivery_address` | Data     | Populated by Mapbox Address Autofill               |
| `city`             | Data     | Populated by Mapbox Address Autofill               |
| `state`            | Data     | Populated by Mapbox Address Autofill               |
| `zip`              | Data     | Populated by Mapbox Address Autofill               |
| `space_number`     | Data     | Lot/space number within the community (manual entry)|
| `latitude`         | Float    | Read-only, populated by Mapbox Autofill selection  |
| `longitude`        | Float    | Read-only, populated by Mapbox Autofill selection  |

**Community Details section:**

| Field              | Type     | Notes                                              |
|--------------------|----------|----------------------------------------------------|
| `contact_name`     | Data     | Park/community contact person                      |
| `contact_phone`    | Data     | Park/community phone number                        |
| `gated`            | Check    | Whether the community is gated                     |
| `access_code`      | Data     | Gate access code (visible only when gated = 1)     |
| `space_rent`       | Currency | Monthly space rental rate                          |

### Park DocType

Deleted entirely. No migration — company data will be wiped before deployment.

## Mapbox Address Autofill on HBR Form

### How It Works

The `delivery_address` field on the HBR form is wired to the Mapbox Search Box API via custom JavaScript in `home_build_request.js`:

1. Dealer starts typing an address in the `delivery_address` field
2. An autocomplete dropdown appears with Mapbox suggestions
3. Dealer picks a result
4. The selection auto-fills `delivery_address`, `city`, `state`, `zip`, `latitude`, and `longitude`
5. Dealer manually enters `community_name` and `space_number`

### Implementation

- Custom control logic in `dcr/public/js/home_build_request.js` (existing doctype_js file)
- Hooks into the `delivery_address` field's input event
- Calls Mapbox Search Box API using token from Map Settings
- Renders results in an awesomplete-style dropdown (consistent with Frappe's existing Link field UX)
- On selection, populates address fields and coordinates in one shot

### No Server-Side Geocoding

Coordinates come directly from the Mapbox Autofill selection. No `before_save` geocoding hook needed. If a dealer manually edits the address after selection, the lat/lng from the original selection are preserved (good enough for map placement).

## Map Settings — New Single DocType

| Field                  | Type     | Default                                  |
|------------------------|----------|------------------------------------------|
| `mapbox_access_token`  | Password | —                                        |
| `default_latitude`     | Float    | 34.0 (Southwest US)                      |
| `default_longitude`    | Float    | -115.0 (Southwest US)                    |
| `default_zoom`         | Int      | 6                                        |
| `map_style_url`        | Data     | `mapbox://styles/mapbox/streets-v12`     |

Token is used by both the HBR form autofill and the workspace map.

## Workspace Heatmap

### Embedding Method

**Custom HTML Block** added to the **Overview** and **Deals** workspace pages. Full-bleed CSS (negative margins + width override) to fill the workspace content area edge-to-edge. Map height fills the viewport minus the navbar.

The same block is created once and added to both workspaces.

### Map Layers

Both layers are always visible simultaneously:

- **Heatmap layer** — intensity based on HBR concentration at each location. Provides the big-picture density view.
- **Cluster marker layer** — circle markers that group when overlapping, showing count numbers on clusters. Individual markers visible at full zoom.

### Click Interaction

Clicking a marker opens a popup showing:
- Community name
- Address
- HBR count at that location

The popup includes a link to `/app/home-build-request?community_name={name}` to drill down into the filtered HBR list for that community.

### API Endpoint

**`dcr.api.map.get_heatmap_data`** (whitelisted)

Returns all HBRs with coordinates, grouped by location, in a single lightweight JSON response. Called by the map JS on page load.

Response shape:
```json
[
  {
    "community_name": "Oak Forest MHP",
    "address": "123 Main St, Westlake Village, CA 93065",
    "latitude": 34.1416,
    "longitude": -118.8209,
    "hbr_count": 12
  }
]
```

The endpoint aggregates HBRs by lat/lng (or by address string) and returns one entry per unique location with the count.

### Mapbox GL JS Loading

The Custom HTML Block's JavaScript section dynamically injects the Mapbox GL JS script and CSS, then initializes the map after the script loads.

### Configuration

Map reads center, zoom, style, and access token from Map Settings via API on load.

### Full-Bleed CSS

Negative margins and `width: calc(100% + Npx)` to break out of the workspace content container padding. Exact pixel values determined by inspecting the live DOM. Map height: `calc(100vh - ~120px)` to account for the navbar.

## Scope

- No filtering — shows all HBRs with coordinates
- No real-time updates — data fetched fresh on each page load
- Southwest US default view
- Only HBRs with valid lat/lng appear on the map
- No data migration — clean slate after company data wipe
