# Lending UX Overhaul Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up form layouts, field naming, auto-fetch wiring, and field organization across HBR, MIFA, Loan Application, Customer, and Loan doctypes for a polished demo-ready experience.

**Architecture:** Declarative changes only — doctype JSON edits, fixture JSON updates, Python string replacements, and one data migration patch. No new Python logic. All changes are to field labels, types, ordering, visibility, and fetch_from properties.

**Tech Stack:** Frappe v15, ERPNext, Lending module, Frappe Cloud deployment

**Spec:** `docs/superpowers/specs/2026-03-20-lending-ux-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `dcr/dcr/doctype/home_build_request/home_build_request.json` | financing_type rename, broker type change, escrow financials section |
| Modify | `dcr/dcr/doctype/home_build_request/home_build_request.py` | "DCR Floored" → "Floored" |
| Modify | `dcr/dcr/doctype/mifa/mifa.json` | entity_type fetch_from, signed_mifa hidden |
| Modify | `dcr/api/sales_order_hooks.py` | "DCR Floored" → "Floored" |
| Modify | `dcr/tests/test_required_docs.py` | "DCR Floored" → "Floored" |
| Modify | `dcr/fixtures/custom_field.json` | Label renames, reordering, hidden flags, fetch_from, Customer reorg, Loan reorg |
| Modify | `dcr/dcr/print_format/new_home_info_sheet/new_home_info_sheet.json` | broker Link field fix |
| Create | `dcr/patches/rename_dcr_floored.py` | Data migration patch |
| Modify | `dcr/patches.txt` | Register patch |

---

## Chunk 1: "DCR Floored" → "Floored" Rename

### Task 1: Rename in HBR Doctype JSON

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`

- [ ] **Step 1: Update `financing_type` options**

In `home_build_request.json`, find the `financing_type` field and change options:

```json
"options": "\nCash\nDCR Floored"
```
→
```json
"options": "\nCash\nFloored"
```

- [ ] **Step 2: Update `loan_application` depends_on**

Find the `loan_application` field and change depends_on:

```json
"depends_on": "eval:doc.financing_type=='DCR Floored'"
```
→
```json
"depends_on": "eval:doc.financing_type=='Floored'"
```

- [ ] **Step 3: Commit**

```bash
git add dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "refactor: rename DCR Floored to Floored in HBR doctype"
```

---

### Task 2: Rename in Python Code

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.py`
- Modify: `dcr/api/sales_order_hooks.py`

- [ ] **Step 1: Update home_build_request.py**

Replace all occurrences of `"DCR Floored"` with `"Floored"` in `home_build_request.py`. There are 5 occurrences — in the `REQUIRED_DOCS` lookup table keys (lines 15, 19, 31, 36) and in the `validate` method (line 45).

- [ ] **Step 2: Update sales_order_hooks.py**

Replace all occurrences of `"DCR Floored"` with `"Floored"` in `sales_order_hooks.py`. There are references on lines 4 (docstring), 13 (comment), and 15 (comparison).

- [ ] **Step 3: Commit**

```bash
git add dcr/dcr/doctype/home_build_request/home_build_request.py dcr/api/sales_order_hooks.py
git commit -m "refactor: rename DCR Floored to Floored in Python code"
```

---

### Task 3: Update Tests

**Files:**
- Modify: `dcr/tests/test_required_docs.py`

- [ ] **Step 1: Replace all `"DCR Floored"` with `"Floored"`**

There are 5 occurrences on lines 35, 44, 77, 89, 112.

- [ ] **Step 2: Run tests**

```bash
cd /Users/tristanfleming/Documents/Code/DCR && python -m pytest dcr/tests/test_required_docs.py -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add dcr/tests/test_required_docs.py
git commit -m "test: update tests for Floored rename"
```

---

### Task 4: Data Migration Patch

**Files:**
- Create: `dcr/patches/rename_dcr_floored.py`
- Modify: `dcr/patches.txt`

- [ ] **Step 1: Create the patches directory if needed**

```bash
ls dcr/patches/ 2>/dev/null || mkdir -p dcr/patches && touch dcr/patches/__init__.py
```

- [ ] **Step 2: Create `dcr/patches/rename_dcr_floored.py`**

```python
import frappe


def execute():
    """Rename 'DCR Floored' to 'Floored' in all affected doctypes."""
    # Table names are hardcoded constants, not user input
    for dt in ("Home Build Request", "Sales Order"):
        frappe.db.sql(
            """UPDATE `tab{dt}` SET financing_type = 'Floored'
            WHERE financing_type = 'DCR Floored'""".format(dt=dt)
        )
    frappe.db.commit()
```

- [ ] **Step 3: Register in patches.txt**

Add this line to `dcr/patches.txt`:

```
dcr.patches.rename_dcr_floored
```

- [ ] **Step 4: Commit**

```bash
git add dcr/patches/
git commit -m "feat: add data migration patch for DCR Floored → Floored"
```

---

## Chunk 2: "DCR" Label Cleanup in Custom Fields

### Task 5: Rename DCR-Prefixed Labels

**Files:**
- Modify: `dcr/fixtures/custom_field.json`

- [ ] **Step 1: Update labels**

Find and replace these labels in `custom_field.json`:

| name | Current `"label"` | New `"label"` |
|------|------------------|--------------|
| `Customer-dcr_application_section` | `"DCR Application"` | `"Application"` |
| `Customer-dcr_application_status` | `"DCR Application Status"` | `"Application Status"` |
| `Customer-dcr_account_no` | `"DCR Account No"` | `"Account No"` |
| `Loan Application-dcr_lending_section` | `"DCR Lending"` | `"Lending"` |
| `Loan Application-dcr_documents_section` | `"DCR Documents"` | `"Documents"` |

- [ ] **Step 2: Commit**

```bash
git add dcr/fixtures/custom_field.json
git commit -m "refactor: remove DCR prefix from custom field labels"
```

---

## Chunk 3: HBR Form Refinements

### Task 6: Change broker Field Type and Add Escrow Financials Section

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`

- [ ] **Step 1: Change broker from Data to Link**

Find the `broker` field definition in `home_build_request.json`:

```json
{
 "fieldname": "broker",
 "fieldtype": "Data",
 "label": "Broker"
}
```

Change to:

```json
{
 "fieldname": "broker",
 "fieldtype": "Link",
 "label": "Broker",
 "options": "Supplier"
}
```

- [ ] **Step 2: Add escrow_financials_section to field_order**

In the `field_order` array, insert `"escrow_financials_section"` between `"escrow_phone"` and `"customer_deposit"`:

Current:
```json
"escrow_phone",
"customer_deposit",
```

New:
```json
"escrow_phone",
"escrow_financials_section",
"customer_deposit",
```

- [ ] **Step 3: Add escrow_financials_section field definition**

In the `fields` array, add this field definition after the `escrow_phone` field object:

```json
{
 "fieldname": "escrow_financials_section",
 "fieldtype": "Section Break",
 "label": "Financials"
}
```

- [ ] **Step 4: Commit**

```bash
git add dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "refactor: broker to Link, add Escrow Financials section to HBR"
```

---

### Task 7: Fix Print Format for broker Link Field

**Files:**
- Modify: `dcr/dcr/print_format/new_home_info_sheet/new_home_info_sheet.json`

- [ ] **Step 1: Update broker reference in Jinja HTML**

In the print format HTML (line 11, inside the `html` field), find:

```
{{ doc.broker or '' }}
```

Replace with:

```
{{ frappe.db.get_value("Supplier", doc.broker, "supplier_name") if doc.broker else '' }}
```

- [ ] **Step 2: Commit**

```bash
git add dcr/dcr/print_format/new_home_info_sheet/new_home_info_sheet.json
git commit -m "fix: resolve broker supplier name in print format after Link type change"
```

---

## Chunk 4: MIFA Form Changes

### Task 8: Add fetch_from and Hide signed_mifa

**Files:**
- Modify: `dcr/dcr/doctype/mifa/mifa.json`

- [ ] **Step 1: Add fetch_from to entity_type**

Find the `entity_type` field definition in `mifa.json`:

```json
{
 "fieldname": "entity_type",
 "fieldtype": "Select",
 "label": "Entity Type",
 "options": "\nLLC\nCorporation\nPartnership\nTrust",
 "description": "Can also be fetched from Customer.entity_type"
}
```

Add `fetch_from` and update description:

```json
{
 "fieldname": "entity_type",
 "fieldtype": "Select",
 "label": "Entity Type",
 "options": "\nLLC\nCorporation\nPartnership\nTrust",
 "fetch_from": "customer.entity_type"
}
```

- [ ] **Step 2: Hide signed_mifa**

Find the `signed_mifa` field definition:

```json
{
 "fieldname": "signed_mifa",
 "fieldtype": "Attach",
 "label": "Signed MIFA",
 "description": "Populated by DocuSign webhook"
}
```

Add `"hidden": 1`:

```json
{
 "fieldname": "signed_mifa",
 "fieldtype": "Attach",
 "label": "Signed MIFA",
 "description": "Populated by DocuSign webhook",
 "hidden": 1
}
```

- [ ] **Step 3: Commit**

```bash
git add dcr/dcr/doctype/mifa/mifa.json
git commit -m "refactor: add entity_type fetch_from, hide signed_mifa on MIFA"
```

---

## Chunk 5: Loan Application Custom Fields — Reorder and Cleanup

### Task 9: Reorder Sections and Add fetch_from / Hidden / Collapsible

**Files:**
- Modify: `dcr/fixtures/custom_field.json`

All changes are to existing entries in the Loan Application section of `custom_field.json`.

- [ ] **Step 1: Add fetch_from and read_only to home_type**

Find `Loan Application-home_type` and add:

```json
"fetch_from": "home_build_request.home_type",
"read_only": 1
```

- [ ] **Step 2: Reorder Exhibit A section — move up**

Find `Loan Application-exhibit_a_section` and change:

```json
"insert_after": "doc_checklist"
```
→
```json
"insert_after": "available_credit"
```

- [ ] **Step 3: Reorder Documents section — move down**

Find `Loan Application-dcr_documents_section` and change:

```json
"insert_after": "signed_packet"
```
→
```json
"insert_after": "custom_notes"
```

- [ ] **Step 4: Move signed_packet and hide it**

Find `Loan Application-signed_packet` and change:

```json
"insert_after": "available_credit"
```
→
```json
"insert_after": "doc_checklist",
"hidden": 1
```

- [ ] **Step 5: Make Advance Pre-Approval collapsible**

Find `Loan Application-advance_preapproval_section` and add:

```json
"collapsible": 1
```

- [ ] **Step 6: Commit**

```bash
git add dcr/fixtures/custom_field.json
git commit -m "refactor: reorder Loan Application sections, add fetch_from, hide signed_packet"
```

---

## Chunk 6: Customer (Dealer) Custom Fields — Reorganization

### Task 10: Reorganize Customer Sections

**Files:**
- Modify: `dcr/fixtures/custom_field.json`

This task reorganizes the Customer custom fields into 4 logical sections: Dealer Information, Application, Dealer Documents (new, collapsible), and Dealer Agreement.

**Target chain after all changes:**

```
Dealer Information section (after customer_details) — no change
  dealer_license_no — no change
  license_expiry_date — no change
  sellers_permit_no — no change
  column_break_dealer1 (after sellers_permit_no) — no change
  entity_type (after column_break_dealer1) — MOVED from Dealer Agreement
  w9_status (after entity_type) — CHANGED from column_break_dealer1

Application section (after w9_status) — CHANGED from master_dealer_list_updated
  dcr_application_status — no change
  dcr_account_no — no change
  column_break_dcr1 (after dcr_account_no) — no change
  dealer_agreement_status (after column_break_dcr1) — CHANGED from mifa_required
  master_dealer_list_updated (after dealer_agreement_status) — no change
  mifa_required (after master_dealer_list_updated) — CHANGED from w9_status

Dealer Documents section (after mifa_required) — NEW
  dealer_license_copy (after dealer_documents_section) — CHANGED from column_break_dcr1
  sellers_permit_copy (after dealer_license_copy) — no change
  column_break_dealer_docs (after sellers_permit_copy) — NEW
  w9_copy (after column_break_dealer_docs) — CHANGED from sellers_permit_copy
  retailer_application_copy (after w9_copy) — no change

Dealer Agreement section (after retailer_application_copy) — no change
  rebate_percentage — no change
  (entity_type removed — moved to Dealer Information)
```

- [ ] **Step 1: Move entity_type to Dealer Information right column**

Find `Customer-entity_type` and change `insert_after`:
`"rebate_percentage"` → `"column_break_dealer1"`

- [ ] **Step 2: Update w9_status to follow entity_type**

Find `Customer-w9_status` and change `insert_after`:
`"column_break_dealer1"` → `"entity_type"`

- [ ] **Step 3: Update dcr_application_section to follow w9_status**

Find `Customer-dcr_application_section` and change `insert_after`:
`"master_dealer_list_updated"` → `"w9_status"`

- [ ] **Step 4: Move dealer_agreement_status to Application right column**

Find `Customer-dealer_agreement_status` and change `insert_after`:
`"mifa_required"` → `"column_break_dcr1"`

- [ ] **Step 5: Move mifa_required to after master_dealer_list_updated**

Find `Customer-mifa_required` and change `insert_after`:
`"w9_status"` → `"master_dealer_list_updated"`

Note: `Customer-master_dealer_list_updated` stays `insert_after: "dealer_agreement_status"` — no change needed.

- [ ] **Step 6: Create Dealer Documents section break**

Add a new entry to `custom_field.json`:

```json
{
  "doctype": "Custom Field",
  "name": "Customer-dealer_documents_section",
  "dt": "Customer",
  "fieldname": "dealer_documents_section",
  "fieldtype": "Section Break",
  "label": "Dealer Documents",
  "insert_after": "mifa_required",
  "depends_on": "eval:doc.customer_group=='Dealer'",
  "collapsible": 1
}
```

- [ ] **Step 7: Move document attachments under Dealer Documents**

Update `Customer-dealer_license_copy` `insert_after`:
`"column_break_dcr1"` → `"dealer_documents_section"`

Add a new column break for the documents right column:

```json
{
  "doctype": "Custom Field",
  "name": "Customer-column_break_dealer_docs",
  "dt": "Customer",
  "fieldname": "column_break_dealer_docs",
  "fieldtype": "Column Break",
  "insert_after": "sellers_permit_copy"
}
```

Update `Customer-w9_copy` `insert_after`:
`"sellers_permit_copy"` → `"column_break_dealer_docs"`

Note: `Customer-retailer_application_copy` stays `insert_after: "w9_copy"` — no change needed.

- [ ] **Step 9: Commit**

```bash
git add dcr/fixtures/custom_field.json
git commit -m "refactor: reorganize Customer dealer sections into logical groups"
```

---

## Chunk 7: Loan Custom Fields — Payoff Simplification

### Task 11: Simplify Payoff Section and Make Rebate Collapsible

**Files:**
- Modify: `dcr/fixtures/custom_field.json`

- [ ] **Step 1: Reorder Payoff fields to 2 columns**

Left column (dates + amounts owed):

`Loan-interest_owed_at_payoff` — change:
```json
"insert_after": "column_break_payoff1"
```
→
```json
"insert_after": "payoff_good_thru_date"
```

`Loan-insurance_at_payoff` — change:
```json
"insert_after": "service_fee_amount"
```
→
```json
"insert_after": "interest_owed_at_payoff"
```

`Loan-column_break_payoff1` — change:
```json
"insert_after": "payoff_good_thru_date"
```
→
```json
"insert_after": "insurance_at_payoff"
```

Right column (amounts collected):

`Loan-late_fees_collected` — change:
```json
"insert_after": "interest_owed_at_payoff"
```
→
```json
"insert_after": "column_break_payoff1"
```

`Loan-service_fee_amount` — change:
```json
"insert_after": "late_fees_collected"
```
(no change — already correct)

`Loan-principal_collected` — change:
```json
"insert_after": "column_break_payoff2"
```
→
```json
"insert_after": "service_fee_amount"
```

`Loan-paid_from_escrow` — change:
```json
"insert_after": "principal_collected"
```
(no change — already correct)

- [ ] **Step 2: Remove column_break_payoff2**

Delete the entire `Loan-column_break_payoff2` entry from `custom_field.json`.

- [ ] **Step 3: Make Rebate section collapsible**

Find `Loan-rebate_section` and add:

```json
"collapsible": 1
```

- [ ] **Step 4: Commit**

```bash
git add dcr/fixtures/custom_field.json
git commit -m "refactor: simplify Loan payoff to 2 columns, make rebate collapsible"
```

---

## Chunk 8: Final Verification

### Task 12: Run All Tests and Verify

- [ ] **Step 1: Run the full test suite**

```bash
cd /Users/tristanfleming/Documents/Code/DCR && python -m pytest dcr/tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Verify JSON validity**

```bash
python -c "import json; json.load(open('dcr/fixtures/custom_field.json')); print('custom_field.json: valid')"
python -c "import json; json.load(open('dcr/dcr/doctype/home_build_request/home_build_request.json')); print('HBR json: valid')"
python -c "import json; json.load(open('dcr/dcr/doctype/mifa/mifa.json')); print('MIFA json: valid')"
python -c "import json; json.load(open('dcr/dcr/print_format/new_home_info_sheet/new_home_info_sheet.json')); print('Print format json: valid')"
```

Expected: All files valid.

- [ ] **Step 3: Verify no remaining "DCR Floored" references**

```bash
grep -r "DCR Floored" dcr/ --include="*.py" --include="*.json" --include="*.txt"
```

Expected: No output (zero matches).

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git status
```

If clean, no action needed. If fixes were made, commit them.

---

## Notes

### Deployment
- Push to GitHub → deploy via Frappe Cloud dashboard
- `bench migrate` runs automatically, which will:
  - Apply the `rename_dcr_floored` patch (updates existing data)
  - Sync custom fields from `custom_field.json` (applies label changes, reordering, hidden flags)
  - Sync doctype changes from JSON files

### Rollback
- All changes are in version control — revert the commit(s) and redeploy
- The data migration patch is idempotent (running it twice is harmless — the WHERE clause won't match anything on second run)

### broker Data Migration
- If production has existing free-text broker values, they will become invalid Link references
- Clear them manually or add a step to the patch if needed
- If no production data has broker values populated, no action needed
