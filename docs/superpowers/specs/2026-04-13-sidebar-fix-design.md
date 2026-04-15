# Frappe v16 Workspace Sidebar Fix

**Date:** 2026-04-13
**Status:** Draft
**Upstream issues:** frappe/frappe#37872 (open), frappe/frappe#35881 (closed, partial fix), frappe/frappe#37981 (related)

## Problem

Frappe v16's new Workspace Sidebar feature has three rendering bugs that affect DCR:

1. **Section Break items don't render.** The `TypeSectionBreak.make()` method returns early when `nested_items` is empty. Frappe stores sidebar items as a flat list in `frappe.boot.workspace_sidebar_item`, but the renderer expects Section Break items to have their children pre-populated in `nested_items`. Since they're flat siblings, the array is empty and the section never renders.

2. **Sidebar Item Group labels are missing.** `TypeSidebarItemGroup` inherits from `TypeLink` without overriding `make()`. The `TypeLink.make()` early-return guard skips items with no path unless they are `standard` or type `Section Break`. Item Groups have no `link_to` (they're group headers), so `get_path()` returns null and the guard kills rendering. Only the collapse chevron shows (added by a separate mechanism), with no label text.

3. **Active state highlights the wrong item.** When multiple sidebar items link to the same DocType with different `route_options`/`filters` (e.g., "Suppliers" and "Factories" both link to `Supplier`), Frappe highlights the first match by doctype name, ignoring URL query parameters.

## Approach

Fix bugs 1 and 2 at the data layer in `boot_session` (Python), before the client renders. Fix bug 3 with a new client-side JS file.

### Why data-layer for bugs 1 and 2

- Bug 1 is fundamentally a data structure problem (empty `nested_items`). The renderer code is correct — it just needs the right data shape.
- Bug 2 is bypassed by setting `standard: true` on Item Group items, which skips the early-return guard. Trade-off: hides drag handle and settings gear on those items in sidebar edit mode. Editing is still possible via the Workspace Sidebar form.
- No JS monkey-patching of Frappe class prototypes means no timing issues with ES module loading and no fragility against Frappe updates.

### Why JS for bug 3

Active-state matching doesn't exist in Frappe's sidebar code at all — it's new behavior, not a data fix.

## Design

### Part 1: Boot Data Restructure (`dcr/api/boot.py`)

Add a new function called after the existing null `link_to` filter in `boot_session`.

**Nesting algorithm:** Walk the flat `items` list for each workspace sidebar. Collect items into groups:

- Items before the first Section Break remain top-level
- When a Section Break is encountered, start collecting subsequent items into its `nested_items` array
- Continue collecting until the next Section Break or end of list
- Remove collected items from the top-level list

Before:
```
[Home, SectionBreak, Dealers, Suppliers, Factories, SectionBreak, Masters(group), AllCustomers(child), AllSuppliers(child)]
```

After:
```
[Home, SectionBreak{nested_items: [Dealers, Suppliers, Factories]}, SectionBreak{nested_items: [Masters, AllCustomers, AllSuppliers]}]
```

**Item Group marking:** During the same pass, set `standard = True` on any item with `type == "Sidebar Item Group"`. This includes items found inside `nested_items`.

**Scope:** Runs on every workspace sidebar in `bootinfo.workspace_sidebar_item`, not hardcoded to any specific workspace.

**Idempotency guard:** Before nesting, check if a Section Break already has populated `nested_items`. If so, skip that section — prevents double-nesting if boot_session runs multiple times or Frappe fixes this upstream.

### Part 2: Active-State Fix (`dcr/public/js/sidebar_fix.js`)

New file added to `app_include_js`.

**On each route change:**

1. Get current route doctype from `frappe.get_route()` and URL params from `window.location.search`
2. Determine the current workspace name from `frappe.app.sidebar?.current_workspace` or by reading the `data-workspace` attribute from the sidebar DOM, or by matching the current route against workspace pages in `frappe.boot.workspace_sidebar_item`
3. Read sidebar items from `frappe.boot.workspace_sidebar_item[workspace_name].items`
4. Flatten nested items (since Part 1 restructures them) to get all Link-type items
5. Find all items where `link_to` matches the current doctype
6. If 0 or 1 match, return (default behavior is correct)
7. If 2+ matches, score each by comparing its `route_options` (parsed from JSON string) against URL params — count matching key/value pairs, require all of the item's params to match
8. **Tie-breaker:** If multiple items have the same score, prefer the one appearing first in the sidebar config (stable document order)
9. Find the best-scoring item's label in the sidebar DOM
10. Remove `.active` class from all sidebar item containers
11. Add `.active` to the best match's container

**Defensive parsing:** Wrap `JSON.parse` of `route_options`/`filters` in try/catch — malformed JSON silently skips that item. Normalize URL param values (decode URI components) before comparison.

**Workspace resolution priority:**
1. `frappe.app.sidebar?.current_workspace`
2. `data-workspace` attribute from sidebar DOM
3. Match current route's doctype against items across all workspaces in boot data
4. If unresolved, exit silently — do not mutate sidebar DOM across workspaces

**Route change hook:** Use `frappe.router.on("change", fn)` with a fallback to `$(document).on("page-change", fn)` if the former doesn't exist. Run with `setTimeout(..., 300)` to let Frappe's default logic run first, then override.

**Guard:** Only runs when URL has query params AND multiple sidebar items share the same `link_to`. Otherwise no-op.

### Part 3: Integration (`dcr/hooks.py`)

Change `app_include_js` from a single string to a list:

```python
app_include_js = ["/assets/dcr/js/icon_fix.js", "/assets/dcr/js/sidebar_fix.js"]
```

No changes to `icon_fix.js`.

## Files Changed

| File | Change |
|------|--------|
| `dcr/api/boot.py` | Add nesting + `standard` marking after existing filter |
| `dcr/public/js/sidebar_fix.js` | New file — active-state matching |
| `dcr/hooks.py` | Add `sidebar_fix.js` to `app_include_js` |

## Known Limitations

- **Edit-mode side effect:** Sidebar Item Group items marked `standard: true` won't show inline drag/edit controls. Users can still edit via Workspace Sidebar > [sidebar name] form.
- **300ms delay:** Active-state fix runs after a timeout to avoid racing Frappe's own logic. On very slow connections, the wrong item may flash briefly before correction.
- **Upstream dependency:** If Frappe fixes these bugs upstream (frappe/frappe#37872), the boot_session nesting will be redundant (but harmless — it just re-nests already-nested items). The `standard: true` marking and active-state fix would still be needed unless those specific issues are also addressed.

## Testing

1. **Section Breaks:** Verify visual separators appear between item groups in the Contacts sidebar (and any other workspace with Section Breaks configured)
2. **Item Group labels:** Verify "Masters" label (and any other configured group names) appears next to the collapse chevron
3. **Group nesting:** Verify child items (All Customers, All Suppliers) appear indented under the Masters group
4. **Active state:** Navigate to `/app/supplier` — "Suppliers" should highlight. Navigate to Factories (with its route_options) — "Factories" should highlight instead.
5. **No regression:** Desktop icons still render correctly. Sidebar items without Section Breaks or Item Groups still work.
