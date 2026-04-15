# Post-Testing Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Supplier Quotation from the deal flow, consolidate data on HBR, standardize form layouts across all doctypes, simplify the document checklist, improve email UX, and restyle print format signature blocks.

**Architecture:** HBR is the single source of truth for deal data. Submission locks the record; all downstream docs (LA, Loan, PI) are created manually via Create buttons. SQ is fully removed from the flow. Custom fields on Loan Application, Loan, and Loan Disbursement fetch read-only data from HBR.

**Tech Stack:** Frappe Framework v15, ERPNext, Lending module. Changes via DocType JSON, custom_field.json fixtures, Python controllers, client-side JS.

---

## Pre-Implementation Notes

**Already implemented (skip):**
- HBR already has `home_serial_no` and `quote_no` fields (Phase 2.1 from spec)
- LA custom fields already have `fetch_from` for serial_no, quote_no, buyer_name, factory, home_type (Phase 2.2)
- Loan custom fields already have `fetch_from` for serial_no, buyer_name, factory (Phase 2.3)
- Factory filter on HBR already works via `get_assigned_factories` (Phase 4.1)
- Park address fields already split into line1/line2/city/state/zip (Phase 6.1)
- Park fetch_from fields already on HBR (Phase 4.3)
- Park already has `quick_entry: 1` (Phase 6.2)
- Factory Assignment already has `quick_entry: 1` (Phase 8.2)
- Customer.js already allows multiple Factory Assignments (Phase 8.1)
- Factory Assignment already auto-sets status on submit (Phase 8.3)
- Customer dashboard already has Factory Assignment link (Phase 8.4)
- Create → Loan Application button already exists on HBR (Phase 4.5 partial)
- Loan Disbursement `factory_po` label already says "Purchase Invoice" and options = "Purchase Invoice"

**Dependency order:** Tasks 1-4 (SQ removal + flow cleanup) → Tasks 5-8 (HBR layout) → Tasks 9-11 (other doctype layouts) → Tasks 12-14 (checklist, email, print formats). Tasks 12-14 are independent of each other.

---

### Task 1: Remove SQ auto-creation from HBR on_submit

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.py`
- Modify: `dcr/hooks.py`
- Modify: `dcr/api/lending.py`

- [ ] **Step 1: Remove SQ and LA creation methods from HBR**

Delete these methods entirely from `HomeBuildRequest` class:
- `_create_supplier_quotation()` (lines 90-145)
- `_copy_factory_quote_to_sq()` (lines 147-163)
- `_create_loan_application()` (lines 165-215)

Also delete the standalone `create_loan_application_from_hbr()` whitelisted function (lines 270-280) — LA creation now happens entirely client-side via `frappe.new_doc`.

- [ ] **Step 2: Simplify on_submit**

Replace `on_submit` with:

```python
def on_submit(self):
    """Submission locks the deal record. Downstream docs created manually."""
    pass
```

**IMPORTANT:** Keep `before_submit` intact — it calls `validate_checklist_complete()` which is the submission gate. Do NOT remove or modify it.

- [ ] **Step 3: Remove SQ doc_event from hooks.py and delete on_sq_before_save**

In `dcr/hooks.py`, remove the Supplier Quotation entry from `doc_events`:

```python
# Remove this block:
"Supplier Quotation": {
    "before_save": "dcr.api.lending.on_sq_before_save"
},
```

In `dcr/api/lending.py`, delete the `on_sq_before_save` function (lines 207-215). This function wrote `home_serial_no` and `quote_no` from SQ back to HBR. With SQ removed from the flow, these fields are now entered directly on HBR before submission.

- [ ] **Step 4: Commit**

```bash
git add dcr/dcr/doctype/home_build_request/home_build_request.py dcr/hooks.py dcr/api/lending.py
git commit -m "feat: remove SQ auto-creation from HBR submission flow"
```

---

### Task 2: Remove SQ custom fields and fixtures

**Files:**
- Modify: `dcr/fixtures/custom_field.json`
- Modify: `dcr/hooks.py`

- [ ] **Step 1: Remove SQ entries from custom_field.json**

Delete these 6 entries from `dcr/fixtures/custom_field.json` where `dt == "Supplier Quotation"`:
- `Supplier Quotation-home_build_request`
- `Supplier Quotation-plot_plan`
- `Supplier Quotation-signed_by_dealer`
- `Supplier Quotation-signature_date`
- `Supplier Quotation-home_serial_no`
- `Supplier Quotation-quote_no`

- [ ] **Step 2: Remove SQ entries from hooks.py fixtures filter**

In `dcr/hooks.py`, remove these lines from the Custom Field fixtures filter:
```python
"Supplier Quotation-home_build_request",
"Supplier Quotation-plot_plan",
"Supplier Quotation-signed_by_dealer",
"Supplier Quotation-signature_date",
"Supplier Quotation-home_serial_no",
"Supplier Quotation-quote_no",
```

- [ ] **Step 3: Remove SQ from HBR dashboard links**

In `dcr/dcr/doctype/home_build_request/home_build_request.json`, remove from the `links` array:
```json
{
  "group": "Orders",
  "link_doctype": "Supplier Quotation",
  "link_fieldname": "home_build_request"
}
```

- [ ] **Step 4: Commit**

```bash
git add dcr/fixtures/custom_field.json dcr/hooks.py dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "feat: remove Supplier Quotation custom fields and dashboard links"
```

---

### Task 3: Remove obsolete HBR fields and simplify status

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`

- [ ] **Step 1: Remove factory_quote, loan_application, and factory_order_section**

From the `fields` array in `home_build_request.json`, remove these field objects:
- `factory_quote` (Link → Supplier Quotation) — SQ is gone
- `loan_application` (Link → Loan Application) — LA is now created manually, not linked from HBR
- `factory_order_section` (Section Break, label: Factory Order)
- `column_break_factory_order` (Column Break)

**Keep `home_invoice_plus_freight`** — it holds the factory price and feeds LA `requested_advance_amount` via `fetch_from`. Label already changed to "Home Total" and `read_only_depends_on` already removed (done pre-plan). No further changes needed for this field.

Also remove these from the `field_order` array:
- `factory_order_section`
- `factory_quote`
- `column_break_factory_order`
- `loan_application`

- [ ] **Step 2: Simplify status field options**

Change the `status` field options from:
```
Draft\nDocs Pending\nReady to PO\nPO Submitted
```
To:
```
Draft\nSubmitted
```

Frappe handles Draft/Submitted via `docstatus` natively, but keeping the status field allows list view filtering. The field is `read_only` already.

- [ ] **Step 3: Update any Python references to removed fields**

In `home_build_request.py`, search for and remove:
- Any reference to `self.factory_quote`
- Any reference to `self.loan_application`

The `_create_loan_application()` method (which set `self.loan_application`) was already removed in Task 1.

- [ ] **Step 4: Update new_home_info_sheet print format**

Check `dcr/dcr/print_format/new_home_info_sheet/new_home_info_sheet.json` for references to `factory_quote`. If it references `factory_quote`, remove that reference. The `home_invoice_plus_freight` reference should still work since that field is kept.

- [ ] **Step 5: Commit**

```bash
git add dcr/dcr/doctype/home_build_request/home_build_request.json dcr/dcr/doctype/home_build_request/home_build_request.py dcr/dcr/print_format/new_home_info_sheet/
git commit -m "feat: remove obsolete HBR fields (factory_quote, SQ-era status options)"
```

---

### Task 4: Rename fields and add PI link

**Files:**
- Modify: `dcr/fixtures/custom_field.json`
- Modify: `dcr/hooks.py`

- [ ] **Step 1: Verify factory_po on Loan Disbursement (no fieldname rename)**

The `factory_po` field on Loan Disbursement already has label "Purchase Invoice" and options "Purchase Invoice" — confirmed in the current `custom_field.json`. **Do NOT rename the fieldname** from `factory_po` to `purchase_invoice` — changing a fieldname in fixtures creates a new DB column and orphans existing data. The label is already correct for users; the internal fieldname is a non-issue.

Verify: open `dcr/fixtures/custom_field.json`, find `Loan Disbursement-factory_po`, confirm label = "Purchase Invoice" and options = "Purchase Invoice". No changes needed.

- [ ] **Step 2: Rename financing_type label to "Deal type"**

In `dcr/dcr/doctype/home_build_request/home_build_request.json`, find the `financing_type` field and change:
- `"label": "Financing Type"` → `"label": "Deal type"`

The fieldname stays `financing_type`. All `depends_on` expressions use the fieldname, so no changes needed there.

- [ ] **Step 3: Add home_build_request Link field to Purchase Invoice**

In `dcr/fixtures/custom_field.json`, add a new entry:
```json
{
  "doctype": "Custom Field",
  "dt": "Purchase Invoice",
  "fieldname": "home_build_request",
  "fieldtype": "Link",
  "label": "Home Build Request",
  "name": "Purchase Invoice-home_build_request",
  "options": "Home Build Request",
  "insert_after": "supplier_name"
}
```

In `dcr/hooks.py`, add to the Custom Field fixtures filter:
```python
"Purchase Invoice-home_build_request",
```

- [ ] **Step 4: Add fetch_from for home_build_request on Loan**

In `dcr/fixtures/custom_field.json`, find `Loan-home_build_request` and add:
```json
"fetch_from": "loan_application.home_build_request"
```

This auto-populates HBR when a Loan is created from a Loan Application (standard Frappe Lending flow).

- [ ] **Step 5: Commit**

```bash
git add dcr/fixtures/custom_field.json dcr/hooks.py dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "feat: add PI link field, Loan HBR fetch_from, rename financing_type label"
```

---

### Task 5: Rearrange HBR form layout

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`

Target layout:
```
[Header]
  Customer, Status | Home Type, Deal type (financing_type), Property Type

[Deal reference]
  Factory, Model, Home Total | Serial No, Quote No

[Park] (depends: property_type == 'Park')
  Park (link), Space No
  (fetch_from fields in subsections below)

[Buyer] (depends: home_type == 'Customer Sold')
  Home Buyer (link)

[Financials] (depends: home_type == 'Customer Sold')
  Customer Deposit, Selling Price | Lender (end_buyer_lender)

[Escrow] (depends: home_type == 'Customer Sold')
  Escrow Company, Escrow Number | Escrow Contact, Escrow Phone

[Broker] (depends: home_type == 'Customer Sold', collapsible)
  Broker | Broker Contact, Broker Phone

[Document checklist]
  doc_checklist (Table)
```

- [ ] **Step 1: Rearrange header section**

Current field_order header: `customer, financing_type, status, column_break_1, home_type, property_type`

Change to: `customer, status, column_break_1, home_type, financing_type, property_type`

This puts Customer + Status on left, Home Type + Deal type + Property Type on right.

- [ ] **Step 2: Rename "Home" section to "Deal reference" and reorder**

Change `home_section` label from `"Home"` to `"Deal reference"`.

Current field_order: `model_name, home_serial_no, home_invoice_plus_freight, column_break_home, factory, quote_no`. Reorder to:

`home_section, factory, model_name, home_invoice_plus_freight, column_break_home, home_serial_no, quote_no`

This puts Factory + Model + Invoice Amount on left, Serial No + Quote No on right.

- [ ] **Step 3: Split buyer_section into Buyer and Financials**

Current `buyer_section` contains: home_buyer, customer_deposit, column_break_buyer, end_buyer_lender, selling_price.

Split into:
1. `buyer_section` — just `home_buyer` (remove customer_deposit and column_break_buyer from this section)
2. New `financials_section` (Section Break) — `customer_deposit`, `selling_price`, `column_break_financials`, `end_buyer_lender`

Add new field objects:
```json
{
  "fieldname": "financials_section",
  "fieldtype": "Section Break",
  "label": "Financials",
  "depends_on": "eval:doc.home_type=='Customer Sold'"
},
{
  "fieldname": "column_break_financials",
  "fieldtype": "Column Break"
}
```

Remove `column_break_buyer` field since buyer_section now has only one field.

Update `field_order`:
```
buyer_section, home_buyer,
financials_section, customer_deposit, selling_price, column_break_financials, end_buyer_lender
```

- [ ] **Step 4: Merge Park subsections**

Currently there are 3 Park sections: `park_section`, `park_details_section`, `park_contact_section`. The spec says to merge park details into the park section for a vertical layout. However, since these are read-only fetch_from fields, keeping them in subsections is fine for organization.

The spec says to remove the Column Break between park and space_number in the Park section. Current field_order: `park_section, park, column_break_park, space_number`. Change to: `park_section, park, space_number` (remove `column_break_park`).

Remove the `column_break_park` field object.

- [ ] **Step 5: Update full field_order array**

Set the complete `field_order` to:
```json
[
  "customer",
  "status",
  "column_break_1",
  "home_type",
  "financing_type",
  "property_type",
  "home_section",
  "factory",
  "model_name",
  "home_invoice_plus_freight",
  "column_break_home",
  "home_serial_no",
  "quote_no",
  "park_section",
  "park",
  "space_number",
  "park_details_section",
  "park_address_line1",
  "park_address_line2",
  "column_break_park_details",
  "park_city",
  "park_state",
  "park_zip",
  "park_contact_section",
  "park_contact_name",
  "park_gated",
  "column_break_park_contact",
  "park_phone",
  "park_access_code",
  "buyer_section",
  "home_buyer",
  "financials_section",
  "customer_deposit",
  "selling_price",
  "column_break_financials",
  "end_buyer_lender",
  "escrow_section",
  "escrow_company",
  "escrow_number",
  "column_break_escrow",
  "escrow_contact",
  "escrow_phone",
  "broker_section",
  "broker",
  "column_break_broker",
  "broker_contact",
  "broker_phone",
  "documents_section",
  "doc_checklist"
]
```

- [ ] **Step 6: Commit**

```bash
git add dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "feat: rearrange HBR form — 5-section layout with Deal reference"
```

---

### Task 6: Add Create buttons and dashboard links to HBR

**Files:**
- Modify: `dcr/public/js/home_build_request.js`
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`

- [ ] **Step 1: Update HBR JS with Create buttons**

Replace the `refresh` handler in `dcr/public/js/home_build_request.js`:

```javascript
refresh: function(frm) {
    // Factory filter
    if (frm.doc.customer) {
        frm.set_query('factory', function() {
            return {
                query: 'dcr.dcr.doctype.home_build_request.home_build_request.get_assigned_factories',
                filters: { customer: frm.doc.customer }
            };
        });
    }

    // Create buttons only on submitted HBR
    if (frm.doc.docstatus !== 1) return;

    // Create → Loan Application (Floored only, if none exists)
    if (frm.doc.financing_type === 'Floored') {
        frappe.db.count('Loan Application', {
            filters: { home_build_request: frm.doc.name, docstatus: ['!=', 2] }
        }).then(function(count) {
            if (count === 0) {
                frm.add_custom_button(__('Loan Application'), function() {
                    frappe.new_doc('Loan Application', {
                        applicant_type: 'Customer',
                        applicant: frm.doc.customer,
                        home_build_request: frm.doc.name
                    });
                }, __('Create'));
            }
        });
    }

    // Create → Purchase Invoice (all deals)
    frm.add_custom_button(__('Purchase Invoice'), function() {
        frappe.new_doc('Purchase Invoice', {
            supplier: frm.doc.factory,
            home_build_request: frm.doc.name
        });
    }, __('Create'));
},
```

- [ ] **Step 2: Update HBR dashboard links**

In `dcr/dcr/doctype/home_build_request/home_build_request.json`, replace the `links` array with:
```json
[
  {
    "group": "Orders",
    "link_doctype": "Purchase Invoice",
    "link_fieldname": "home_build_request"
  },
  {
    "group": "Lending",
    "link_doctype": "Loan Application",
    "link_fieldname": "home_build_request"
  },
  {
    "group": "Lending",
    "link_doctype": "Loan",
    "link_fieldname": "home_build_request"
  },
  {
    "group": "Lending",
    "link_doctype": "Loan Disbursement",
    "link_fieldname": "home_build_request"
  },
  {
    "group": "Documents",
    "link_doctype": "Signature Request",
    "link_fieldname": "reference_name"
  }
]
```

Changes: Removed SQ link. Added Purchase Invoice link. Added Loan link (was missing).

- [ ] **Step 3: Add Loan link to HBR dashboard via DocType Link fixture**

The Loan doctype needs a `home_build_request` linkable field for the dashboard to work. The custom field already exists (`Loan-home_build_request`). However, we need a DocType Link fixture for the sidebar.

In `dcr/hooks.py`, check if `"Loan-Home Build Request"` is already in the DocType Link filters. If not, there's no need — the `links` array in the HBR JSON handles the reverse direction. The `links` array tells Frappe: "on the HBR form, show linked Loans where `loan.home_build_request == this_hbr`." This already works since `Loan-home_build_request` custom field exists.

- [ ] **Step 4: Commit**

```bash
git add dcr/public/js/home_build_request.js dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "feat: add Create → PI button and update HBR dashboard links"
```

---

### Task 7: Add Financials depends_on and customer_dashboard override

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json` (if not already done in Task 5)
- Create: `dcr/overrides/customer_dashboard.py`
- Modify: `dcr/hooks.py`

- [ ] **Step 1: Verify Financials section depends_on**

Confirm that the `financials_section` created in Task 5 has `"depends_on": "eval:doc.home_type=='Customer Sold'"`. If not, add it.

- [ ] **Step 2: Create customer dashboard override**

Create `dcr/overrides/__init__.py`:
```python
```

Create `dcr/overrides/customer_dashboard.py`:
```python
from frappe import _


def get_data(data):
    data["transactions"].append({
        "label": _("DCR"),
        "items": ["Factory Assignment", "MIFA", "Home Build Request"]
    })
    return data
```

- [ ] **Step 3: Add dashboard override to hooks.py**

Add to `dcr/hooks.py`:
```python
override_doctype_dashboards = {
    "Customer": "dcr.overrides.customer_dashboard.get_data"
}
```

- [ ] **Step 4: Commit**

```bash
git add dcr/overrides/__init__.py dcr/overrides/customer_dashboard.py dcr/hooks.py dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "feat: add Customer dashboard override with DCR links"
```

---

### Task 8: Standardize LA form layout

**Files:**
- Modify: `dcr/fixtures/custom_field.json`

Target LA layout:
```
[Header — standard Lending fields]
  Applicant (default: Customer), Applicant Type | Company, Posting Date, Status

[Deal reference — DCR custom section]
  Home Build Request (link) | Home Type (RO), Factory (RO)

[Lending]
  Requested Advance Amount, Advance Date | Outstanding Balance (RO), Available Credit (RO)

[Exhibit A / ACH]
  Serial No (RO), Quote No (RO), Floor Plan (RO) | Buyer Name (RO), Monthly Interest, Monthly Insurance, First Autopay

[Advance pre-approval] (depends: eval:doc.home_type=='Spec')
  Current Y/N, Projected Investment, Projected Sales Price | Projected Equity, LTV, Monthly Space Rent, Projected Payoff
  Notes

[ERPNext — hide/default]
  Loan Product, Loan Amount, Repayment Method/Periods
```

- [ ] **Step 1: Reorder LA custom fields via insert_after**

Update `insert_after` values for LA custom fields to achieve the target layout. Key changes:

1. `home_build_request` — insert_after: `applicant_name` (already correct)
2. `home_type` — insert_after: `home_build_request` (already correct)
3. `factory` — insert_after: `home_type` (already correct)
4. Create a new Section Break for "Deal reference" if one doesn't exist. Actually, `home_build_request` is currently inserted after `applicant_name` which puts it in the header area. Add a new section break.

Add new custom field:
```json
{
  "doctype": "Custom Field",
  "dt": "Loan Application",
  "fieldname": "deal_reference_section",
  "fieldtype": "Section Break",
  "label": "Deal reference",
  "name": "Loan Application-deal_reference_section",
  "insert_after": "applicant_name"
}
```

Then update:
- `home_build_request` insert_after: `deal_reference_section`
- `home_type` insert_after: `home_build_request`

Add a Column Break after home_type for Factory:
```json
{
  "doctype": "Custom Field",
  "dt": "Loan Application",
  "fieldname": "column_break_deal_ref",
  "fieldtype": "Column Break",
  "name": "Loan Application-column_break_deal_ref",
  "insert_after": "home_type"
}
```

Then: `factory` insert_after: `column_break_deal_ref`

2. `dcr_lending_section` — insert_after: `factory` (update from current `home_type`)
3. Advance pre-approval section — add `depends_on`: `eval:doc.home_type=='Spec'`

- [ ] **Step 2: Add depends_on to advance_preapproval_section**

Update `Loan Application-advance_preapproval_section` to add:
```json
"depends_on": "eval:doc.home_type=='Spec'"
```

- [ ] **Step 3: Add buyer_name read_only**

Verify `Loan Application-buyer_name` has `"read_only": 1`. Currently it does NOT have read_only set. Add it.

- [ ] **Step 4: Add to hooks.py fixtures**

Add new field names to the Custom Field filter in hooks.py:
```python
"Loan Application-deal_reference_section",
"Loan Application-column_break_deal_ref",
```

- [ ] **Step 5: Commit**

```bash
git add dcr/fixtures/custom_field.json dcr/hooks.py
git commit -m "feat: standardize LA form layout with Deal reference section"
```

---

### Task 9: Standardize Loan form layout

**Files:**
- Modify: `dcr/fixtures/custom_field.json`

Target layout:
```
[Header — standard]
  Applicant, Applicant Type | Loan Application, Company, Posting Date, Status

[Deal reference]
  Home Build Request (RO), Factory (RO) | Serial No (RO), Buyer Name (RO)

[ACH payment]
  ACH Payment Account

[Payoff]
  Payoff Date, Payoff Good Thru Date, Interest Owed | Late Fees, Service Fees, Insurance, Principal, Paid from Escrow

[Rebate]
  Qualifying Amount
```

- [ ] **Step 1: Rename "Home / Deal Reference" section to "Deal reference"**

Update `Loan-home_deal_reference_section` label from `"Home / Deal Reference"` to `"Deal reference"`.

- [ ] **Step 2: Reorder Deal reference fields**

Current order: HBR, Serial No, Buyer Name | Factory.

Target: HBR, Factory | Serial No, Buyer Name.

Update insert_after values:
- `home_build_request` → insert_after: `home_deal_reference_section` (already correct)
- `factory` → insert_after: `home_build_request` (currently after `column_break_home_deal`)
- `column_break_home_deal` → insert_after: `factory`
- `home_serial_no` → insert_after: `column_break_home_deal`
- `buyer_name` → insert_after: `home_serial_no`

- [ ] **Step 3: Move ACH section before Payoff**

Current: ACH section is after `repayment_method` (in the ERPNext section). Move it:
- `ach_payment_section` → insert_after: `buyer_name` (after Deal reference, before Payoff)
- `ach_payment_account` → insert_after: `ach_payment_section` (already correct relative)

- [ ] **Step 4: Commit**

```bash
git add dcr/fixtures/custom_field.json
git commit -m "feat: standardize Loan form layout with Deal reference section"
```

---

### Task 10: Standardize Loan Disbursement layout

**Files:**
- Modify: `dcr/fixtures/custom_field.json`

Target: `[Header] Against Loan, Disbursement Date | Company, Status` then `[Deal reference] Home Build Request (RO), Factory (RO) | Purchase Invoice (link)`

- [ ] **Step 1: Add Deal reference section to Loan Disbursement**

Add new custom field:
```json
{
  "doctype": "Custom Field",
  "dt": "Loan Disbursement",
  "fieldname": "deal_reference_section",
  "fieldtype": "Section Break",
  "label": "Deal reference",
  "name": "Loan Disbursement-deal_reference_section",
  "insert_after": "against_loan"
}
```

Update insert_after chain:
- `home_build_request` → insert_after: `deal_reference_section`
- `factory` → insert_after: `home_build_request`  (currently after `factory_po`)

Add column break:
```json
{
  "doctype": "Custom Field",
  "dt": "Loan Disbursement",
  "fieldname": "column_break_deal_ref",
  "fieldtype": "Column Break",
  "name": "Loan Disbursement-column_break_deal_ref",
  "insert_after": "factory"
}
```

- `purchase_invoice` → insert_after: `column_break_deal_ref`

- [ ] **Step 2: Add to hooks.py fixtures**

Add:
```python
"Loan Disbursement-deal_reference_section",
"Loan Disbursement-column_break_deal_ref",
```

- [ ] **Step 3: Commit**

```bash
git add dcr/fixtures/custom_field.json dcr/hooks.py
git commit -m "feat: standardize Loan Disbursement layout with Deal reference section"
```

---

### Task 11: Document checklist simplification

**Data migration note:** Replacing the `status` Select with a `waived` Check changes the DB column. Rows with status="Waived" will lose that flag. Rows with status="Received"/"Verified" that have attachments will still pass the new validation (`not waived and not attachment`). If any Draft HBRs have "Waived" checklist rows, they'll need manual fixing after deploy. This is acceptable given the small number of active deals.

**Files:**
- Modify: `dcr/dcr/doctype/document_checklist/document_checklist.json`
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.py`
- Modify: `dcr/public/js/home_build_request.js`

- [ ] **Step 1: Replace status Select with waived Check**

In `dcr/dcr/doctype/document_checklist/document_checklist.json`, replace the `status` field:

Remove:
```json
{
  "default": "Pending",
  "fieldname": "status",
  "fieldtype": "Select",
  "in_list_view": 1,
  "label": "Status",
  "options": "Pending\nReceived\nVerified\nWaived",
  "reqd": 1
}
```

Add in its place:
```json
{
  "default": 0,
  "fieldname": "waived",
  "fieldtype": "Check",
  "in_list_view": 1,
  "label": "Waived"
}
```

Also update the `field_order` array to replace `status` with `waived`.

- [ ] **Step 2: Update validate_checklist_complete**

In `dcr/dcr/doctype/home_build_request/home_build_request.py`, replace `validate_checklist_complete`:

```python
def validate_checklist_complete(self):
    """Block submission unless every checklist row has an attachment or is waived."""
    incomplete = []
    for row in self.doc_checklist:
        if not row.waived and not row.attachment:
            incomplete.append(row.document_type)

    if incomplete:
        frappe.throw(
            _("The following documents are missing: {0}").format(
                ", ".join(incomplete)
            ),
            title=_("Document checklist incomplete"),
        )
```

- [ ] **Step 3: Update populate_checklist in JS**

In `dcr/public/js/home_build_request.js`, update the `populate_checklist` function. Remove `row.status = 'Pending';` since the status field no longer exists:

```javascript
for (var i = 0; i < docs.length; i++) {
    var row = frm.add_child('doc_checklist');
    row.document_type = docs[i];
}
```

- [ ] **Step 4: Commit**

```bash
git add dcr/dcr/doctype/document_checklist/document_checklist.json dcr/dcr/doctype/home_build_request/home_build_request.py dcr/public/js/home_build_request.js
git commit -m "feat: simplify document checklist — replace status with waived checkbox"
```

---

### Task 12: Remove w9_status from Customer

**Files:**
- Modify: `dcr/fixtures/custom_field.json`
- Modify: `dcr/hooks.py`

- [ ] **Step 1: Remove w9_status custom field**

In `dcr/fixtures/custom_field.json`, remove the `Customer-w9_status` entry.

In `dcr/hooks.py`, remove `"Customer-w9_status"` from the Custom Field fixtures filter.

- [ ] **Step 2: Commit**

```bash
git add dcr/fixtures/custom_field.json dcr/hooks.py
git commit -m "feat: remove w9_status — w9_copy Attach field is sufficient"
```

---

### Task 13: Email dropdown buttons

**IMPORTANT:** Only modify the `refresh` handler's button grouping in each file. All helper functions below the handler (Plaid integration, manual entry dialogs, send functions, etc.) must remain completely unchanged. The `Actions` group buttons (Manage Bank Account, Manage Auto-Pay) also stay unchanged.

**Files:**
- Modify: `dcr/public/js/loan.js`
- Modify: `dcr/public/js/loan_application.js`
- Modify: `dcr/public/js/customer.js`

- [ ] **Step 1: Refactor Loan email buttons into Email dropdown**

In `dcr/public/js/loan.js`, replace the individual top-level email buttons with an Email dropdown group:

```javascript
refresh: function(frm) {
    if (frm.doc.docstatus !== 1) return;

    // Email → Disbursement Notice (if any disbursement exists)
    frappe.db.count('Loan Disbursement', {
        filters: { against_loan: frm.doc.name, docstatus: 1 }
    }).then(count => {
        if (count > 0) {
            frm.add_custom_button(__('Disbursement Notice'), function() {
                send_disbursement_notice(frm);
            }, __('Email'));
        }
    });

    // Email → FL Payoff Letter / COD Payoff Letter (active loans)
    if (frm.doc.status && ['Disbursed', 'Active'].includes(frm.doc.status)) {
        frm.add_custom_button(__('FL Payoff Letter'), function() {
            send_payoff(frm, 'Flooring');
        }, __('Email'));

        frm.add_custom_button(__('COD Payoff Letter'), function() {
            send_payoff(frm, 'COD');
        }, __('Email'));
    }

    // Actions: Manage Auto-Pay (unchanged)
    frappe.call({
        method: 'dcr.dcr.doctype.ach_settings.ach_settings.is_ach_enabled',
        callback: function(r) {
            if (r.message) {
                frm.add_custom_button(__('Manage Auto-Pay'), function() {
                    show_autopay_manager(frm);
                }, __('Actions'));
            }
        }
    });
}
```

- [ ] **Step 2: Refactor LA buttons into Email and Create groups**

In `dcr/public/js/loan_application.js`, move email-related buttons into Email dropdown:

```javascript
// Email → Send for Signature (Flooring Packet)
if (!frm.doc.signed_packet) {
    frm.add_custom_button(__('Flooring Packet'), function() {
        send_flooring_packet(frm);
    }, __('Email'));
}

// Email → Pre-Approval
frm.add_custom_button(__('Pre-Approval'), function() {
    send_pre_approval(frm);
}, __('Email'));
```

Keep the Create → Loan button as-is.

- [ ] **Step 3: Refactor Customer buttons into Email dropdown**

In `dcr/public/js/customer.js`, move "Send for Signature" into Email dropdown:

```javascript
// Email → Dealer Agreement (Send for Signature)
if (frm.doc.dealer_agreement_status !== 'Signed') {
    frm.add_custom_button(__('Dealer Agreement'), function() {
        send_dealer_agreement(frm);
    }, __('Email'));
}
```

Keep Create buttons (MIFA, Factory Assignment) as-is.

- [ ] **Step 4: Commit**

```bash
git add dcr/public/js/loan.js dcr/public/js/loan_application.js dcr/public/js/customer.js
git commit -m "feat: consolidate email buttons into Email dropdown across all doctypes"
```

---

### Task 14: Print format signature block restyle

**Files:**
- Modify: `dcr/dcr/print_format/mifa/mifa.json`
- Modify: `dcr/dcr/print_format/exhibit_a_receipt/exhibit_a_receipt.json`
- Modify: `dcr/dcr/print_format/dealer_agreement/dealer_agreement.json`
- Modify: Any other print formats with signature blocks

- [ ] **Step 1: Define the signature block HTML template**

Replace all `inv-items` table-based signature blocks with this pattern:

```html
<!-- ═══ SIGNATURE BLOCK ═══ -->
<div class="no-break" style="padding-top: 32px;">
  <table style="width: 100%; border-collapse: collapse;">
    <tr>
      <td style="width: 48%; vertical-align: top; padding-right: 4%;">
        <div style="font-weight: 600; font-size: 12px; padding-bottom: 12px;">DEALER</div>
        <div style="padding-bottom: 4px;">{{ customer_doc.customer_name or '' }}</div>
        <div style="padding-top: 24px;">
          BY: <span style="border-bottom: 1px solid #333; display: inline-block; min-width: 250px;">&nbsp;</span>
        </div>
        <div style="padding-top: 4px; font-size: 11px; color: #666;">Name</div>
        <div style="padding-top: 16px;">
          <span style="border-bottom: 1px solid #333; display: inline-block; min-width: 250px;">&nbsp;</span>
        </div>
        <div style="padding-top: 4px; font-size: 11px; color: #666;">Title</div>
        <div style="padding-top: 16px;">
          <span style="border-bottom: 1px solid #333; display: inline-block; min-width: 250px;">&nbsp;</span>
        </div>
        <div style="padding-top: 4px; font-size: 11px; color: #666;">Date</div>
      </td>
      <td style="width: 48%; vertical-align: top;">
        <div style="font-weight: 600; font-size: 12px; padding-bottom: 12px;">LENDER</div>
        <div style="padding-bottom: 4px;">Dealer Capital Resources, Inc.</div>
        <div style="padding-bottom: 4px;">A California Corporation</div>
        <div style="padding-bottom: 4px;">CFL 603 I934</div>
        <div style="padding-top: 24px;">
          BY: <span style="border-bottom: 1px solid #333; display: inline-block; min-width: 250px;">&nbsp;</span>
        </div>
        <div style="padding-top: 4px; font-size: 11px; color: #666;">Name</div>
        <div style="padding-top: 16px;">
          <span style="border-bottom: 1px solid #333; display: inline-block; min-width: 250px;">&nbsp;</span>
        </div>
        <div style="padding-top: 4px; font-size: 11px; color: #666;">Title</div>
        <div style="padding-top: 16px;">
          <span style="border-bottom: 1px solid #333; display: inline-block; min-width: 250px;">&nbsp;</span>
        </div>
        <div style="padding-top: 4px; font-size: 11px; color: #666;">Date</div>
      </td>
    </tr>
  </table>
</div>
```

- [ ] **Step 2: Apply to MIFA print format**

In `dcr/dcr/print_format/mifa/mifa.json`, find the signature block (search for `inv-items` near the bottom of the HTML). Replace the entire `<div class="no-break">` block containing the `inv-items` signature table with the template from Step 1.

Preserve any DocuSign anchor tags (`/s1/`, `/s2/`, etc.) that may be embedded in the signature lines — these are needed for the DocuSign signing ceremony. Embed them as zero-width spans where the signature lines are.

- [ ] **Step 3: Apply to Exhibit A print format**

Same pattern for `exhibit_a_receipt.json`.

- [ ] **Step 4: Apply to Dealer Agreement print format**

Same pattern for `dealer_agreement.json`.

- [ ] **Step 5: Review remaining print formats**

Check `dealer_flooring_loan_payoff.json`, `dealer_cod_payoff.json`, and `advance_pre_approval.json` for signature blocks. These are payoff letters and pre-approvals — they may have simpler signature areas. Apply the same restyle if they use `inv-items`.

- [ ] **Step 6: Commit**

```bash
git add dcr/dcr/print_format/
git commit -m "feat: restyle print format signature blocks — classic legal style"
```

---

## Verification Checklist

After all tasks are complete, verify:

- [ ] HBR can be submitted (doc gate works with waived checkbox)
- [ ] HBR submission does NOT auto-create SQ or LA
- [ ] Create → Loan Application button appears on submitted Floored HBRs
- [ ] Create → Purchase Invoice button appears on all submitted HBRs
- [ ] Factory field on HBR only shows approved factories for the selected dealer
- [ ] Serial No and Quote No on LA and Loan are read-only and fetch from HBR
- [ ] Factory on Loan is read-only and fetches from HBR
- [ ] Park details surface as read-only on HBR when Park is selected
- [ ] Multiple Factory Assignments can be created per Customer
- [ ] Factory Assignment auto-sets status to "Submitted" on submit
- [ ] Email dropdown works on Loan (replaces individual buttons)
- [ ] Loan Disbursement `factory_po` field shows label "Purchase Invoice" (fieldname kept for data safety)
- [ ] All forms follow the 5-section layout standard
- [ ] Print format signature areas use classic style, not table grids
