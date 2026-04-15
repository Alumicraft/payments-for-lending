# Loan Application Field Restructure v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize Loan Application into 7 clean sections matching the spec, removing duplicate fields and merging Exhibit A into Lending.

**Architecture:** Fixtures define custom fields with properties. Property Setters hide/configure standard fields. A Customize Form API reorder in `after_migrate` enforces exact field order every deploy — this is the key lesson from the failed v1 attempt. No `dcr_` mirror fields.

**Tech Stack:** Frappe Framework v15, Python (setup.py, patches, server hooks), JavaScript (client script), Jinja (print formats)

**Spec:** `docs/superpowers/specs/2026-03-26-loan-application-field-order.md`

**Critical constraints (from v1 failure):**
- `insert_after` does NOT reliably control field order on Frappe Cloud
- Hiding a standard section break hides ALL its children — only safe after reorder moves children away
- Patches run BEFORE fixture sync; `after_migrate` runs AFTER fixture sync
- Standard fields cannot be deleted — only hidden and repositioned

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `dcr/patches/cleanup_la_fields.py` | Create | One-time: delete orphaned + removed custom fields |
| `dcr/patches.txt` | Modify | Register new patch |
| `dcr/fixtures/custom_field.json` | Modify | Update LA custom fields (remove 7, add 7, update 8) |
| `dcr/fixtures/property_setter.json` | Modify | Add ~20 property setters for LA standard fields |
| `dcr/hooks.py` | Modify | Update fixture filter list |
| `dcr/setup.py` | Modify | Add Customize Form API reorder in `after_install` |
| `dcr/public/js/loan_application.js` | Modify | Add auto-calculation triggers |
| `dcr/api/lending.py` | Modify | Replace `requested_advance_amount` refs with `loan_amount` |
| `dcr/dcr/print_format/exhibit_a_receipt/exhibit_a_receipt.json` | Modify | `requested_advance_amount` → `loan_amount` |
| `dcr/dcr/print_format/ach_recurring_payment_authorization/ach_recurring_payment_authorization.json` | Modify | Hardcode autopay text, remove `first_autopay_description` ref |
| `dcr/dcr/print_format/advance_pre_approval/advance_pre_approval.json` | Modify | `requested_advance_amount` → `loan_amount`, `custom_projected_investment` → `loan_amount` |
| `dcr/api/dcr_email.py` | Modify | Rename `requested_advance_amount` param to `loan_amount` in `send_flooring_packet_sent` |

**Out of scope (already implemented per user):**
- Park `space_rent` field and HBR `park_space_rent` field
- HBR `home_serial_no` and `quote_no` fields

**Deferred items:**
- Connections sidebar ("Lending" group label) — cosmetic, can be done separately
- `outstanding_loan_balance`, `available_credit`, `custom_current_yn` real-time client-side fetch on form load — currently calculated server-side on validate, which is sufficient for now

---

## Task 1: Patch — Delete orphaned and removed custom fields

**Files:**
- Create: `dcr/patches/cleanup_la_fields.py`
- Modify: `dcr/patches.txt`

This patch runs BEFORE fixture sync. It deletes:
- **Orphans from failed v1** (exist on Cloud, not in fixtures): `dcr_documents_section`, `lending_calculations_section`
- **Fields being removed per spec**: `requested_advance_amount`, `first_autopay_description`, `custom_projected_investment`
- **Sections/breaks being replaced**: `dcr_lending_section`, `exhibit_a_section`, `column_break_exhibit_a`, `column_break_dcr_lending`

After this patch, fixture sync recreates fields with correct names/properties.

- [ ] **Step 1: Create the patch file**

```python
# dcr/patches/cleanup_la_fields.py
import frappe

def execute():
    """Delete orphaned and removed Loan Application custom fields.

    Runs before fixture sync so new fields can be created cleanly.
    """
    fields_to_delete = [
        # Orphans from failed v1 restructure (exist on Cloud, not in fixtures)
        "Loan Application-dcr_documents_section",
        "Loan Application-lending_calculations_section",
        # Fields removed per spec
        "Loan Application-requested_advance_amount",
        "Loan Application-first_autopay_description",
        "Loan Application-custom_projected_investment",
        # Sections/breaks being replaced with new names
        "Loan Application-dcr_lending_section",
        "Loan Application-exhibit_a_section",
        "Loan Application-column_break_exhibit_a",
        "Loan Application-column_break_dcr_lending",
        # May exist from previous deploys (safe to attempt — skips if not found)
        "Loan Application-doc_checklist",
    ]

    for field_name in fields_to_delete:
        if frappe.db.exists("Custom Field", field_name):
            frappe.delete_doc("Custom Field", field_name, force=True)
            print(f"  Deleted: {field_name}")
        else:
            print(f"  Skipped (not found): {field_name}")

    frappe.db.commit()
```

- [ ] **Step 2: Register the patch**

Append to `dcr/patches.txt`:
```
dcr.patches.cleanup_la_fields
```

- [ ] **Step 3: Commit**

```bash
git add dcr/patches/cleanup_la_fields.py dcr/patches.txt
git commit -m "patch: delete orphaned and removed LA custom fields"
```

---

## Task 2: Update custom field fixtures

**Files:**
- Modify: `dcr/fixtures/custom_field.json`

**Remove** these LA entries from the JSON array (7 fields):
- `Loan Application-requested_advance_amount`
- `Loan Application-first_autopay_description`
- `Loan Application-custom_projected_investment`
- `Loan Application-dcr_lending_section`
- `Loan Application-exhibit_a_section`
- `Loan Application-column_break_exhibit_a`
- `Loan Application-column_break_dcr_lending`

**Add** these new LA entries (7 fields):
```json
{
  "doctype": "Custom Field",
  "name": "Loan Application-column_break_header",
  "dt": "Loan Application",
  "fieldname": "column_break_header",
  "fieldtype": "Column Break",
  "insert_after": "applicant_name"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-lending_section",
  "dt": "Loan Application",
  "fieldname": "lending_section",
  "fieldtype": "Section Break",
  "label": "Lending",
  "insert_after": "factory"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-column_break_lending",
  "dt": "Loan Application",
  "fieldname": "column_break_lending",
  "fieldtype": "Column Break",
  "insert_after": "floor_plan"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-lending_calculations_section",
  "dt": "Loan Application",
  "fieldname": "lending_calculations_section",
  "fieldtype": "Section Break",
  "label": "Lending calculations",
  "insert_after": "buyer_name"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-column_break_lending_calc",
  "dt": "Loan Application",
  "fieldname": "column_break_lending_calc",
  "fieldtype": "Column Break",
  "insert_after": "custom_current_yn"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-dcr_documents_section",
  "dt": "Loan Application",
  "fieldname": "dcr_documents_section",
  "fieldtype": "Section Break",
  "label": "Signed documents",
  "insert_after": "custom_notes"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-column_break_repayment",
  "dt": "Loan Application",
  "fieldname": "column_break_repayment",
  "fieldtype": "Column Break",
  "insert_after": "repayment_method"
}
```

**Update** these existing LA entries (property changes only):

| Field | Changes |
|-------|---------|
| `deal_reference_section` | label: "Deal reference" (sentence case) |
| `advance_date_requested` | label: "Advance Date" (was "Advance Date Requested") |
| `home_serial_no` | insert_after: "advance_date_requested" (was exhibit_a_section) |
| `quote_no` | insert_after: "home_serial_no" |
| `floor_plan` | label: "Model" (was "Floor Plan"), insert_after: "quote_no" |
| `buyer_name` | label: "Buyer Name" (was "Buyer Name (End Customer)"), remove description, insert_after: "column_break_lending" |
| `monthly_interest_amount` | read_only: 1, insert_after: "column_break_lending_calc" |
| `monthly_insurance_amount` | insert_after: "monthly_interest_amount" |
| `advance_preapproval_section` | label: "Pre-approval letter" (was "Advance Pre-Approval"), collapsible: 0, depends_on: "eval:doc.home_type=='Spec'" (keep existing), insert_after: "total_payable_interest" |
| `custom_current_yn` | label: "Current" (was "Current Y/N"), read_only: 1, insert_after: "outstanding_loan_balance" |
| `custom_projected_sales_price` | insert_after: "advance_preapproval_section", fetch_from: "home_build_request.selling_price" |
| `custom_projected_equity` | insert_after: "custom_projected_sales_price", read_only: 1 |
| `custom_projected_ltv` | insert_after: "custom_projected_equity", read_only: 1 |
| `custom_projected_payoff` | insert_after: "custom_projected_ltv" |
| `column_break_preapproval` | insert_after: "custom_projected_payoff" |
| `custom_monthly_space_rent` | insert_after: "column_break_preapproval", fetch_from: "home_build_request.park_space_rent", read_only: 1 |
| `custom_notes` | insert_after: "custom_monthly_space_rent" |
| `signed_packet` | insert_after: "dcr_documents_section" (was "doc_checklist") |
| `available_credit` | insert_after: "lending_calculations_section" (was "outstanding_loan_balance") |
| `outstanding_loan_balance` | insert_after: "available_credit" (was "column_break_dcr_lending") |

**Note:** `insert_after` values are set for fixture sync but the ACTUAL order is enforced by the Customize Form API reorder in `after_migrate` (Task 5). Don't rely on insert_after for correctness.

- [ ] **Step 1: Remove 7 deleted field entries from the JSON array**
- [ ] **Step 2: Add 7 new field entries to the JSON array**
- [ ] **Step 3: Update properties on existing field entries per table above**
- [ ] **Step 4: Commit**

```bash
git add dcr/fixtures/custom_field.json
git commit -m "fixtures: update LA custom fields for restructure"
```

---

## Task 3: Add property setters for LA standard fields

**Files:**
- Modify: `dcr/fixtures/property_setter.json`

Add property setters for ALL standard Loan Application fields that need hiding, defaults, or read_only. **Do NOT** add property setters for standard section breaks — those are handled in `after_migrate` after field reorder (Task 5).

```json
[
  {"doctype":"Property Setter","name":"Customer-first_name-hidden","doc_type":"Customer","doctype_or_field":"DocField","field_name":"first_name","property":"hidden","property_type":"Check","value":"1"},
  {"doctype":"Property Setter","name":"Customer-last_name-hidden","doc_type":"Customer","doctype_or_field":"DocField","field_name":"last_name","property":"hidden","property_type":"Check","value":"1"},

  {"doctype":"Property Setter","name":"Loan Application-applicant_type-hidden","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"applicant_type","property":"hidden","property_type":"Check","value":"1"},
  {"doctype":"Property Setter","name":"Loan Application-applicant_type-default","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"applicant_type","property":"default","property_type":"Text","value":"Customer"},
  {"doctype":"Property Setter","name":"Loan Application-is_term_loan-hidden","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"is_term_loan","property":"hidden","property_type":"Check","value":"1"},
  {"doctype":"Property Setter","name":"Loan Application-is_secured_loan-hidden","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"is_secured_loan","property":"hidden","property_type":"Check","value":"1"},
  {"doctype":"Property Setter","name":"Loan Application-description-hidden","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"description","property":"hidden","property_type":"Check","value":"1"},
  {"doctype":"Property Setter","name":"Loan Application-proposed_pledges-hidden","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"proposed_pledges","property":"hidden","property_type":"Check","value":"1"},
  {"doctype":"Property Setter","name":"Loan Application-maximum_loan_amount-hidden","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"maximum_loan_amount","property":"hidden","property_type":"Check","value":"1"},
  {"doctype":"Property Setter","name":"Loan Application-repayment_method-hidden","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"repayment_method","property":"hidden","property_type":"Check","value":"1"},
  {"doctype":"Property Setter","name":"Loan Application-repayment_method-default","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"repayment_method","property":"default","property_type":"Text","value":"Repay Over Number of Periods"},
  {"doctype":"Property Setter","name":"Loan Application-repayment_periods-hidden","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"repayment_periods","property":"hidden","property_type":"Check","value":"1"},
  {"doctype":"Property Setter","name":"Loan Application-repayment_periods-default","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"repayment_periods","property":"default","property_type":"Text","value":"12"},
  {"doctype":"Property Setter","name":"Loan Application-rate_of_interest-read_only","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"rate_of_interest","property":"read_only","property_type":"Check","value":"1"},
  {"doctype":"Property Setter","name":"Loan Application-repayment_amount-read_only","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"repayment_amount","property":"read_only","property_type":"Check","value":"1"},
  {"doctype":"Property Setter","name":"Loan Application-total_payable_amount-read_only","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"total_payable_amount","property":"read_only","property_type":"Check","value":"1"},
  {"doctype":"Property Setter","name":"Loan Application-total_payable_interest-read_only","doc_type":"Loan Application","doctype_or_field":"DocField","field_name":"total_payable_interest","property":"read_only","property_type":"Check","value":"1"}
]
```

- [ ] **Step 1: Replace property_setter.json with the above (keeping existing Customer entries)**
- [ ] **Step 2: Commit**

```bash
git add dcr/fixtures/property_setter.json
git commit -m "fixtures: add LA standard field property setters"
```

---

## Task 4: Update hooks.py fixture filter

**Files:**
- Modify: `dcr/hooks.py`

Update the Custom Field filter list:
- **Remove** these 7 names:
  - `Loan Application-requested_advance_amount`
  - `Loan Application-first_autopay_description`
  - `Loan Application-custom_projected_investment`
  - `Loan Application-dcr_lending_section`
  - `Loan Application-exhibit_a_section`
  - `Loan Application-column_break_exhibit_a`
  - `Loan Application-column_break_dcr_lending`

- **Add** these 7 names:
  - `Loan Application-column_break_header`
  - `Loan Application-lending_section`
  - `Loan Application-column_break_lending`
  - `Loan Application-lending_calculations_section`
  - `Loan Application-column_break_lending_calc`
  - `Loan Application-dcr_documents_section`
  - `Loan Application-column_break_repayment`

Update the Property Setter filter list — add all new LA property setter names:
```python
["name", "in", [
    "Customer-first_name-hidden",
    "Customer-last_name-hidden",
    "Loan Application-applicant_type-hidden",
    "Loan Application-applicant_type-default",
    "Loan Application-is_term_loan-hidden",
    "Loan Application-is_secured_loan-hidden",
    "Loan Application-description-hidden",
    "Loan Application-proposed_pledges-hidden",
    "Loan Application-maximum_loan_amount-hidden",
    "Loan Application-repayment_method-hidden",
    "Loan Application-repayment_method-default",
    "Loan Application-repayment_periods-hidden",
    "Loan Application-repayment_periods-default",
    "Loan Application-rate_of_interest-read_only",
    "Loan Application-repayment_amount-read_only",
    "Loan Application-total_payable_amount-read_only",
    "Loan Application-total_payable_interest-read_only",
]]
```

- [ ] **Step 1: Update Custom Field filter list**
- [ ] **Step 2: Update Property Setter filter list**
- [ ] **Step 3: Commit**

```bash
git add dcr/hooks.py
git commit -m "hooks: update fixture filters for LA restructure"
```

---

## Task 5: Add Customize Form API reorder in after_migrate

**Files:**
- Modify: `dcr/setup.py`

This is the **critical piece** that failed in v1. The `after_install` function (which doubles as `after_migrate`) must programmatically reorder ALL Loan Application fields using the Customize Form API. This runs AFTER fixture sync, so all custom fields exist and all property setters are applied.

The function also hides standard section breaks and column breaks AFTER reorder so their children (which have been moved away) aren't affected.

- [ ] **Step 1: Add the reorder function to setup.py**

```python
import frappe


def after_install():
    """Ensure DCR module definition and required groups exist."""
    if not frappe.db.exists("Module Def", "DCR"):
        frappe.get_doc({
            "doctype": "Module Def",
            "module_name": "DCR",
            "app_name": "dcr",
        }).insert(ignore_permissions=True)

    # Supplier Groups
    for group_name in ("Escrow", "Factory"):
        if not frappe.db.exists("Supplier Group", group_name):
            frappe.get_doc({
                "doctype": "Supplier Group",
                "supplier_group_name": group_name,
            }).insert(ignore_permissions=True)

    # Customer Groups
    for group_name in ("Home Buyer", "Dealer"):
        if not frappe.db.exists("Customer Group", group_name):
            frappe.get_doc({
                "doctype": "Customer Group",
                "customer_group_name": group_name,
            }).insert(ignore_permissions=True)

    reorder_loan_application_fields()

    frappe.db.commit()


def reorder_loan_application_fields():
    """Reorder ALL Loan Application fields into the definitive spec order.

    Uses Customize Form API so the order is enforced every deploy,
    regardless of how fixture sync placed things.

    Also hides standard section/column breaks that are no longer needed
    (safe to do here because their children have been moved to custom sections).
    """
    # Definitive field order — every field on the form, in exact spec order.
    # Visible fields first, then hidden standard fields at the end.
    FIELD_ORDER = [
        # --- Section 1: Header (no label) ---
        "applicant_type",        # standard, hidden, default "Customer"
        "applicant",             # standard
        "applicant_name",        # standard
        "column_break_header",   # custom (NEW)
        "posting_date",          # standard
        "status",                # standard

        # --- Section 2: Deal reference ---
        "deal_reference_section",  # custom
        "home_build_request",      # custom
        "home_type",               # custom
        "column_break_deal_ref",   # custom
        "factory",                 # custom

        # --- Section 3: Lending ---
        "lending_section",         # custom (NEW, replaces dcr_lending_section)
        "loan_product",            # standard
        "loan_amount",             # standard
        "advance_date_requested",  # custom
        "home_serial_no",          # custom
        "quote_no",                # custom
        "floor_plan",              # custom (label: Model)
        "column_break_lending",    # custom (NEW)
        "rate_of_interest",        # standard, read_only
        "buyer_name",              # custom (label: Buyer Name)

        # --- Section 4: Lending calculations ---
        "lending_calculations_section",  # custom (NEW)
        "available_credit",              # custom
        "outstanding_loan_balance",      # custom
        "custom_current_yn",             # custom (label: Current)
        "column_break_lending_calc",     # custom (NEW)
        "monthly_interest_amount",       # custom, read_only
        "monthly_insurance_amount",      # custom
        "repayment_amount",              # standard, read_only
        "total_payable_amount",          # standard, read_only
        "total_payable_interest",        # standard, read_only

        # --- Section 5: Pre-approval letter ---
        "advance_preapproval_section",   # custom (label: Pre-approval letter)
        "custom_projected_sales_price",  # custom
        "custom_projected_equity",       # custom, read_only
        "custom_projected_ltv",          # custom, read_only
        "custom_projected_payoff",       # custom
        "column_break_preapproval",      # custom
        "custom_monthly_space_rent",     # custom, read_only
        "custom_notes",                  # custom

        # --- Section 6: Signed documents ---
        "dcr_documents_section",  # custom (NEW)
        "signed_packet",          # custom, read_only

        # --- Section 7: Repayment info ---
        "repayment_info",          # standard section
        "repayment_method",        # standard, hidden, default
        "column_break_repayment",  # custom (NEW)
        "repayment_periods",       # standard, hidden, default
        "company",                 # standard

        # --- Hidden standard fields (parked at end) ---
        "column_break_2",
        "section_break_4",
        "is_term_loan",
        "loan_security_details_section",
        "is_secured_loan",
        "column_break_7",
        "description",
        "proposed_pledges",
        "maximum_loan_amount",
        "column_break_11",
        "amended_from",
    ]

    # Standard section/column breaks to hide (only safe after reorder)
    HIDE_FIELDS = [
        "section_break_4",
        "column_break_2",
        "column_break_7",
        "loan_security_details_section",
        "column_break_11",
    ]

    customize = frappe.get_doc("Customize Form")
    customize.doc_type = "Loan Application"
    customize.fetch_to_customize()

    # Build lookup: fieldname → field row
    field_map = {f.fieldname: f for f in customize.fields}

    # Verify all expected fields exist
    missing = [fn for fn in FIELD_ORDER if fn not in field_map]
    if missing:
        print(f"  WARNING: LA reorder skipping — missing fields: {missing}")
        return

    # Reorder: place spec fields first, then any unexpected fields at the end
    ordered = [field_map[fn] for fn in FIELD_ORDER]
    remaining = [f for f in customize.fields if f.fieldname not in set(FIELD_ORDER)]
    if remaining:
        print(f"  WARNING: unexpected fields on LA (appended at end): "
              f"{[f.fieldname for f in remaining]}")

    customize.fields = ordered + remaining

    # Reassign idx values (1-based)
    for i, field in enumerate(customize.fields):
        field.idx = i + 1

    # Hide standard section/column breaks (now safe — their children moved away)
    for fn in HIDE_FIELDS:
        if fn in field_map:
            field_map[fn].hidden = 1

    try:
        customize.save_customization()
        print("  Loan Application field order updated successfully")
    except Exception as e:
        print(f"  ERROR: LA reorder failed — {e}")
        frappe.log_error("LA field reorder failed", str(e))
```

- [ ] **Step 2: Commit**

```bash
git add dcr/setup.py
git commit -m "setup: add Customize Form API reorder for LA fields"
```

---

## Task 6: Update client script with auto-calculations

**Files:**
- Modify: `dcr/public/js/loan_application.js`

Add client-side auto-calculation triggers per spec:

| Field | Formula | Trigger |
|-------|---------|---------|
| `monthly_interest_amount` | `(rate_of_interest / 100) * loan_amount / 12` | `loan_amount` or `rate_of_interest` change |
| `custom_projected_equity` | `custom_projected_sales_price - loan_amount` | `loan_amount` or `custom_projected_sales_price` change |
| `custom_projected_ltv` | `loan_amount / custom_projected_sales_price * 100` | `loan_amount` or `custom_projected_sales_price` change |

Also set `applicant_type` default on `setup` event.

- [ ] **Step 1: Add calculation handlers**

Add these event handlers inside the existing `frappe.ui.form.on('Loan Application', { ... })` block:

```javascript
frappe.ui.form.on('Loan Application', {
    setup: function(frm) {
        // Default applicant_type to Customer (hidden field)
        if (frm.is_new() && !frm.doc.applicant_type) {
            frm.set_value('applicant_type', 'Customer');
        }
    },

    refresh: function(frm) {
        // ... existing refresh code stays unchanged ...
    },

    loan_amount: function(frm) {
        calculate_monthly_interest(frm);
        calculate_preapproval_fields(frm);
    },

    rate_of_interest: function(frm) {
        calculate_monthly_interest(frm);
    },

    custom_projected_sales_price: function(frm) {
        calculate_preapproval_fields(frm);
    }
});


function calculate_monthly_interest(frm) {
    var rate = frm.doc.rate_of_interest || 0;
    var amount = frm.doc.loan_amount || 0;
    if (rate && amount) {
        frm.set_value('monthly_interest_amount', (rate / 100) * amount / 12);
    }
}


function calculate_preapproval_fields(frm) {
    var sales_price = frm.doc.custom_projected_sales_price || 0;
    var loan_amount = frm.doc.loan_amount || 0;

    if (sales_price && loan_amount) {
        frm.set_value('custom_projected_equity', sales_price - loan_amount);
        frm.set_value('custom_projected_ltv', (loan_amount / sales_price) * 100);
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add dcr/public/js/loan_application.js
git commit -m "feat: add LA client-side auto-calculations"
```

---

## Task 7: Update server-side validation

**Files:**
- Modify: `dcr/api/lending.py`

Two changes:
1. Line 81: Replace `doc.get("requested_advance_amount") or doc.get("loan_amount")` with just `doc.get("loan_amount")`
2. Lines 102-107: Replace `custom_projected_investment` with `loan_amount` in pre-approval equity/LTV calc

- [ ] **Step 1: Update validate_loan_application**

Change line 81:
```python
# Before:
requested = doc.get("requested_advance_amount") or doc.get("loan_amount") or 0
# After:
requested = doc.get("loan_amount") or 0
```

Change lines 101-107:
```python
# Before:
investment = doc.get("custom_projected_investment") or 0
sales_price = doc.get("custom_projected_sales_price") or 0
if investment and sales_price:
    doc.custom_projected_equity = sales_price - investment
    doc.custom_projected_ltv = (investment / sales_price) * 100

# After:
loan_amount = doc.get("loan_amount") or 0
sales_price = doc.get("custom_projected_sales_price") or 0
if loan_amount and sales_price:
    doc.custom_projected_equity = sales_price - loan_amount
    doc.custom_projected_ltv = (loan_amount / sales_price) * 100
```

- [ ] **Step 2: Commit**

```bash
git add dcr/api/lending.py
git commit -m "fix: use loan_amount instead of removed fields in LA validation"
```

---

## Task 8: Update print formats

**Files:**
- Modify: `dcr/dcr/print_format/exhibit_a_receipt/exhibit_a_receipt.json`
- Modify: `dcr/dcr/print_format/ach_recurring_payment_authorization/ach_recurring_payment_authorization.json`
- Modify: `dcr/dcr/print_format/advance_pre_approval/advance_pre_approval.json`

### Exhibit A Receipt
Find/replace in the HTML string:
- `doc.requested_advance_amount` → `doc.loan_amount`
  (the line: `{{ format_currency(doc.requested_advance_amount) if doc.requested_advance_amount else '$________' }}`)
  → `{{ format_currency(doc.loan_amount) if doc.loan_amount else '$________' }}`

### ACH Recurring Payment Authorization
Replace the first_autopay_description row:
- `{{ doc.first_autopay_description or '30 days after the earlier of funding of the loan or factory invoice date of the home.' }}`
  → `30 days after the earlier of funding of the loan or factory invoice date of the home.`

### Advance Pre-Approval
Find/replace in the HTML string:
- `doc.requested_advance_amount or doc.loan_amount` → `doc.loan_amount`
  (appears twice: "Projected advance amount" row and LTV calc in Sold variant)
- `doc.custom_projected_investment` → `doc.loan_amount`
  (appears once: "Projected investment" row in Spec variant)
- LTV calc in Sold variant: `doc.requested_advance_amount / hbr.selling_price` → `doc.loan_amount / hbr.selling_price`

- [ ] **Step 1: Update Exhibit A Receipt**
- [ ] **Step 2: Update ACH Authorization**
- [ ] **Step 3: Update Advance Pre-Approval**
- [ ] **Step 4: Commit**

```bash
git add dcr/dcr/print_format/
git commit -m "fix: update print formats for removed LA fields"
```

---

## Task 9: Update email helper

**Files:**
- Modify: `dcr/api/dcr_email.py`

The `send_flooring_packet_sent` function at line 185 uses `requested_advance_amount` as both a parameter name and an `extra_data` key. Rename to `loan_amount` for consistency with the field change.

- [ ] **Step 1: Update function signature and extra_data key**

```python
# Before:
def send_flooring_packet_sent(customer_name, loan_application, requested_advance_amount, factory_name, to_email, reference_name=None):
    ...
    extra_data={
        ...
        "requested_advance_amount": requested_advance_amount,
        ...
    },

# After:
def send_flooring_packet_sent(customer_name, loan_application, loan_amount, factory_name, to_email, reference_name=None):
    ...
    extra_data={
        ...
        "loan_amount": loan_amount,
        ...
    },
```

Also find any callers of this function (likely in `dcr/api/docusign.py`) and update the kwarg from `requested_advance_amount=` to `loan_amount=`.

Also check the email template `flooring-packet-sent` for the `{{ requested_advance_amount }}` variable and rename to `{{ loan_amount }}`.

- [ ] **Step 2: Update callers and email template**
- [ ] **Step 3: Commit**

```bash
git add dcr/api/dcr_email.py dcr/api/docusign.py
git commit -m "fix: rename requested_advance_amount to loan_amount in email helper"
```

---

## Post-deploy verification checklist

After deploying to Frappe Cloud:

1. Open Customize Form → Loan Application — verify all 46+ fields are in correct order
2. Create a new Loan Application:
   - Applicant Type defaults to "Customer" (hidden)
   - Applicant, Posting Date, Status in header
   - HBR link works and fetches home_type, factory, serial_no, quote_no, model, buyer_name
3. Enter loan_amount and rate_of_interest — verify monthly_interest_amount auto-calculates
4. For a Spec home_type: verify Pre-approval letter section appears, equity/LTV auto-calculate from loan_amount
5. Verify hidden fields (is_term_loan, is_secured_loan, etc.) are not visible
6. Print Exhibit A Receipt — verify it shows loan_amount not requested_advance_amount
7. Print ACH Authorization — verify autopay text is hardcoded
8. Print Advance Pre-Approval — verify it uses loan_amount for projected investment and advance amount
