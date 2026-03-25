# DCR Deal Hub Design Spec

**Date:** 2026-03-25
**Status:** Draft
**Scope:** DCR app only (emails app deferred)

## Architecture Principle

Data lives in one place. Everything else fetches from it.

| Layer | Doctype | Role |
|-------|---------|------|
| Reference | Park, Model, Loan Product | Rarely changes. Reused across deals. |
| Dealer Hub | Customer | Dealer identity, docs, agreement status, entity type. |
| Deal Hub | Home Build Request | Single source of truth for all deal data. |
| Downstream | SQ, LA, Loan, Loan Disbursement | Created from the hub. Fields fetch_from hub or parent. Read-only. |

**Writeback exception:** Supplier Quotation writes `home_serial_no` and `quote_no` back to HBR on save. These fields originate at the factory and enter the system via SQ.

---

## Section 1: HBR — New Fields & Data Model

### New fields on HBR

| Field | Fieldtype | Options | Notes |
|-------|-----------|---------|-------|
| `home_serial_no` | Data | unique, not mandatory | Factory assigns. Writeback from SQ. |
| `quote_no` | Data | | Factory order confirmation. Writeback from SQ. |

### home_invoice_plus_freight behavior

- Editable until `factory_quote` (SQ link) is populated
- `read_only_depends_on: eval:doc.factory_quote` makes it read-only once SQ exists
- Remains the source for LA `requested_advance_amount` via fetch_from

### Park fetch_from fields on HBR

All read_only, surfaced when Park is selected:

| HBR Field | fetch_from |
|-----------|------------|
| `park_address_line1` | `park.address_line1` |
| `park_address_line2` | `park.address_line2` |
| `park_city` | `park.city` |
| `park_state` | `park.state` |
| `park_zip` | `park.zip` |
| `park_contact_name` | `park.contact_name` |
| `park_phone` | `park.office_phone` |
| `park_gated` | `park.gated` |
| `park_access_code` | `park.access_code` |

### Factory field filter

Client-side `set_query` on `factory` field: only show Suppliers where an approved Factory Assignment exists for `doc.customer`.

Query logic:
```
Factory Assignment WHERE customer = doc.customer
  AND docstatus = 1
  AND active = 1
→ return distinct factory values
```

### Section visibility

- Escrow section: `depends_on: eval:doc.home_type=='Customer Sold'`
- Broker section: `depends_on: eval:doc.home_type=='Customer Sold'`
- Buyer section: `depends_on: eval:doc.home_type=='Customer Sold'` (already done)

---

## Section 2: Park Doctype Cleanup

### Address field split

Replace `address` + `city_state_zip` with:

| Field | Fieldtype | Notes |
|-------|-----------|-------|
| `address_line1` | Data | Replaces `address` |
| `address_line2` | Data | New |
| `city` | Data | Split from `city_state_zip` |
| `state` | Data | Split from `city_state_zip` |
| `zip` | Data | Split from `city_state_zip` |

Existing fields kept: `park_name`, `office_phone`, `contact_name`, `gated`, `access_code`.

### Quick entry

`quick_entry: 1` in Park doctype JSON. Fields shown: park_name, address_line1, city, state, zip, office_phone, contact_name.

### Data migration

Patch to split existing `city_state_zip` values:
- Pattern: "City, ST ZIP" (e.g., "Riverside, CA 92501")
- Split on comma + space for city, then space-separate state and zip
- Remove old `address` and `city_state_zip` fields after migration

---

## Section 3: Supplier Quotation — New Fields & Writeback

### New custom fields on SQ

| Field | Fieldtype | Notes |
|-------|-----------|-------|
| `home_serial_no` | Data | First known from factory |
| `quote_no` | Data | Factory order confirmation number |

### Writeback to HBR

Doc event: `before_save` on Supplier Quotation (registered in hooks.py).

Logic:
```python
def on_sq_before_save(doc, method):
    if not doc.home_build_request:
        return
    hbr = frappe.get_doc("Home Build Request", doc.home_build_request)
    changed = False
    if doc.home_serial_no and hbr.home_serial_no != doc.home_serial_no:
        hbr.home_serial_no = doc.home_serial_no
        changed = True
    if doc.quote_no and hbr.quote_no != doc.quote_no:
        hbr.quote_no = doc.quote_no
        changed = True
    if changed:
        hbr.save(ignore_permissions=True)
```

Data flow: Factory info → SQ (manual entry) → HBR (writeback) → LA, Loan (fetch_from)

---

## Section 4: Downstream Fetch Chain

All downstream fields fetch from HBR or their parent record. All read_only.

### Loan Application (custom field fixture changes)

| Field | Change |
|-------|--------|
| `home_serial_no` | Add `fetch_from: home_build_request.home_serial_no`, `read_only: 1` |
| `quote_no` | Add `fetch_from: home_build_request.quote_no`, `read_only: 1` |
| `floor_plan` | No change (already `fetch_from: home_build_request.model_name`, read_only) |
| `buyer_name` | No change (already `fetch_from: home_build_request.home_buyer`) |
| `factory` | No change (already `fetch_from: home_build_request.factory`, read_only) |
| `requested_advance_amount` | No change (already `fetch_from: home_build_request.home_invoice_plus_freight`, fetch_if_empty) |

### Loan (custom field fixture changes)

| Field | Change |
|-------|--------|
| `home_build_request` | `read_only: 1`. Auto-populated from LA in `on_loan_validate` (already wired). |
| `home_serial_no` | Add `fetch_from: home_build_request.home_serial_no`, `read_only: 1` |
| `buyer_name` | Add `fetch_from: home_build_request.home_buyer`, `read_only: 1` |
| `factory` | Add `fetch_from: home_build_request.factory`, `read_only: 1` |

### Loan Disbursement

No changes needed. Already correctly wired:
- `home_build_request`: `fetch_from: against_loan.home_build_request`
- `factory`: `fetch_from: against_loan.factory`

### Python hook

`on_loan_validate` in `lending.py` already copies `home_build_request` from LA to Loan. The fetch_from declarations on Loan fields handle the rest automatically once `home_build_request` is set.

---

## Section 5: Customer & Factory Assignment

### Customer changes

**Remove:** `rebate_percentage` from custom_field fixtures. Now lives on Factory Assignment (per dealer-factory pair).

**Mandatory fields** (via fixtures, `reqd: 1`):
- `dealer_license_no`
- `entity_type`
- `default_loan_product`

**Hide Lending tab name fields:** Property setters to hide `first_name` and `last_name` standard fields that Lending adds (redundant with Contact records).

### Factory Assignment changes

**New field:**

| Field | Fieldtype | Notes |
|-------|-----------|-------|
| `rebate_percentage` | Percent | Per dealer-factory rebate rate |

**Auto-set status on submit:**
In `on_submit()`: unconditionally set `retailer_application_status = "Submitted"` before triggering the retailer application email. Remove any requirement for user to pre-select status.

**Allow multiple per dealer:**
Remove the `count === 0` check in `customer.js` that hides "Create -> Factory Assignment" after one exists.

**Quick entry:**
`quick_entry: 1` in doctype JSON. Dialog fields: customer, factory, assignment_date, rebate_percentage, letter_of_authorization.

**Dashboard link:**
Add Factory Assignment to Customer's connections panel (links config).

---

## Section 6: Mandatory Fields on Downstream Records

### Loan Application (custom field fixtures, `reqd: 1`)
- `home_build_request` (already has `link_filters: docstatus=1`)
- `requested_advance_amount`

### Loan (custom field fixtures, `reqd: 1`)
- `home_build_request` (read_only, auto-populated from LA)
- `factory` (read_only, fetch_from HBR)

### Loan Disbursement (custom field fixtures, `reqd: 1`)
- `home_build_request` (fetch_from against_loan)
- `factory` (fetch_from against_loan)
- `factory_po` — **kept optional** (may not exist at disbursement time)

Safety note: Making read_only + fetch_from fields mandatory is safe because they auto-populate. The mandatory check prevents saving if source data is missing (defensive).

---

## Section 7: HBR Form Organization

### Proposed layout

```
── Deal Info (top, always visible) ──────────────────
  Customer*          | Home Type* (Spec/Customer Sold)
  Financing Type*    | Property Type* (Park/Private)
  Status (read_only)

── Home ─────────────────────────────────────────────
  Model Name*        | Factory (filtered by FA)
  Home Serial No     | Quote No
  Home Invoice + Freight (read_only after SQ)

── Park (depends_on: property_type=='Park') ─────────
  Park (Link, quick_entry) | Space Number
  --- read_only fetch_from park ---
  Address Line 1     | Address Line 2
  City / State / Zip (3 columns)
  Contact Name       | Phone
  Gated (check)      | Access Code

── Buyer (depends_on: home_type=='Customer Sold') ───
  Home Buyer         | End Buyer Lender
  Customer Deposit   | Selling Price

── Escrow (depends_on: home_type=='Customer Sold') ──
  Escrow Company     | Escrow Number
  Escrow Contact     | Escrow Phone

── Broker (depends_on: home_type=='Customer Sold') ──
  Broker             | Broker Contact
                     | Broker Phone

── Factory Order ────────────────────────────────────
  Factory Quote (Link to SQ, read_only)
  Loan Application (Link, read_only, depends_on: Floored)

── Document Checklist ───────────────────────────────
  doc_checklist (Table)
```

### Key changes from current
- Home section consolidates model, factory, serial/quote, and invoice amount
- Park section surfaces fetched address/contact details inline
- Buyer/Escrow/Broker all hidden for Spec deals
- Factory Order section groups downstream links
- Top-to-bottom flow: what → where → who → money → docs

---

## Items Explicitly Deferred

- Emails app consolidation (separate design)
- BUG-001 welcome email (blocked on emails app)
- CC DCR on retailer application email (blocked on emails app)
- Home sections (Single/Double/Triple), sqft, beds, baths (not needed now)
- GL account configuration (needs input from DCR)
- ACHQ sandbox credentials (needs input from DCR)

---

## Summary of All Changes

| Area | Type | Count |
|------|------|-------|
| HBR new fields | JSON | 2 (home_serial_no, quote_no) + 9 park fetch_from |
| HBR form reorg | JSON | Section restructuring |
| HBR factory filter | JS | set_query in client script |
| HBR read_only logic | JSON | read_only_depends_on on home_invoice_plus_freight |
| Park address split | JSON + patch | 5 new fields, remove 2 old |
| Park quick_entry | JSON | 1 flag |
| SQ new fields | Fixtures | 2 (home_serial_no, quote_no) |
| SQ writeback | Python | before_save hook |
| LA fetch_from | Fixtures | 2 fields updated (home_serial_no, quote_no) |
| LA mandatory | Fixtures | 2 fields |
| Loan fetch_from | Fixtures | 3 fields updated + read_only on HBR link |
| Loan mandatory | Fixtures | 2 fields |
| Loan Disbursement mandatory | Fixtures | 2 fields |
| Customer remove rebate | Fixtures | 1 field removed |
| Customer mandatory | Fixtures | 3 fields |
| Customer hide lending names | Property setter | 2 fields |
| FA rebate_percentage | JSON | 1 new field |
| FA auto-status | Python | on_submit change |
| FA multiple allowed | JS | Remove count check |
| FA quick_entry | JSON | 1 flag |
| FA dashboard link | Python/JSON | Links config |
