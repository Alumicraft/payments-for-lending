# Map Icons, Filters, Legend & Snail Trails — Design Spec

## Overview

Builds on the workspace heatmap (2026-04-14) with five additions:

1. **Block vs full-bleed zoom** — separate zoom for the map widget vs the dedicated Map workspace.
2. **Status-colored home icons** in two styles (puck, full pin) — swap based on a configurable zoom threshold.
3. **Factory icons** sourced from Supplier primary addresses.
4. **Snail trails** between a home and its factory on click.
5. **Legend that doubles as a filter** — toggle visibility per status. Full-bleed only.

Map dataset is restricted to a **trailing 12-month window** based on `HBR.creation`.

## Map Settings — New Fields

Two new fields on the singleton `Map Settings` doctype:

| Field                      | Type  | Default | Notes                                                       |
|----------------------------|-------|---------|-------------------------------------------------------------|
| `block_zoom`               | Float | `4.5`   | Zoom level when the block is rendered outside the Map page  |
| `puck_full_zoom_threshold` | Float | `12`    | Below this zoom, render pucks; at/above, render full icons  |

Block-mode reuses `default_latitude` / `default_longitude` for centering — no separate block center.

## Status Taxonomy (Derived)

Deal status is **derived at query time** from existing docs, not stored on the HBR. Single source of truth — no new field, no sync hooks.

| Status      | Rule                                                          | Color (TBD by icon design) |
|-------------|---------------------------------------------------------------|---------------------------|
| Draft       | `HBR.docstatus = 0`                                           | (designer)                |
| Cancelled   | `HBR.docstatus = 2` OR linked PO is cancelled                 | (designer)                |
| Pending     | `HBR.docstatus = 1` and no PO exists                          | (designer)                |
| Ordered     | A linked Purchase Order exists and not yet fully received     | (designer)                |
| Delivered   | A linked Purchase Receipt exists                              | (designer)                |

Linkage:
- HBR ↔ Purchase Order via `PO.custom_home_build_request`
- HBR ↔ Purchase Receipt via the PO it references (PR's items reference the PO)

Default filter state: **Cancelled hidden by default**, all others visible. Persisted in `localStorage` per user.

## Trailing 12-Month Window

`get_heatmap_data` returns only HBRs where `creation >= NOW() - 365 days`. Heatmap, pins, legend counts, and trails all reflect this window.

## Home Icons

Two visual styles per status × two themes (light/dark) = **20 home assets**.

```
home-puck-{status}-{theme}.png
home-full-{status}-{theme}.png
```

Where `status ∈ {draft, pending, ordered, delivered, cancelled}` and `theme ∈ {light, dark}`.

**Switching rules**:
- Default: zoom < `puck_full_zoom_threshold` → puck. Zoom ≥ threshold → full icon. Implemented via Mapbox `step` expression on `icon-image`.
- Hover/click promotion: a puck under cursor or in selected state swaps to its full-icon counterpart, regardless of zoom. Implemented via a separate "focused" symbol layer with a feature-state filter.

Anchors: puck = center, full = bottom.

## Factory Icons

| Property | Value                                                    |
|----------|----------------------------------------------------------|
| Visible  | Always, all zoom levels, single brand color              |
| Asset    | `factory-{theme}.png` (2 total)                          |
| Source   | All `Supplier` records in the `Factory` Supplier Group   |
| Coords   | Two new hidden custom fields on Supplier — `latitude`, `longitude` |

Supplier coords are populated by an `on_update` hook that geocodes the supplier's primary address (the `Address` doctype linked via `Dynamic Link` to that supplier). Geocoding only fires when the resolved primary address differs from the cached one.

Factories are returned by a new endpoint `dcr.api.map.get_factory_locations()` and rendered in their own Mapbox source/layer so they are not affected by the home status filter.

## Snail Trail

| Trigger              | Behavior                                                                    |
|----------------------|-----------------------------------------------------------------------------|
| Click home pin       | Animated dashed line from home → its `factory`                              |
| Click home row in stacked-popup | Same, but using only the row's `factory`                         |
| Click factory pin    | Fan of lines from factory → every home referencing it (within active filter)|
| Click empty map / Esc / different pin | Dismiss                                                    |

**Linkage**: new `factory` Link → Supplier field on Home Build Request. Drives the trail directly. (We are *not* using Customer → Factory Assignment for this — too indirect, and a customer can have multiple assignments.)

**Visual**:
- `line` layer rendered on a great-circle interpolation (~20 segments) between the two points so it bows naturally.
- `line-dasharray` animated each tick (`requestAnimationFrame`) to produce marching-ants snail effect.
- Line color = the home's status color.
- Capped: factory-fan limited to 100 lines (worst case ≈ 1000 homes / # factories per year). If exceeded, render the top 100 by `creation desc` and surface a "+N more" hint.

## Address-Level Stacking

Multiple HBRs can share an address. Group key:

```
(round(lat, 4), round(lng, 4), normalized(delivery_address), space_number_or_null)
```

So two lots in the same park (different `space_number`) are **separate pins**. Same address with no space → stacked.

When a stack contains > 1 home:
- Pin color follows priority: `Ordered > Pending > Delivered > Draft > Cancelled`
- Count badge in the top-right corner shows visible-after-filter count
- Click → popup is a list view: header `"{N} deals at {address}"`, body is one row per home (status pill, customer, factory, "Open" link)
- Pin disappears entirely if every home in the stack is filtered out
- No automatic snail trail on a multi-home pin (ambiguous); trail fires when the user clicks an individual row in the popup

**Mapbox geocoding caveat**: Spaces in a park frequently geocode to the same lat/lng (the park entrance). Pins at identical coords get a small **deterministic** jitter — hash `space_number` to a stable offset of a few meters — so distinct spaces don't z-fight or overwrite each other.

## Legend & Filter

**Full-bleed only.** Block view shows a static read-only legend pill (color swatches + counts), no checkboxes.

**Layout** (full-bleed):
- Floating card, bottom-left, ~200px wide
- Header: "Deal status" + collapse chevron
- Rows: color swatch • label • count • checkbox per status
- Footer: "Show all / Hide all"

**Behavior**:
- Multi-select; defaults: all visible **except Cancelled**
- Filter applies to home pins (puck + full), the heatmap weighting, popup contents, and trail counts. Factories are unaffected.
- State persisted to `localStorage` keyed `dcr-map-status-filter`
- Counts update live as the filter changes

**Implementation**:
- Single config object in JS defines status order, label, color, asset basename
- Layer filters use `['in', ['get', 'status'], ['literal', activeStatuses]]` — no re-fetch needed

## API Changes

### `dcr.api.map.get_map_settings`

Adds:
- `block_zoom`
- `puck_full_zoom_threshold`

### `dcr.api.map.get_heatmap_data`

- Filters HBR by `creation >= now - 365 days`
- Joins to Purchase Order and Purchase Receipt to derive `status`
- Returns one feature per `(coords, address, space_number)` group
- Each feature carries: `community_name`, `address`, `space_number`, `latitude`, `longitude`, `hbr_count`, `status` (priority pick when stacked), `homes` (per-deal list with `name`, `status`, `customer`, `factory` for popup)

### `dcr.api.map.get_factory_locations` *(new)*

Returns all Suppliers in the `Factory` group with non-zero `(latitude, longitude)`. Shape:

```json
[
  {"name": "SUPP-0001", "supplier_name": "Acme Manufactured Homes",
   "latitude": 33.45, "longitude": -112.07}
]
```

## DocType Changes

### Home Build Request *(this app's own doctype — edit JSON directly)*

Add field:

| Field     | Type | Options   | Notes                              |
|-----------|------|-----------|------------------------------------|
| `factory` | Link | Supplier  | Drives the snail trail target      |

Placed near the existing `customer` field. Filter the link query to Suppliers in the `Factory` group.

### Supplier *(ERPNext doctype — custom fields via setup.py)*

Add hidden fields:

| Fieldname   | Type  | Hidden | Read-only |
|-------------|-------|--------|-----------|
| `latitude`  | Float | yes    | yes       |
| `longitude` | Float | yes    | yes       |

Geocoded by an `on_update` hook against the supplier's primary address.

## Out of Scope (Phase 2)

- Block-mode filtering (legend stays read-only on the block)
- Trail caching / pre-warming
- Alternate pin assets per `home_type` (Spec vs Customer Sold)
- Time-window slider (always trailing 12 months for now)

## Implementation Order

1. Map Settings fields (this PR)
2. Supplier custom fields + geocoding hook (this PR)
3. HBR `factory` field (this PR)
4. `get_heatmap_data` rewrite + status derivation (this PR)
5. `get_factory_locations` endpoint (this PR)
6. Block JS: `block_zoom` wiring + factory layer + status-aware icon expressions w/ placeholder colors (this PR)
7. Real status icons (next PR — depends on design assets)
8. Legend + filter UI (next PR)
9. Snail trail rendering (next PR)
10. Stacked-popup list view (next PR)
