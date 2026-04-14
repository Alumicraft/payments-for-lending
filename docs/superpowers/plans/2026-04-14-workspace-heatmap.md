# Workspace Heatmap & Park Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Embed a Mapbox heatmap + cluster map in workspace pages showing HBR density, replace the Park DocType with direct address fields on HBR powered by Mapbox Address Autofill, and create a Map Settings DocType for configuration.

**Architecture:** Server-side: Map Settings Single DocType stores Mapbox config; HBR DocType gets address/geo fields populated by client-side Mapbox Autofill; a lightweight API endpoint returns aggregated HBR location data. Client-side: Mapbox GL JS renders a heatmap + cluster layer in a Custom HTML Block on workspace pages; Mapbox Search Box JS powers the address autofill on the HBR form.

**Tech Stack:** Frappe v16, Mapbox GL JS, Mapbox Search Box API, Python (server-side API), JavaScript (client-side map + autofill)

**Note on property_type:** The spec says to remove `property_type`, but the DOC_REQUIREMENTS dictionary in `home_build_request.py` uses it as a key dimension — Park deliveries require "Park Agreement" and "Park Approval" while Private Property deliveries require "50% Deposit Proof". Removing it would break document checklist logic. This plan **keeps `property_type`** on HBR as a Select field (it classifies the delivery type, not a reference to the Park DocType). The Park **DocType** and Park **Link field** are removed.

**Note on testing:** This app runs on Frappe Cloud with no local bench. Tests use Python's `unittest` directly (no DB dependency). DocType JSON changes and JS are verified by deploying to Frappe Cloud.

---

## File Structure

### Files to Create

| File | Responsibility |
|------|----------------|
| `dcr/dcr/doctype/map_settings/map_settings.json` | Map Settings Single DocType definition |
| `dcr/dcr/doctype/map_settings/map_settings.py` | Map Settings controller (minimal) |
| `dcr/dcr/doctype/map_settings/__init__.py` | Module init |
| `dcr/api/map.py` | Heatmap data API endpoint |
| `dcr/patches/remove_park_doctype.py` | Cleanup patch for Park removal |
| `dcr/tests/test_map_api.py` | Tests for heatmap API |

### Files to Modify

| File | Changes |
|------|---------|
| `dcr/dcr/doctype/home_build_request/home_build_request.json` | Remove park link/fetch fields, add address + geo fields |
| `dcr/dcr/doctype/home_build_request/home_build_request.py` | Remove property_type validation referencing Park, keep DOC_REQUIREMENTS |
| `dcr/public/js/home_build_request.js` | Add Mapbox Address Autofill on delivery_address field |
| `dcr/dcr/doctype/document_checklist/document_checklist.json` | Keep "Park Approval" and "Park Agreement" options (they're document names, not Park DocType references) |
| `dcr/dcr/print_format/new_home_info_sheet/new_home_info_sheet.json` | Read community info from HBR fields instead of Park record |
| `dcr/hooks.py` | Add Map Settings to doc_events if needed |
| `dcr/setup.py` | Create Map Settings on install, create Custom HTML Block |
| `dcr/patches.txt` | Register remove_park_doctype patch |
| `dcr/tests/test_required_docs.py` | No changes needed (property_type stays, DOC_REQUIREMENTS stay) |

### Files to Delete

| File | Reason |
|------|--------|
| `dcr/dcr/doctype/park/park.json` | Park DocType removed |
| `dcr/dcr/doctype/park/park.py` | Park DocType removed |
| `dcr/dcr/doctype/park/__init__.py` | Park DocType removed |

---

## Task 1: Create Map Settings DocType

**Files:**
- Create: `dcr/dcr/doctype/map_settings/map_settings.json`
- Create: `dcr/dcr/doctype/map_settings/map_settings.py`
- Create: `dcr/dcr/doctype/map_settings/__init__.py`

- [ ] **Step 1: Create the directory**

```bash
mkdir -p dcr/dcr/doctype/map_settings
```

- [ ] **Step 2: Create `__init__.py`**

```bash
touch dcr/dcr/doctype/map_settings/__init__.py
```

- [ ] **Step 3: Create `map_settings.json`**

```json
{
 "actions": [],
 "creation": "2026-04-14 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "issingle": 1,
 "field_order": [
  "mapbox_access_token",
  "map_style_url",
  "column_break_defaults",
  "default_latitude",
  "default_longitude",
  "default_zoom"
 ],
 "fields": [
  {
   "fieldname": "mapbox_access_token",
   "fieldtype": "Password",
   "label": "Mapbox Access Token",
   "reqd": 1
  },
  {
   "default": "mapbox://styles/mapbox/streets-v12",
   "fieldname": "map_style_url",
   "fieldtype": "Data",
   "label": "Map Style URL"
  },
  {
   "fieldname": "column_break_defaults",
   "fieldtype": "Column Break"
  },
  {
   "default": "34.0",
   "fieldname": "default_latitude",
   "fieldtype": "Float",
   "label": "Default Latitude",
   "precision": "6"
  },
  {
   "default": "-115.0",
   "fieldname": "default_longitude",
   "fieldtype": "Float",
   "label": "Default Longitude",
   "precision": "6"
  },
  {
   "default": "6",
   "fieldname": "default_zoom",
   "fieldtype": "Int",
   "label": "Default Zoom"
  }
 ],
 "links": [],
 "modified": "2026-04-14 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "DCR",
 "name": "Map Settings",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "read": 1,
   "role": "System Manager",
   "write": 1
  }
 ],
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": []
}
```

- [ ] **Step 4: Create `map_settings.py`**

```python
from frappe.model.document import Document


class MapSettings(Document):
    pass
```

- [ ] **Step 5: Commit**

```bash
git add dcr/dcr/doctype/map_settings/
git commit -m "feat: add Map Settings Single DocType for Mapbox config"
```

---

## Task 2: Restructure HBR DocType JSON — Remove Park Fields, Add Address/Geo Fields

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`

This task replaces the Park link + fetch_from fields with direct address fields and geolocation coordinates.

- [ ] **Step 1: Remove old park fields from `field_order` and `fields`**

Remove these entries from `field_order`:
- `park_section`, `park`, `park_space_rent`
- `park_details_section`, `park_address_line1`, `park_address_line2`, `column_break_park_details`, `park_city`, `park_state`, `park_zip`
- `park_contact_section`, `park_contact_name`, `column_break_park_contact`, `park_phone`, `park_gated`, `park_access_code`

Remove all corresponding field objects from `fields` array.

Keep `space_number` and `property_type` — they stay on HBR.

- [ ] **Step 2: Add new delivery location and community detail fields**

Add to `field_order` (after `property_type`):

```
"delivery_section",
"community_name",
"delivery_address",
"column_break_delivery",
"city",
"state",
"zip",
"space_number",
"community_details_section",
"contact_name",
"contact_phone",
"column_break_community",
"gated",
"access_code",
"space_rent",
"geo_section",
"latitude",
"longitude"
```

Add these field objects to `fields`:

```json
{
 "fieldname": "delivery_section",
 "fieldtype": "Section Break",
 "label": "Delivery Location"
},
{
 "fieldname": "community_name",
 "fieldtype": "Data",
 "label": "Community Name"
},
{
 "fieldname": "delivery_address",
 "fieldtype": "Data",
 "label": "Delivery Address"
},
{
 "fieldname": "column_break_delivery",
 "fieldtype": "Column Break"
},
{
 "fieldname": "city",
 "fieldtype": "Data",
 "label": "City"
},
{
 "fieldname": "state",
 "fieldtype": "Data",
 "label": "State"
},
{
 "fieldname": "zip",
 "fieldtype": "Data",
 "label": "ZIP"
},
{
 "fieldname": "community_details_section",
 "fieldtype": "Section Break",
 "label": "Community Details",
 "collapsible": 1
},
{
 "fieldname": "contact_name",
 "fieldtype": "Data",
 "label": "Contact Name"
},
{
 "fieldname": "contact_phone",
 "fieldtype": "Data",
 "label": "Contact Phone",
 "options": "Phone"
},
{
 "fieldname": "column_break_community",
 "fieldtype": "Column Break"
},
{
 "fieldname": "gated",
 "fieldtype": "Check",
 "label": "Gated"
},
{
 "fieldname": "access_code",
 "fieldtype": "Data",
 "label": "Access Code",
 "depends_on": "eval:doc.gated"
},
{
 "fieldname": "space_rent",
 "fieldtype": "Currency",
 "label": "Monthly Space Rent"
},
{
 "fieldname": "geo_section",
 "fieldtype": "Section Break",
 "label": "Geolocation",
 "collapsible": 1
},
{
 "fieldname": "latitude",
 "fieldtype": "Float",
 "label": "Latitude",
 "precision": "6",
 "read_only": 1
},
{
 "fieldname": "longitude",
 "fieldtype": "Float",
 "label": "Longitude",
 "precision": "6",
 "read_only": 1
}
```

- [ ] **Step 3: Remove Park link from `links` array in the JSON**

The Park DocType JSON has a `links` section pointing to HBR. That file is being deleted. But also check if HBR's own `links` array references Park — it does not (it links to Purchase Invoice, Loan Application, Loan, Loan Disbursement, Signature Request). No change needed here.

- [ ] **Step 4: Move `space_number` into the delivery section**

`space_number` was under `park_section`. It's now in the new `delivery_section` field_order (already included in Step 2 above). Remove it from its old position in `field_order`.

- [ ] **Step 5: Update `park_section` depends_on removal**

The old `park_section` had `"depends_on": "eval:doc.property_type=='Park'"`. The new `delivery_section` has no depends_on — it's always visible. The `community_details_section` is collapsible but always present.

- [ ] **Step 6: Commit**

```bash
git add dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "feat: replace Park link fields with direct address and geo fields on HBR"
```

---

## Task 3: Update HBR Python — Remove Park-Specific Validation

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.py`

- [ ] **Step 1: Remove the property_type validation that referenced Park**

In `home_build_request.py`, remove line 45-46:

```python
        if self.financing_type == "Floored" and not self.property_type:
            frappe.throw(_("Property Type is required"))
```

Replace with nothing — `property_type` is still `reqd: 1` in the JSON, so Frappe handles this validation automatically.

- [ ] **Step 2: Verify DOC_REQUIREMENTS stays unchanged**

The DOC_REQUIREMENTS dictionary and `get_required_docs()` function remain exactly as-is. They use string keys like `"Park"` and `"Private Property"` which are Select field values, not references to the Park DocType.

- [ ] **Step 3: Run tests to verify nothing broke**

```bash
cd /Users/tristanfleming/Documents/Code/DCR
python -m pytest dcr/tests/test_required_docs.py -v
```

Expected: All 10 tests pass. No changes needed to tests since DOC_REQUIREMENTS is unchanged.

- [ ] **Step 4: Commit**

```bash
git add dcr/dcr/doctype/home_build_request/home_build_request.py
git commit -m "fix: remove redundant property_type validation (field is already reqd)"
```

---

## Task 4: Delete Park DocType + Cleanup Patch

**Files:**
- Delete: `dcr/dcr/doctype/park/park.json`, `dcr/dcr/doctype/park/park.py`, `dcr/dcr/doctype/park/__init__.py`
- Create: `dcr/patches/remove_park_doctype.py`
- Modify: `dcr/patches.txt`
- Modify: `dcr/setup.py`

- [ ] **Step 1: Delete the Park DocType directory**

```bash
rm -rf dcr/dcr/doctype/park/
```

- [ ] **Step 2: Create the cleanup patch**

Create `dcr/patches/remove_park_doctype.py`:

```python
"""Remove the Park DocType from the database.

The Park DocType has been replaced by direct address fields on
Home Build Request. Company data is wiped before this deploy,
so no data migration is needed.
"""
import frappe


def execute():
    if frappe.db.exists("DocType", "Park"):
        frappe.delete_doc("DocType", "Park", force=True)
        frappe.db.commit()
```

- [ ] **Step 3: Register the patch in `patches.txt`**

Append to `dcr/patches.txt`:

```
dcr.patches.remove_park_doctype
```

- [ ] **Step 4: Remove Park from `setup.py` if referenced**

Check `dcr/setup.py` — Park is not referenced in `after_install()`. No change needed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: remove Park DocType and add cleanup patch"
```

---

## Task 5: Update Print Format

**Files:**
- Modify: `dcr/dcr/print_format/new_home_info_sheet/new_home_info_sheet.json`

The print format currently does `frappe.get_doc("Park", doc.park)` and reads park fields. It needs to read directly from HBR fields instead.

- [ ] **Step 1: Remove the Park variable from the template header**

In the `html` field of `new_home_info_sheet.json`, find and remove:

```jinja
{% set park = frappe.get_doc("Park", doc.park) if doc.park else None %}
```

- [ ] **Step 2: Update the Community Information section**

Replace the entire Community Information block. Change from reading `park.park_name`, `park.address_line1`, etc. to reading `doc.community_name`, `doc.delivery_address`, etc.

Old:
```jinja
{% if doc.property_type == "Park" %}
  ...
  <td class="f-val">{{ park.park_name if park else '' }}</td>
  ...
  <td class="f-val">{{ park.address_line1 if park else '' }}</td>
  ...
  <td class="f-val">{{ (park.city or '') ~ ', ' ~ (park.state or '') ~ ' ' ~ (park.zip or '') if park else '' }}</td>
  ...
  <td class="f-val">{{ "Yes" if park and park.gated else "No" }}{% if park and park.access_code %} ... {{ park.access_code }}{% endif %}</td>
  ...
  <td class="f-val">{{ format_phone(park.office_phone) if park else '' }}</td>
  ...
  <td class="f-val">{{ park.contact_name if park else '' }}</td>
  ...
{% endif %}
```

New:
```jinja
{% if doc.property_type == "Park" %}
<table class="inv-items" style="margin-top: 24px !important;">
  <thead>
    <tr><th colspan="2">Community Information</th></tr>
  </thead>
  <tbody>
    <tr>
      <td class="f-lbl">Community Name</td>
      <td class="f-val">{{ doc.community_name or '' }}</td>
    </tr>
    <tr>
      <td class="f-lbl">Address</td>
      <td class="f-val">{{ doc.delivery_address or '' }}</td>
    </tr>
    <tr>
      <td class="f-lbl">City, St Zip</td>
      <td class="f-val">{{ (doc.city or '') ~ ', ' ~ (doc.state or '') ~ ' ' ~ (doc.zip or '') }}</td>
    </tr>
    <tr>
      <td class="f-lbl">Gated Community</td>
      <td class="f-val">{{ "Yes" if doc.gated else "No" }}{% if doc.access_code %} &nbsp;&nbsp; Access Code: {{ doc.access_code }}{% endif %}</td>
    </tr>
    <tr>
      <td class="f-lbl">Space #</td>
      <td class="f-val">{{ doc.space_number or '' }}</td>
    </tr>
    <tr>
      <td class="f-lbl">Office Phone</td>
      <td class="f-val">{{ format_phone(doc.contact_phone) }}</td>
    </tr>
    <tr>
      <td class="f-lbl">Community Contact</td>
      <td class="f-val">{{ doc.contact_name or '' }}</td>
    </tr>
  </tbody>
</table>
{% endif %}
```

- [ ] **Step 3: Commit**

```bash
git add dcr/dcr/print_format/new_home_info_sheet/new_home_info_sheet.json
git commit -m "fix: update print format to read community info from HBR fields"
```

---

## Task 6: Add Mapbox Address Autofill to HBR Form

**Files:**
- Modify: `dcr/public/js/home_build_request.js`

- [ ] **Step 1: Add Mapbox Search Box script loader**

Add a helper function at the top of the file (before the `frappe.ui.form.on` block) that dynamically loads the Mapbox Search Box JS and CSS:

```javascript
var _mapbox_loaded = false;

function load_mapbox_search(callback) {
    if (_mapbox_loaded) { callback(); return; }

    var css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = 'https://api.mapbox.com/search-js/v1.0.0-beta.22/web/style.css';
    document.head.appendChild(css);

    var script = document.createElement('script');
    script.src = 'https://api.mapbox.com/search-js/v1.0.0-beta.22/web/SearchBoxAPI.js';
    script.onload = function() {
        _mapbox_loaded = true;
        callback();
    };
    document.head.appendChild(script);
}
```

Note: The exact Mapbox Search Box JS URL and API may differ — check the current Mapbox docs at implementation time and use the latest stable version. The Search Box API provides `mapboxsdk.SearchBoxAPI` or similar namespace.

- [ ] **Step 2: Add address autofill logic to the `refresh` handler**

Inside `frappe.ui.form.on('Home Build Request', { refresh: ... })`, after the existing query setups, add:

```javascript
        // Mapbox address autofill
        if (!frm.doc.docstatus) {
            setup_address_autofill(frm);
        }
```

- [ ] **Step 3: Create the `setup_address_autofill` function**

Add after the `populate_checklist` function:

```javascript
function setup_address_autofill(frm) {
    var $input = frm.fields_dict.delivery_address.$input;
    if (!$input || $input.data('mapbox-bound')) return;
    $input.data('mapbox-bound', true);

    var _debounce = null;

    $input.on('input', function() {
        var query = $input.val();
        if (!query || query.length < 3) return;

        clearTimeout(_debounce);
        _debounce = setTimeout(function() {
            frappe.call({
                method: 'dcr.api.map.search_address',
                args: { query: query },
                callback: function(r) {
                    if (!r.message || !r.message.length) return;
                    show_address_dropdown(frm, $input, r.message);
                }
            });
        }, 300);
    });
}

function show_address_dropdown(frm, $input, suggestions) {
    // Remove existing dropdown
    $input.parent().find('.mapbox-dropdown').remove();

    var $dropdown = $('<ul class="mapbox-dropdown" style="'
        + 'position:absolute; z-index:100; background:#fff; border:1px solid #d1d8dd;'
        + 'border-radius:4px; max-height:200px; overflow-y:auto; width:100%;'
        + 'list-style:none; padding:0; margin:4px 0 0 0; box-shadow:0 2px 6px rgba(0,0,0,0.1);'
        + '"></ul>');

    for (var i = 0; i < suggestions.length; i++) {
        (function(s) {
            var $li = $('<li style="padding:8px 12px; cursor:pointer; font-size:13px;"></li>')
                .text(s.full_address)
                .on('mousedown', function(e) {
                    e.preventDefault();
                    frm.set_value('delivery_address', s.address || '');
                    frm.set_value('city', s.city || '');
                    frm.set_value('state', s.state || '');
                    frm.set_value('zip', s.zip || '');
                    frm.set_value('latitude', s.latitude || 0);
                    frm.set_value('longitude', s.longitude || 0);
                    $dropdown.remove();
                })
                .on('mouseenter', function() { $(this).css('background', '#f5f7fa'); })
                .on('mouseleave', function() { $(this).css('background', '#fff'); });
            $dropdown.append($li);
        })(suggestions[i]);
    }

    $input.parent().css('position', 'relative').append($dropdown);

    // Close on blur
    $input.one('blur', function() {
        setTimeout(function() { $dropdown.remove(); }, 200);
    });
}
```

- [ ] **Step 4: Commit**

```bash
git add dcr/public/js/home_build_request.js
git commit -m "feat: add Mapbox address autofill to HBR delivery_address field"
```

---

## Task 7: Create Map API Endpoints

**Files:**
- Create: `dcr/api/map.py`
- Create: `dcr/tests/test_map_api.py`

- [ ] **Step 1: Write tests for the search_address and get_heatmap_data endpoints**

Create `dcr/tests/test_map_api.py`:

```python
"""Tests for map API helper functions.

Pure function tests — no DB or Mapbox API dependency.
"""

import unittest
from unittest.mock import patch, MagicMock


class TestParseMapboxResponse(unittest.TestCase):
    """Test the response parser that extracts structured address data."""

    def test_parse_valid_feature(self):
        from dcr.api.map import _parse_mapbox_feature

        feature = {
            "geometry": {"coordinates": [-118.82, 34.14]},
            "properties": {
                "full_address": "123 Main St, Westlake Village, CA 93065",
                "address": "123 Main St",
                "place": "Westlake Village",
                "region": "California",
                "region_code": "CA",
                "postcode": "93065",
            }
        }
        result = _parse_mapbox_feature(feature)
        self.assertEqual(result["address"], "123 Main St")
        self.assertEqual(result["city"], "Westlake Village")
        self.assertEqual(result["state"], "CA")
        self.assertEqual(result["zip"], "93065")
        self.assertAlmostEqual(result["latitude"], 34.14)
        self.assertAlmostEqual(result["longitude"], -118.82)

    def test_parse_missing_fields_returns_empty_strings(self):
        from dcr.api.map import _parse_mapbox_feature

        feature = {
            "geometry": {"coordinates": [-118.0, 34.0]},
            "properties": {
                "full_address": "Unknown",
            }
        }
        result = _parse_mapbox_feature(feature)
        self.assertEqual(result["address"], "")
        self.assertEqual(result["city"], "")
        self.assertEqual(result["state"], "")
        self.assertEqual(result["zip"], "")
        self.assertEqual(result["full_address"], "Unknown")

    def test_parse_empty_feature(self):
        from dcr.api.map import _parse_mapbox_feature

        feature = {"geometry": {"coordinates": [0, 0]}, "properties": {}}
        result = _parse_mapbox_feature(feature)
        self.assertEqual(result["latitude"], 0)
        self.assertEqual(result["longitude"], 0)


class TestAggregateHeatmapData(unittest.TestCase):
    """Test the aggregation logic that groups HBRs by location."""

    def test_aggregate_groups_by_coordinates(self):
        from dcr.api.map import _aggregate_locations

        rows = [
            {"community_name": "Oak Forest", "delivery_address": "123 Main",
             "city": "Westlake", "state": "CA", "zip": "93065",
             "latitude": 34.14, "longitude": -118.82},
            {"community_name": "Oak Forest", "delivery_address": "123 Main",
             "city": "Westlake", "state": "CA", "zip": "93065",
             "latitude": 34.14, "longitude": -118.82},
            {"community_name": "Pine Valley", "delivery_address": "456 Oak",
             "city": "Simi", "state": "CA", "zip": "93063",
             "latitude": 34.27, "longitude": -118.78},
        ]
        result = _aggregate_locations(rows)
        self.assertEqual(len(result), 2)

        oak = next(r for r in result if r["community_name"] == "Oak Forest")
        self.assertEqual(oak["hbr_count"], 2)

        pine = next(r for r in result if r["community_name"] == "Pine Valley")
        self.assertEqual(pine["hbr_count"], 1)

    def test_aggregate_empty_list(self):
        from dcr.api.map import _aggregate_locations

        result = _aggregate_locations([])
        self.assertEqual(result, [])

    def test_aggregate_skips_zero_coordinates(self):
        from dcr.api.map import _aggregate_locations

        rows = [
            {"community_name": "No Coords", "delivery_address": "789 Elm",
             "city": "LA", "state": "CA", "zip": "90001",
             "latitude": 0, "longitude": 0},
        ]
        result = _aggregate_locations(rows)
        self.assertEqual(len(result), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest dcr/tests/test_map_api.py -v
```

Expected: FAIL — `dcr.api.map` module does not exist.

- [ ] **Step 3: Create `dcr/api/map.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest dcr/tests/test_map_api.py -v
```

Expected: All 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add dcr/api/map.py dcr/tests/test_map_api.py
git commit -m "feat: add map API endpoints for address search and heatmap data"
```

---

## Task 8: Create Custom HTML Block for Heatmap

**Files:**
- Modify: `dcr/setup.py`

The Custom HTML Block is created programmatically in `after_install` so it survives deploys. It contains the HTML container and JavaScript that loads Mapbox GL JS and renders the map.

- [ ] **Step 1: Add the Custom HTML Block creation to `setup.py`**

Add this function and call it from `after_install()`:

```python
def ensure_heatmap_block():
    """Create or update the workspace heatmap Custom HTML Block."""
    block_name = "HBR Heatmap"
    html_content = '<div id="dcr-heatmap" style="width:100%; height:calc(100vh - 140px); min-height:400px;"></div>'
    js_content = """
(function() {
    var container = root_element.querySelector('#dcr-heatmap');
    if (!container) return;

    // Full-bleed: break out of workspace padding
    var parent = root_element.closest('.widget-group') || root_element.parentElement;
    if (parent) {
        var cs = getComputedStyle(parent);
        var pl = parseInt(cs.paddingLeft) || 0;
        var pr = parseInt(cs.paddingRight) || 0;
        if (pl || pr) {
            root_element.style.marginLeft = '-' + pl + 'px';
            root_element.style.marginRight = '-' + pr + 'px';
            root_element.style.width = 'calc(100% + ' + (pl + pr) + 'px)';
        }
    }

    // Load Mapbox GL JS
    function loadMapbox(cb) {
        if (window.mapboxgl) { cb(); return; }
        var css = document.createElement('link');
        css.rel = 'stylesheet';
        css.href = 'https://api.mapbox.com/mapbox-gl-js/v3.3.0/mapbox-gl.css';
        document.head.appendChild(css);
        var s = document.createElement('script');
        s.src = 'https://api.mapbox.com/mapbox-gl-js/v3.3.0/mapbox-gl.js';
        s.onload = cb;
        document.head.appendChild(s);
    }

    function initMap() {
        frappe.call({
            method: 'dcr.api.map.get_map_settings',
            callback: function(r) {
                if (!r.message || !r.message.access_token) {
                    container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8d99a6;font-size:14px;">Configure Map Settings to enable the heatmap</div>';
                    return;
                }
                var cfg = r.message;
                mapboxgl.accessToken = cfg.access_token;
                var map = new mapboxgl.Map({
                    container: container,
                    style: cfg.map_style_url,
                    center: [cfg.default_longitude, cfg.default_latitude],
                    zoom: cfg.default_zoom
                });
                map.addControl(new mapboxgl.NavigationControl(), 'top-right');
                map.on('load', function() { loadData(map); });
            }
        });
    }

    function loadData(map) {
        frappe.call({
            method: 'dcr.api.map.get_heatmap_data',
            callback: function(r) {
                if (!r.message || !r.message.length) return;
                var geojson = {
                    type: 'FeatureCollection',
                    features: r.message.map(function(d) {
                        return {
                            type: 'Feature',
                            geometry: { type: 'Point', coordinates: [d.longitude, d.latitude] },
                            properties: {
                                community_name: d.community_name,
                                address: d.address,
                                hbr_count: d.hbr_count
                            }
                        };
                    })
                };

                // Heatmap layer
                map.addSource('hbr-locations', { type: 'geojson', data: geojson });
                map.addLayer({
                    id: 'hbr-heat',
                    type: 'heatmap',
                    source: 'hbr-locations',
                    paint: {
                        'heatmap-weight': ['interpolate', ['linear'], ['get', 'hbr_count'], 1, 0.3, 10, 1],
                        'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 0, 1, 12, 3],
                        'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 0, 15, 12, 30],
                        'heatmap-opacity': 0.6
                    }
                });

                // Cluster source
                map.addSource('hbr-clusters', {
                    type: 'geojson',
                    data: geojson,
                    cluster: true,
                    clusterMaxZoom: 14,
                    clusterRadius: 50,
                    clusterProperties: {
                        total_count: ['+', ['get', 'hbr_count']]
                    }
                });

                // Cluster circles
                map.addLayer({
                    id: 'clusters',
                    type: 'circle',
                    source: 'hbr-clusters',
                    filter: ['has', 'point_count'],
                    paint: {
                        'circle-color': ['step', ['get', 'total_count'], '#51bbd6', 5, '#f1f075', 15, '#f28cb1'],
                        'circle-radius': ['step', ['get', 'total_count'], 18, 5, 24, 15, 32],
                        'circle-stroke-width': 2,
                        'circle-stroke-color': '#fff'
                    }
                });

                // Cluster count labels
                map.addLayer({
                    id: 'cluster-count',
                    type: 'symbol',
                    source: 'hbr-clusters',
                    filter: ['has', 'point_count'],
                    layout: {
                        'text-field': ['to-string', ['get', 'total_count']],
                        'text-font': ['DIN Offc Pro Medium', 'Arial Unicode MS Bold'],
                        'text-size': 12
                    }
                });

                // Individual points
                map.addLayer({
                    id: 'unclustered-point',
                    type: 'circle',
                    source: 'hbr-clusters',
                    filter: ['!', ['has', 'point_count']],
                    paint: {
                        'circle-color': '#11b4da',
                        'circle-radius': 8,
                        'circle-stroke-width': 2,
                        'circle-stroke-color': '#fff'
                    }
                });

                // Popup on click — individual points
                map.on('click', 'unclustered-point', function(e) {
                    var p = e.features[0].properties;
                    var html = '<div style="font-family:Inter,sans-serif;font-size:13px;">'
                        + '<strong>' + (p.community_name || 'Unknown') + '</strong><br>'
                        + '<span style="color:#666;">' + (p.address || '') + '</span><br>'
                        + '<span style="font-weight:600;">' + p.hbr_count + ' deal' + (p.hbr_count > 1 ? 's' : '') + '</span><br>'
                        + '<a href="/app/home-build-request?community_name=' + encodeURIComponent(p.community_name) + '" style="color:#2490ef;">View deals</a>'
                        + '</div>';
                    new mapboxgl.Popup({ offset: 15 })
                        .setLngLat(e.features[0].geometry.coordinates)
                        .setHTML(html)
                        .addTo(map);
                });

                // Zoom into cluster on click
                map.on('click', 'clusters', function(e) {
                    map.getSource('hbr-clusters').getClusterExpansionZoom(
                        e.features[0].properties.cluster_id,
                        function(err, zoom) {
                            if (err) return;
                            map.easeTo({ center: e.features[0].geometry.coordinates, zoom: zoom });
                        }
                    );
                });

                // Cursor styles
                map.on('mouseenter', 'clusters', function() { map.getCanvas().style.cursor = 'pointer'; });
                map.on('mouseleave', 'clusters', function() { map.getCanvas().style.cursor = ''; });
                map.on('mouseenter', 'unclustered-point', function() { map.getCanvas().style.cursor = 'pointer'; });
                map.on('mouseleave', 'unclustered-point', function() { map.getCanvas().style.cursor = ''; });
            }
        });
    }

    loadMapbox(initMap);
})();
"""

    if frappe.db.exists("Custom HTML Block", block_name):
        block = frappe.get_doc("Custom HTML Block", block_name)
        block.html = html_content
        block.script = js_content
        block.save(ignore_permissions=True)
    else:
        frappe.get_doc({
            "doctype": "Custom HTML Block",
            "name": block_name,
            "html": html_content,
            "script": js_content,
            "private": 0,
        }).insert(ignore_permissions=True)
```

- [ ] **Step 2: Call `ensure_heatmap_block()` from `after_install()`**

At the end of the existing `after_install()` function in `dcr/setup.py`, before `frappe.db.commit()`, add:

```python
    ensure_heatmap_block()
```

- [ ] **Step 3: Add heatmap block to Overview and Deals workspaces**

Add to `after_install()`, before the commit:

```python
    # Link heatmap block to workspaces
    block_name = "HBR Heatmap"
    for ws_name in ("Overview", "Deals"):
        if not frappe.db.exists("Workspace", ws_name):
            continue
        ws = frappe.get_doc("Workspace", ws_name)
        block_linked = any(
            row.html_block_name == block_name
            for row in ws.get("custom_html_blocks", [])
        )
        if not block_linked:
            ws.append("custom_html_blocks", {"html_block_name": block_name})
            ws.save(ignore_permissions=True)
```

Note: The exact child table field name for linking Custom HTML Blocks to Workspaces may differ in Frappe v16. Verify the Workspace DocType's child table structure at implementation time. If workspaces don't have a `custom_html_blocks` child table, the block may need to be added manually via the workspace editor UI after deploy.

- [ ] **Step 4: Commit**

```bash
git add dcr/setup.py
git commit -m "feat: add heatmap Custom HTML Block creation in setup.py"
```

---

## Task 9: Final Integration — Hooks and Wiring

**Files:**
- Modify: `dcr/hooks.py` (if needed)

- [ ] **Step 1: Verify hooks.py doesn't need changes**

The map API endpoints are whitelisted methods accessed via `frappe.call()` — they don't need to be registered in hooks.py. The Custom HTML Block is created in `setup.py` which already runs via `after_install` / `after_migrate` hooks. The HBR JS is already loaded via `doctype_js`. No hooks.py changes needed.

- [ ] **Step 2: Ensure Map Settings is accessible in the sidebar**

Map Settings is a Single DocType — Frappe automatically makes it accessible at `/app/map-settings` for users with System Manager role. No sidebar link needed.

- [ ] **Step 3: Run all tests**

```bash
python -m pytest dcr/tests/ -v
```

Expected: All tests pass (test_required_docs.py unchanged, test_map_api.py new tests pass).

- [ ] **Step 4: Final commit if any changes**

```bash
git status
# Only commit if there are changes
```

---

## Task 10: Deployment Checklist

This task is not code — it's the deployment sequence for Frappe Cloud.

- [ ] **Step 1: Wipe company data on the Frappe Cloud instance**

Do this BEFORE deploying the code. The Park DocType still exists in the DB.

- [ ] **Step 2: Push to GitHub and deploy via Frappe Cloud dashboard**

`bench migrate` runs automatically, which:
- Creates the Map Settings DocType
- Runs the `remove_park_doctype` patch (drops Park from DB)
- Updates HBR with new fields (old park fields are orphaned in DB but harmless)
- Creates the Custom HTML Block via `after_install`

- [ ] **Step 3: Configure Map Settings**

Navigate to `/app/map-settings` and enter:
- Mapbox access token (from your Mapbox account)
- Default lat/lng/zoom (or keep defaults for Southwest US)
- Map style URL (or keep default streets style)

- [ ] **Step 4: Verify the heatmap block appears on Overview and Deals workspaces**

If the block wasn't auto-linked to the workspaces (see Task 8 Step 3 note), manually add it via the workspace editor:
1. Go to `/app/overview` (or `/app/deals`)
2. Click the edit/customize button
3. Add the "HBR Heatmap" Custom HTML Block
4. Save

- [ ] **Step 5: Restrict the Mapbox token by domain**

In Mapbox Studio > Account > Access Tokens, restrict the token to your Frappe Cloud domain URL.

- [ ] **Step 6: Create a test HBR to verify autofill and map**

1. Create a new HBR
2. Type an address in the Delivery Address field
3. Verify the autofill dropdown appears
4. Pick an address and verify city/state/zip/lat/lng auto-populate
5. Submit the HBR
6. Go to the Overview workspace and verify the point appears on the map
