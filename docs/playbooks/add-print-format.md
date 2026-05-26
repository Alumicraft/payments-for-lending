# Add a new print format

DCR print formats are **single-file JSON** with the Jinja HTML inlined as a string in the `html` field. No separate `.html` file. See `dcr/dcr/print_format/new_home_info_sheet/new_home_info_sheet.json` for the canonical example.

## File layout

```
dcr/dcr/print_format/<snake_case_name>/
└── <snake_case_name>.json
```

The folder name and JSON filename are identical. No `__init__.py` needed (it's not a Python package).

## JSON skeleton

```json
{
  "name": "Human Readable Name",
  "doctype": "Print Format",
  "doc_type": "Source Doctype",
  "module": "DCR",
  "print_format_type": "Jinja",
  "standard": "Yes",
  "custom_format": 0,
  "print_format_builder": 0,
  "disabled": 0,
  "html": "...inlined Jinja+HTML+CSS as a single escaped string..."
}
```

Key fields:
- **`name`** — display name, shown in the Print menu. Title case with spaces.
- **`doc_type`** — the source doctype this format renders. Must match an existing doctype exactly (e.g., `"Home Build Request"`, not `"home_build_request"`).
- **`module`** — always `"DCR"`.
- **`standard: "Yes"`** — this is a code-managed format. Required for fixture export.
- **`html`** — the entire template, escaped as a JSON string (newlines as `\n`, quotes as `\"`).

## Variants in one format vs. separate formats

**Default: one print format with Jinja conditionals.** New Home Info Sheet handles 5 variants (Spec/Customer Sold × Cash/Floored × Park/Private) in a single file. Branch with `{% if doc.home_type == "..." %}` blocks.

**Separate format only when** the documents go to different recipients or on different cadences. Exhibit A + ACH Approval are combined because they always go in the same DocuSign packet.

## Jinja conventions used in DCR

Look at `new_home_info_sheet.json` for the canonical patterns. The common helpers:

```jinja
{# Resolve linked records once at the top #}
{% set company_doc = frappe.db.get_value("Company", doc.company, ["company_logo", "email", "phone_no"], as_dict=1) if doc.company else {} %}
{% set buyer = frappe.get_doc("Customer", doc.home_buyer) if doc.home_buyer else None %}

{# Reusable formatting macros #}
{%- macro format_currency(amount) -%}
{{ frappe.utils.fmt_money(amount, currency="USD") }}
{%- endmacro -%}

{%- macro fmt_date(d) -%}
{%- if d -%}{{ frappe.utils.formatdate(d, "MM/dd/yyyy") }}{%- endif -%}
{%- endmacro -%}

{# Phone formatter that handles 10- and 11-digit input #}
{%- macro format_phone(phone) -%} ... {%- endmacro -%}
```

Every value rendered into the template should pass through `or ''` (text) or `if X else ''` (currency/dates) so missing data doesn't render the literal string `None`.

## Styling

DCR's print formats use **inline styles with `!important`** because Frappe's default print stylesheet otherwise overrides everything. The pattern:

- `<link href="https://fonts.googleapis.com/css2?family=Inter..." rel="stylesheet">` for the body font
- A `<style>` block at the top defining `.inv`, `.inv-items`, `.lbl`, `.val`, etc.
- All rules use `!important`
- Use `class="inv-items"` for field tables, `class="no-break"` for blocks that shouldn't split across pages

Don't re-implement headers/footers in Jinja — use Frappe's Letter Head feature for those when possible.

## DocuSign signature anchors

For documents that flow through DocuSign, place anchors as **hidden 1px white text** next to where the signature/date should render. The DCR pattern uses `/sig1/`, `/sig2/`, `/ds1/`, `/ds2/` etc.:

```html
<div class="lbl">Signed:
  <span style="color: #fff !important; font-size: 1px !important;">/sig1/</span>
  <span class="sig-line">&nbsp;</span>
</div>
<div class="lbl">Date:
  <span style="color: #fff !important; font-size: 1px !important;">/ds1/</span>
  <span class="sig-line">&nbsp;</span>
</div>
```

DocuSign scans the rendered PDF for these anchors and places the signature/date fields there. Numbering scheme: `sig1` + `ds1` are signer 1, `sig2` + `ds2` are signer 2, etc.

## Linking it up

1. Verify `doc_type` matches an existing doctype name exactly.
2. If the format references custom fields on the source doctype, confirm those custom fields are in `dcr/fixtures/custom_field.json` and exported.
3. Print formats with `standard: "Yes"` are picked up automatically — **no `hooks.py` entry needed** (unlike `doctype_js`).

## Testing locally

You can't run `bench` locally. The fastest test loop is:
1. Push to a Frappe Cloud staging bench (if one exists) and open a real record → Print → select the new format.
2. If no staging exists, push to main during a low-traffic window and verify on prod against one record.
3. For Jinja syntax errors specifically: copy the `html` field, unescape it, and run `python -c "from jinja2 import Template; Template(open('test.html').read())"` to at least catch parse errors before push.

## Checklist

- [ ] Folder + JSON file created with matching `<snake_case_name>`
- [ ] `doc_type` matches an existing doctype name exactly
- [ ] `module: "DCR"`, `print_format_type: "Jinja"`, `standard: "Yes"`
- [ ] All Jinja values guarded against `None` (`or ''`, `if X else ''`)
- [ ] If signed: DocuSign anchors placed and numbered consistently
- [ ] Variants handled with `{% if %}` blocks rather than duplicating the format
- [ ] Custom fields referenced exist in `fixtures/custom_field.json`
- [ ] Tested on one real record before declaring done
