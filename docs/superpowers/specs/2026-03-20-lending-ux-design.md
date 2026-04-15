# Lending UX Overhaul — Design Spec

**Date:** 2026-03-20
**Goal:** Clean up form layouts, field naming, and auto-fetch wiring to create a polished, demo-ready experience.
**Audience:** Dealers, internal ops, investors — must look professional and work intuitively.

---

## 1. "DCR" Naming Cleanup

All changes are label-only — fieldnames stay the same in the database.

### Custom Fields (fixtures/custom_field.json)

| Field Name | Current Label | New Label |
|------------|--------------|-----------|
| `Customer-dcr_application_section` | "DCR Application" | "Application" |
| `Customer-dcr_application_status` | "DCR Application Status" | "Application Status" |
| `Customer-dcr_account_no` | "DCR Account No" | "Account No" |
| `Loan Application-dcr_lending_section` | "DCR Lending" | "Lending" |
| `Loan Application-dcr_documents_section` | "DCR Documents" | "Documents" |

### HBR Doctype (home_build_request.json)

| Change | Current | New |
|--------|---------|-----|
| `financing_type` options | `\nCash\nDCR Floored` | `\nCash\nFloored` |
| `loan_application` depends_on | `eval:doc.financing_type=='DCR Floored'` | `eval:doc.financing_type=='Floored'` |

### Python Code Updates

Every reference to `"DCR Floored"` must change to `"Floored"`:

| File | Lines | Change |
|------|-------|--------|
| `dcr/dcr/doctype/home_build_request/home_build_request.py` | 15, 19, 31, 36, 45 | String literal `"DCR Floored"` → `"Floored"` |
| `dcr/api/sales_order_hooks.py` | 4, 13, 15 | String literal + comments `"DCR Floored"` → `"Floored"` |
| `dcr/tests/test_required_docs.py` | 35, 44, 77, 89, 112 | String literal `"DCR Floored"` → `"Floored"` |

### Data Migration

Existing records with `financing_type = "DCR Floored"` need updating. Add a one-time patch:

```python
# dcr/patches/rename_dcr_floored.py
import frappe

def execute():
    """Rename 'DCR Floored' to 'Floored' in all affected doctypes."""
    for dt in ("Home Build Request", "Sales Order"):
        frappe.db.sql("""
            UPDATE `tab{dt}` SET financing_type = 'Floored'
            WHERE financing_type = 'DCR Floored'
        """.format(dt=dt))
    frappe.db.commit()
```

Register in `patches.txt`.

---

## 2. Home Build Request — Form Reorganization

The form already has the right sections and field order from the missing-fields plan. The changes here are refinements:

### Field Type Change

| Field | Current Type | New Type | Options |
|-------|-------------|----------|---------|
| `broker` | Data | Link | Supplier |

**Data migration note:** Any existing HBR records with free-text broker values will become invalid Link references. The data migration patch (Section 1) should clear these values, or they should be manually re-linked after deployment. If no production data has broker values populated yet, no migration is needed.

**Print format impact:** The `new_home_info_sheet` print format references `doc.broker` directly. After changing to a Link field, this will output the Supplier ID instead of the name. Update the print format to use `frappe.db.get_value("Supplier", doc.broker, "supplier_name")` or the `broker.supplier_name` pattern.

### Escrow Section — Add Financials Sub-Section

Currently `customer_deposit`, `selling_price`, `end_buyer_lender` sit in the Escrow section after a column break. Add an explicit `escrow_financials_section` Section Break before them with label "Financials" to visually separate escrow contact info from money fields. No `depends_on` needed — the parent escrow section already handles visibility.

Updated `field_order` for the escrow area:
```
escrow_section
escrow_company, escrow_number
column_break_escrow
escrow_contact, escrow_phone
escrow_financials_section        ← NEW
customer_deposit, selling_price
column_break_escrow2
end_buyer_lender
```

### No Other Field Order Changes

The current top-to-bottom flow (Primary → References → Park → Buyer → Escrow → Broker → Home Info → Documents) already matches the FigJam flow. No reordering needed.

---

## 3. Loan Application Custom Fields — Reorganization

### Section Renames (covered in Section 1)

- "DCR Lending" → "Lending"
- "DCR Documents" → "Documents"

### fetch_from Additions

Add `fetch_from` to the `home_type` field on Loan Application so it auto-populates when `home_build_request` is selected:

| Field | fetch_from | read_only |
|-------|-----------|-----------|
| `Loan Application-home_type` | `home_build_request.home_type` | 1 |

The field already exists with options `\nSpec\nCustomer Sold`. Adding `fetch_from` and `read_only` means it fills automatically and can't be manually overridden.

### Section Ordering

Current order in fixtures (by `insert_after` chain):
1. `home_build_request` (after `applicant_name`)
2. `home_type` (after `home_build_request`)
3. Lending section: advance amounts, balance, credit
4. `signed_packet` (after `available_credit`)
5. Documents section: doc_checklist
6. Exhibit A / ACH section
7. Advance Pre-Approval section

**Problem:** `signed_packet` sits between Lending and Documents — it should be hidden (see Section 4). The Exhibit A section comes after Documents, which is unintuitive.

**New order** (via `insert_after` adjustments):
1. `home_build_request` + `home_type`
2. Lending section (advance amounts, balance, credit)
3. Exhibit A / ACH section
4. Advance Pre-Approval section (add `"collapsible": 1` to `advance_preapproval_section`)
5. Documents section (doc_checklist)
6. `signed_packet` (hidden)

Changes to `insert_after` values:
- `Loan Application-exhibit_a_section`: change `insert_after` from `"doc_checklist"` to `"available_credit"`
- `Loan Application-advance_preapproval_section`: keep as-is (already after `first_autopay_description`)
- `Loan Application-dcr_documents_section`: change `insert_after` from `"signed_packet"` to `"custom_notes"`
- `Loan Application-signed_packet`: change `insert_after` from `"available_credit"` to `"doc_checklist"`, add `"hidden": 1`

---

## 4. Hidden Fields (DocuSign-Populated)

These fields exist on the record but are hidden from the form. Signed documents are accessible via the Attachments sidebar.

| Field | Doctype | Change |
|-------|---------|--------|
| `Loan Application-signed_packet` | Loan Application | Add `"hidden": 1` |
| `signed_mifa` | MIFA | Add `"hidden": 1` |

For MIFA, keep the "Signature" section since `dealer_signer_title` is user-entered. Only hide `signed_mifa` within it.

---

## 5. Customer (Dealer) Custom Fields — Reorganization

The Customer form has 3 custom sections for dealers. The current layout mixes concerns — document attachments sit in the "Application" section, agreement status is separated from the Dealer Agreement section, and operational checkboxes are mixed with license info.

### Current Layout

1. **Dealer Information**: license no, expiry, seller's permit | W-9 status, MIFA required, agreement status, master dealer list updated
2. **Application** (was "DCR Application"): application status, account no | license copy, permit copy, W-9 copy, retailer app copy
3. **Dealer Agreement**: rebate percentage, entity type

### New Layout

Reorganize into 4 logically grouped sections:

1. **Dealer Information** — license/permit details (unchanged)
   - `dealer_license_no`, `license_expiry_date`, `sellers_permit_no` (left)
   - `entity_type` (move here from Dealer Agreement), `w9_status` (right)

2. **Application** — onboarding status tracking
   - `dcr_application_status`, `dcr_account_no` (left)
   - `dealer_agreement_status` (move here from Dealer Information), `mifa_required`, `master_dealer_list_updated` (right)

3. **Dealer Documents** (renamed from attachments mixed into Application) — collapsible
   - `dealer_license_copy`, `sellers_permit_copy` (left)
   - `w9_copy`, `retailer_application_copy` (right)

4. **Dealer Agreement** — financial terms
   - `rebate_percentage` (left)
   - (entity_type moved to section 1)

### Changes to `insert_after` values

- `Customer-dealer_agreement_status`: move from after `mifa_required` to after `dcr_account_no` (into Application section, right column)
- `Customer-master_dealer_list_updated`: move to after `dealer_agreement_status`
- `Customer-mifa_required`: move to after `master_dealer_list_updated`
- `Customer-entity_type`: move from Dealer Agreement section to after `sellers_permit_no` (into Dealer Information, right column — swap with `w9_status` position)
- Rename the Application section's right-column area to hold document copies under a new **Dealer Documents** collapsible section break, inserted after `mifa_required`
- `Customer-dealer_license_copy` through `Customer-retailer_application_copy`: move `insert_after` chain to follow the new Dealer Documents section break

---

## 6. Loan Custom Fields — Reorganization

The Loan form has 4 custom sections. The Payoff section uses 3 column breaks for 8 currency fields which feels cramped. The Home/Deal Reference fields have no fetch_from.

### Current Layout

1. **ACH Payment** (collapsible): `ach_payment_account`
2. **Home / Deal Reference**: serial no, buyer name | factory
3. **Payoff**: payoff date, good thru date | interest owed, late fees, service fees, insurance | principal collected, paid from escrow
4. **Rebate**: qualifying amount, rebate percentage

### Changes

**Payoff section — simplify to 2 columns:**

Column 1 (dates + amounts owed):
- `payoff_date`, `payoff_good_thru_date`, `interest_owed_at_payoff`, `insurance_at_payoff`

Column 2 (amounts collected):
- `late_fees_collected`, `service_fee_amount`, `principal_collected`, `paid_from_escrow`

Remove `column_break_payoff2` — go from 3 columns to 2.

Changes to `insert_after`:
- `Loan-insurance_at_payoff`: change from after `service_fee_amount` to after `interest_owed_at_payoff`
- `Loan-column_break_payoff1`: keep as-is (after `insurance_at_payoff` — wait, needs adjustment)
- Reorder: `payoff_date` → `payoff_good_thru_date` → `interest_owed_at_payoff` → `insurance_at_payoff` → `column_break_payoff1` → `late_fees_collected` → `service_fee_amount` → `principal_collected` → `paid_from_escrow`
- Delete `Loan-column_break_payoff2` from fixtures

**Rebate section — make collapsible:**
- Add `"collapsible": 1` to `Loan-rebate_section`

### No fetch_from additions for Loan

The `factory` and `buyer_name` fields on Loan are reference data that may be entered independently of the Loan Application (e.g., copied from HBR at loan booking time via Python). Adding `fetch_from` here would require a Link to Loan Application on the Loan doctype, which doesn't exist as a custom field. Leave as manual/programmatic for now.

---

## 7. fetch_from Additions

### MIFA → Customer

| MIFA Field | fetch_from | Behavior |
|------------|-----------|----------|
| `entity_type` | `customer.entity_type` | Auto-fills when customer is selected. Not read-only — can be overridden if the MIFA entity differs from the Customer record. |

### Loan Application → HBR

| Loan App Field | fetch_from | Behavior |
|----------------|-----------|----------|
| `home_type` | `home_build_request.home_type` | Auto-fills, read-only |

---

## 8. Summary of Files Changed

| File | Type of Change |
|------|---------------|
| `dcr/fixtures/custom_field.json` | Label renames, insert_after reordering, hidden flags, fetch_from additions |
| `dcr/dcr/doctype/home_build_request/home_build_request.json` | `financing_type` options, `loan_application` depends_on, `broker` field type, `escrow_financials_section` addition |
| `dcr/dcr/doctype/mifa/mifa.json` | `entity_type` fetch_from, `signed_mifa` hidden |
| `dcr/dcr/doctype/home_build_request/home_build_request.py` | `"DCR Floored"` → `"Floored"` |
| `dcr/api/sales_order_hooks.py` | `"DCR Floored"` → `"Floored"` |
| `dcr/tests/test_required_docs.py` | `"DCR Floored"` → `"Floored"` |
| `dcr/patches/rename_dcr_floored.py` | **New** — data migration patch |
| `dcr/patches.txt` | Register new patch |
| `dcr/dcr/print_format/new_home_info_sheet/new_home_info_sheet.json` | Update `doc.broker` reference for Link field |

---

## 9. What This Does NOT Cover

- Other workspaces (Home, Contacts, Accounting, Users) — future work
- Client scripts for guided workflows or custom buttons
- Dashboard widgets on forms
- Print format changes beyond the broker field fix
