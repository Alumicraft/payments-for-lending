# Add a dashboard chart

Before building a **Custom** chart, ask: **can a built-in chart type do it?** Custom charts are the most failure-prone path in Frappe v16 (see the gotchas at the bottom — this app paid for every one). Reach for the simpler option first:

| Need | Use | Notes |
|---|---|---|
| Count/sum of one doctype over time | **Count / Sum** chart (UI) | No code. Set Document Type + date field in the form. |
| Break one doctype down by a field | **Group By** chart (UI) | No code. Renders multi-series bars (e.g. "Deals By Order Stage"). |
| Anything a saved report already shows | **Report** chart (UI) | Point at a Query/Script Report. The proven path in this app. |
| Multiple doctypes in one chart, `CASE WHEN` bucketing, or a shape the UI can't express | **Custom** (this playbook) | Code + filesystem layout + fixture. Use only when the above can't. |

The three accounting/deals charts (`Inflows vs Outflows`, `Past-Due Aging`, `New Deals by Type`) are Custom because they need two doctypes, aging buckets, and a stacked series respectively. Canonical example: `dcr/api/dashboard.py` + `dcr/dcr/dashboard_chart_source/past_due_aging/`.

## How a Custom chart actually resolves (read this once)

Custom charts are resolved **client-side**, not by the server `dashboard_chart.get` endpoint (which has no `Custom` branch). The render flow:

1. Frontend reads the Dashboard Chart, sees `chart_type = "Custom"`, takes its `source`.
2. Frontend calls `dashboard_chart_source.get_config(name=source)` → server `read_config()` reads **`{scrub(name)}.js`** from the source folder and returns its text.
3. Frontend `eval()`s that JS, which must register `frappe.dashboards.chart_sources[source] = {method, filters}`.
4. Frontend reads `.filters` and calls `.method` via `xcall`, passing framework kwargs.

**The `.js` file is the whole contract.** No `.py` file is needed in the source folder — the method is named explicitly in the `.js` and can live anywhere (we keep ours in `dcr/api/dashboard.py`).

## File layout

```
dcr/dcr/dashboard_chart_source/<scrub_name>/
├── __init__.py              # empty
├── <scrub_name>.json        # Dashboard Chart Source record
└── <scrub_name>.js          # REQUIRED — registers source + names the method

dcr/api/dashboard.py         # the whitelisted data method(s)
dcr/fixtures/dashboard_chart.json   # the Dashboard Chart record(s)
```

`<scrub_name>` is `frappe.scrub(source_name)` — lowercased, spaces/hyphens → underscores. `"Past-Due Aging"` → `past_due_aging`. The folder must sit under `get_module_path("DCR")` = `dcr/dcr/`.

## 1. The data method (`dcr/api/dashboard.py`)

```python
@frappe.whitelist()
def past_due_aging(**kwargs):
    # ... return frappe-charts format:
    return {"labels": [...], "datasets": [{"name": "...", "values": [...]}]}
```

- **Must be `@frappe.whitelist()`** — the frontend calls it via `xcall`.
- **Must accept `**kwargs`** — the chart widget always passes `chart_name, filters, refresh, time_interval, timespan, from_date, to_date, heatmap_year`. A bare `def f():` raises a TypeError at render. Ignore them unless you wire up real filters.
- Return `{"labels": [...], "datasets": [{"name", "values"}, ...]}`. Multiple datasets = multiple/stacked series.

## 2. The source `.js` config

```js
frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Past-Due Aging"] = {
	method: "dcr.api.dashboard.past_due_aging",
	filters: [],
};
```

- The bracket key **must equal** the Dashboard Chart's `source` (the DCS record name).
- `filters: []` if the chart takes no user filters. (`.filters` is read directly by the frontend — omitting it crashes the render.)
- Read as raw text server-side and eval'd client-side — **no `bench build` needed**, but bump nothing-special; a hard browser refresh after deploy picks up changes.

## 3. The Dashboard Chart Source record (`<scrub_name>.json`)

```json
{
 "doctype": "Dashboard Chart Source",
 "module": "DCR",
 "name": "Past-Due Aging",
 "source_name": "Past-Due Aging",
 "timeseries": 0
}
```

Auto-synced from the filesystem on `bench migrate` — **not** a `hooks.py` fixture. `on_update` blocks UI edits outside developer mode, but migrate sets `frappe.request = None` and skips that guard, so the sync works on Frappe Cloud.

## 4. The Dashboard Chart record (`dcr/fixtures/dashboard_chart.json`)

```json
{
 "doctype": "Dashboard Chart",
 "name": "Past-Due Aging",
 "chart_name": "Past-Due Aging",
 "chart_type": "Custom",
 "source": "Past-Due Aging",
 "type": "Bar",
 "timeseries": 0,
 "filters_json": "[]",
 "is_public": 1,
 "module": "DCR",
 "custom_options": "{\"colors\":[\"#fbe687\",\"#fd7e14\",\"#dc3545\",\"#a02020\"]}"
}
```

Add the chart name to the `Dashboard Chart` block in `hooks.py` `fixtures`. Key fields:

- **`source`** = the DCS record name (NOT a Python path).
- **`filters_json`: `"[]"`** — mandatory; fixture import fails without it.
- **Do NOT set `is_standard`** — the validate hook throws "Cannot edit Standard charts" on fixture insert. Leave it off; the chart becomes a normal code-installed record.
- **`custom_options`** — JSON string. `{"colors":[...]}` for series colors; add `"stacked":1` for stacked bars.
- **`timespan` / `time_interval` are irrelevant for Custom charts** (they drive the server date-window path, which Custom never hits). Don't bother setting them.

## 5. Add to a workspace

Charts must exist on the site *before* you reference them from a workspace (the `save_page` override in `dcr/api/workspace.py` strips orphan chart blocks). So: deploy first, then in the UI open the workspace and add the chart. Verify standalone first at `/app/dashboard-chart/<name>`.

## Deploy & verify

1. Tests: the data methods are pure logic — cover them in `dcr/tests/test_dashboard.py` (mock `frappe.db.sql`, assert the `{labels, datasets}` shape, and that they tolerate framework kwargs).
2. Run `preflight`, push to `main` (see `deploy-to-frappe-cloud.md`).
3. After deploy, hard-refresh and open `/app/dashboard-chart/<name>` — it should render.
4. Add to the workspace.

**Standalone debug check** (don't test via `dashboard_chart.get` — it doesn't handle Custom):
```js
frappe.call({method: "dcr.api.dashboard.past_due_aging"}).then(r => console.log(r.message))
```

## v16 gotchas this app already hit

Each of these cost a failed deploy. The recipe above avoids them; listed here so the symptoms are searchable:

1. **`source` is a record name, not a method path.** Putting `dcr.api.dashboard.x` in `source` → "Dashboard Chart Source ... not found".
2. **Missing `.js` → silent client crash.** `read_config()` returns `""`, nothing registers, `chart_sources[source]` is undefined → `Cannot read properties of undefined (reading 'filters')` at `dashboard_utils.js`. This was the root-cause blocker.
3. **`filters_json` is mandatory** even for Custom → `MandatoryError` on fixture import.
4. **`is_standard: 1` blocks fixture insert** → "Cannot edit Standard charts".
5. **Method without `**kwargs`** → TypeError when the widget passes its 8 framework args.
6. **`frappe.model.rename_field` moved** to `frappe.model.utils.rename_field` in v16 (unrelated patch trap that blocked migrate during this work).
