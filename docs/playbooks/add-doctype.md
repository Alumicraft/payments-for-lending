# Add a new doctype

Before adding a doctype, ask: **does this need its own lifecycle, child tables, or permission rules?** If not, a section + custom fields on an existing doctype is usually the right call. Adding a doctype creates schema, fixtures, and a deploy migration; sections are nearly free.

## File layout

```
dcr/dcr/doctype/<snake_case_name>/
├── __init__.py              # empty
├── <snake_case_name>.json   # schema
├── <snake_case_name>.py     # server-side logic
└── <snake_case_name>.js     # client controller (optional, only if you need form UX)
```

See `dcr/dcr/doctype/home_build_request/` for a canonical example.

## JSON schema essentials

```json
{
  "name": "Doctype Name",
  "doctype": "DocType",
  "module": "DCR",
  "engine": "InnoDB",
  "naming_rule": "Expression (old style)",
  "autoname": "format:HBR-.YYYY.-.####",
  "fields": [ ... ],
  "permissions": [ ... ]
}
```

### Required choices

- **`module`** — always `"DCR"`.
- **`naming_rule` + `autoname`** — DCR uses prefix series like `HBR-.YYYY.-.####` (Home Build Request), `MIFA-.YYYY.-.####`, etc. Pick a 3-4 letter prefix that's unambiguous in the system.
- **`fields`** — see the existing doctypes for the field-type vocabulary (`Data`, `Link`, `Select`, `Currency`, `Date`, `Table`, `Section Break`, `Column Break`).
- **`permissions`** — start by copying the perms from a similarly-scoped doctype rather than designing from scratch.

### The `custom + is_standard` trap

**Never set both `"custom": 1` and `"is_standard": 1` on the same doctype JSON.** This combination triggers a `TypeLink.make()` indent property error on Frappe v16 (see [claude-mem observation #176]).

For code-managed doctypes in this app, the right setting is `"custom": 0` (the default — omit the field entirely). `is_standard` is for fixtures, not doctype JSON.

## Server-side logic (`<name>.py`)

```python
import frappe
from frappe.model.document import Document


class DoctypeName(Document):
    def validate(self):
        # data integrity checks here
        pass

    def before_save(self):
        # derived field computation here
        pass
```

DCR convention is **status field + server-side validation**, not formal Workflows. Status transitions are enforced in `validate()`. The trade-off is no automatic email-on-status-change; if you need that, call `frappe.sendmail` from `validate()` per transition.

## Client controller (`<name>.js`) — optional

Only add a `.js` file if the form genuinely needs UX logic (dynamic field visibility, computed display values, custom buttons). Don't put data integrity in here — it can be bypassed via the API.

If you add one, also register it in `hooks.py`:

```python
doctype_js = {
    "Doctype Name": "public/js/doctype_name.js",
    # ... existing entries
}
```

And the actual JS file goes in `dcr/public/js/<name>.js`, **not** in the doctype folder. The doctype folder `.js` is for the form controller; `public/js/` is what `doctype_js` resolves against.

## Fixtures

If the doctype itself is the entity, the JSON in `dcr/dcr/doctype/<name>/` *is* the source of truth. No fixture export needed.

If you're adding **custom fields** to a standard doctype (e.g., adding fields to `Customer` or `Loan Application`), those go in `dcr/fixtures/custom_field.json`. Export pattern:

1. Create the custom fields in the Frappe Cloud UI on a dev site, OR write them directly into `custom_field.json` following the existing entries' structure.
2. If creating via UI: export with the fixtures mechanism (handled per the `hooks.py` `fixtures` config).
3. **Property Setters** (changing standard field properties — hidden, default, read_only, fetch_from) require an explicit entry in `hooks.py`'s `fixtures` list under `"doctype": "Property Setter"` with a `name IN (...)` filter. New property setter names must be added to that list or they won't export.

## Migrations and renames

If you're **renaming a field** or **moving data** between doctypes:

1. Add a patch in `dcr/patches/<name>.py`:
   ```python
   import frappe

   def execute():
       frappe.db.sql("""UPDATE `tabSome Doctype` SET new_field = old_field WHERE ...""")
       frappe.db.commit()
   ```
2. Register it in `dcr/patches.txt`:
   ```
   dcr.patches.<name>
   ```
3. Patches run **once** in order during the post-deploy migrate. Write them to be idempotent — a patch that re-runs (e.g., a deploy retry) should not corrupt data.

For **renaming a doctype itself**, you need a `rename_doc` patch — see `dcr/patches/rename_dcr_floored.py` for the SQL-update pattern, and Frappe's `frappe.rename_doc` for full doctype renames.

## Permissions

Default minimum:

```json
"permissions": [
  { "role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1,
    "submit": 0, "cancel": 0, "amend": 0, "report": 1, "export": 1, "import": 1,
    "share": 1, "print": 1, "email": 1 },
  { "role": "DCR User", "read": 1, "write": 1, "create": 1, "report": 1,
    "print": 1, "email": 1, "share": 1 }
]
```

Adjust based on whether the doctype is submittable (workflow-style), user-visible vs. admin-only, etc. Copy from the closest existing doctype.

## Checklist

- [ ] Folder created with `__init__.py`, `.json`, `.py` (and `.js` only if needed)
- [ ] `module: "DCR"`, no `"custom": 1` + `"is_standard": 1` combo
- [ ] Naming series prefix chosen and not collide with existing ones
- [ ] Fields, permissions, naming reviewed against a similar existing doctype
- [ ] Server `validate()` covers data integrity (not the JS controller)
- [ ] If `.js` added: registered in `hooks.py` `doctype_js`, file lives in `public/js/`
- [ ] Custom fields on standard doctypes → `fixtures/custom_field.json` updated
- [ ] Property setters → added to `hooks.py` `fixtures` filter list
- [ ] Data migrations → patch in `dcr/patches/` + entry in `patches.txt`
- [ ] [preflight](../../.claude/agents/preflight.md) and [v16-linter](../../.claude/agents/v16-linter.md) pass clean before push
