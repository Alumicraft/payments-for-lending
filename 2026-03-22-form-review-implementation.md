# DCR Form Review Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up redundant fields, wire `fetch_from` data flow, remove Sales Order from the pipeline, integrate Loan Product, improve UX, and hide irrelevant Lending module noise. These changes were identified during a hands-on testing session on 2026-03-22.

**Repo:** `Alumicraft/payments-for-lending` (branch: main)

**Key files:**
- `dcr/hooks.py` — fixture declarations, doc_events
- `dcr/fixtures/custom_field.json` — 82 custom fields across 7 doctypes
- `dcr/fixtures/doctype_link.json` — 5 connections panel links
- `dcr/dcr/doctype/*/` — custom doctypes (HBR, MIFA, etc.)
- `dcr/public/js/` — 6 client scripts (loan, loan_application, home_build_request, customer, mifa, factory_assignment)
- `dcr/api/` — server methods (lending.py, docusign.py, dcr_email.py, sales_order_hooks.py, achq_integration.py, etc.)
- `dcr/dcr/print_format/` — 8 Jinja print formats
- `dcr/patches.txt` — currently has 2 patches (rename_dcr_floored, reorder_customer_links)

**IMPORTANT:** This app runs on Frappe Cloud. No bench commands. All migrations happen via fixtures, patches, and `after_migrate` hooks. Test by running the Frappe test runner or verifying in the browser.

---

## Review Decisions Log

> These decisions were made during code review on 2026-03-22. Flagged here for human review before execution.

### Decision 1: HBR "Create → Loan Application" button — call server method directly, not `frm.trigger('submit')`
**Original plan** had the fallback button call `frm.trigger('submit')` to re-trigger `on_submit`. This is wrong — you cannot re-submit an already-submitted doc in Frappe (docstatus 1 → 1 is not a valid transition). **Fix:** The button calls a new whitelisted server method `create_loan_application_from_hbr` directly. The `on_submit` hook handles the automatic path; the button is a manual fallback.

### Decision 2: HBR `links` array needs Sales Order entry removed too
The original plan removes the `sales_order` *field* from HBR JSON and the fixture entries, but missed that `home_build_request.json` also has a hardcoded `links` entry at the doctype level: `{"group": "Orders", "link_doctype": "Sales Order", "link_fieldname": "home_build_request"}`. This must also be removed or the connections panel will still show Sales Order.

### Decision 3: `signed_packet` is currently `hidden: 1` — need both `hidden: 0` AND `read_only: 1`
The original plan only said "set `read_only: 1`". But the field is currently `hidden: 1` with no `read_only` key. To make it visible but non-editable, we need to set *both* properties.

### Decision 4: Print format rebate — add fallback for loans without a Loan Product
Older loans may not have `loan_product` set. The Jinja template must fall back gracefully: `frappe.db.get_value("Loan Product", doc.loan_product, "rebate_percentage") if doc.loan_product else 0`. Without this, print would crash on legacy data.

### Decision 5: Items from testing notes deferred to future work
These testing note items are **not** included in this plan:
- **#17 (Replace Loan fee fields with Loan Charges)** — requires investigation into Frappe Lending's native Loan Charges feature. Separate spike.
- **#18 ("Is Term Loan" default from Loan Product)** — Loan Product config, not a code change. Set manually.
- **#24 (Purchase Invoice button on Loan)** — The testing notes ask for a "Create → Purchase Invoice" on Loan, but this flow isn't clear enough yet (should it be on Loan or Loan Disbursement?). Deferred.

### Decision 6: `sales_order_hooks.py` has no external imports — safe to delete
Grep confirmed no file in the codebase imports from `dcr.api.sales_order_hooks`. The only reference is in `hooks.py` `doc_events`. Safe to delete.

### Decision 7: Loan validate hook approach for deal reference fields
Frappe Lending's `create_loan` mapped doc only copies fields that exist on the Loan Application standard form. Our custom fields (`home_serial_no`, `buyer_name`, `factory`) are not in the field mapping. Confirmed: must use a `doc_events` validate hook on Loan to populate them.

### Decision 8: `home_build_request` guard in loan_application.js must be preserved
The current `loan_application.js` has two guards: `if (frm.is_new()) return;` and `if (!frm.doc.home_build_request) return;`. When changing the first to `docstatus !== 1`, we must keep the HBR check — without it, non-DCR loan applications (if any exist) would get DCR-specific buttons.

---

## Chunk 1: Customer Field Cleanup

Remove 7 unused/redundant custom fields from Customer and reorganize sections.

### Task 1: Remove unused Customer fields

**Files:**
- Modify: `dcr/hooks.py`
- Modify: `dcr/fixtures/custom_field.json`

**Context:** These fields exist in `hooks.py` lines 46-52 and have corresponding entries in `custom_field.json`. The `dcr_application_section` and `column_break_dcr1` are layout fields for the section being removed.

- [ ] **Step 1:** Remove these field names from the `hooks.py` fixtures `Custom Field` filter list:
  - `Customer-mifa_required`
  - `Customer-master_dealer_list_updated`
  - `Customer-dcr_application_status`
  - `Customer-dcr_account_no`
  - `Customer-rebate_percentage`
  - `Customer-dcr_application_section`
  - `Customer-column_break_dcr1`

- [ ] **Step 2:** Remove the corresponding 7 entries from `dcr/fixtures/custom_field.json` (match on `"name"` field)

- [ ] **Step 3:** Set `"read_only": 1` on the `Customer-dealer_agreement_status` entry in `custom_field.json`

### Task 2: Reorganize Customer sections

**Files:**
- Modify: `dcr/fixtures/custom_field.json`

**Context:** `Customer-dealer_agreement_section` is currently the last entry in `custom_field.json` (along with `entity_type`). `dealer_agreement_status` needs to move into that section.

- [ ] **Step 1:** Update `Customer-dealer_agreement_status` so its `"insert_after"` is `"dealer_agreement_section"` (placing it first in the Dealer Agreement section, before `entity_type`)

- [ ] **Step 2:** Verify the Dealer Agreement section field order is: `dealer_agreement_section` → `dealer_agreement_status` (read-only) → `entity_type`

### Task 3: Add Loan Product link to Customer

**Files:**
- Modify: `dcr/hooks.py`
- Modify: `dcr/fixtures/custom_field.json`

- [ ] **Step 1:** Add `Customer-default_loan_product` to `hooks.py` fixtures filter list (add after the `Customer-entity_type` line)

- [ ] **Step 2:** Add to `custom_field.json`:
```json
{
  "doctype": "Custom Field",
  "name": "Customer-default_loan_product",
  "dt": "Customer",
  "fieldname": "default_loan_product",
  "fieldtype": "Link",
  "options": "Loan Product",
  "label": "Default Loan Product",
  "insert_after": "dealer_agreement_status",
  "description": "Default loan terms for this dealer — sets interest rate, rebate, and repayment terms"
}
```

---

## Chunk 2: Loan Product Custom Field

### Task 4: Add rebate_percentage to Loan Product

**Files:**
- Modify: `dcr/hooks.py`
- Modify: `dcr/fixtures/custom_field.json`

- [ ] **Step 1:** Add `Loan Product-rebate_percentage` to `hooks.py` fixtures filter list (new doctype group — add after the existing Loan Disbursement entries)

- [ ] **Step 2:** Add to `custom_field.json`:
```json
{
  "doctype": "Custom Field",
  "name": "Loan Product-rebate_percentage",
  "dt": "Loan Product",
  "fieldname": "rebate_percentage",
  "fieldtype": "Percent",
  "label": "Rebate Percentage",
  "insert_after": "penalty_interest_rate",
  "description": "Dealer rebate applied at loan payoff"
}
```

---

## Chunk 3: MIFA Updates

### Task 5: Add Loan Product link and make submittable

**Files:**
- Modify: `dcr/dcr/doctype/mifa/mifa.json`

**Context:** Current MIFA field_order is: `customer`, `mifa_date`, `column_break_1`, `credit_limit`, `interest_rate`, `entity_type`, `effective_date`, `terms_section`, `payment_terms`, `signature_section`, `signed_mifa`, `dealer_signer_title`. The `interest_rate` field (line 50-54 of mifa.json) is a plain Percent field with no fetch_from.

- [ ] **Step 1:** Add `loan_product` field to MIFA doctype JSON. Insert into `field_order` after `customer` and add to `fields` array:
```json
{
  "fieldname": "loan_product",
  "fieldtype": "Link",
  "options": "Loan Product",
  "label": "Loan Product",
  "reqd": 1
}
```

- [ ] **Step 2:** Update the existing `interest_rate` field (currently at fields array index 4) to add:
  - `"fetch_from": "loan_product.rate_of_interest"`
  - `"read_only": 1`

- [ ] **Step 3:** Set `"is_submittable": 1` at the doctype root level

- [ ] **Step 4:** Update `dcr/public/js/mifa.js` — change the guard from:
```javascript
if (frm.is_new() || !frm.doc.customer) return;
```
to:
```javascript
if (frm.doc.docstatus !== 1) return;
```
This ensures "Send for Signature" only shows after submission.

### Task 6: Add MIFA validation before send

**Files:**
- Modify: `dcr/public/js/mifa.js`

**Context:** The current `send_mifa` function (line 21 of mifa.js) validates customer email but nothing else.

- [ ] **Step 1:** At the top of `send_mifa(frm)`, add validation:
```javascript
if (!frm.doc.credit_limit || frm.doc.credit_limit <= 0) {
    frappe.msgprint(__('Credit Limit must be set before sending for signature.'));
    return;
}
if (!frm.doc.loan_product) {
    frappe.msgprint(__('Loan Product must be set before sending for signature.'));
    return;
}
```

---

## Chunk 4: Remove Sales Order from Flow

### Task 7: Remove Sales Order integration

**Files:**
- Delete: `dcr/api/sales_order_hooks.py`
- Modify: `dcr/hooks.py`
- Modify: `dcr/fixtures/custom_field.json`
- Modify: `dcr/fixtures/doctype_link.json`
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.py`
- Modify: `dcr/public/js/home_build_request.js`

**Context:** `sales_order_hooks.py` (55 lines) has one function `on_submit` that creates a Loan Application when a Floored Sales Order is submitted. No other file imports from it (confirmed via grep). The logic is being moved into `home_build_request.py` so LA creation happens directly from HBR submit.

- [ ] **Step 1:** Delete `dcr/api/sales_order_hooks.py`

- [ ] **Step 2:** Remove from `hooks.py`:
  - Remove the entire `"Sales Order"` block from `doc_events` (lines ~133-135):
    ```python
    "Sales Order": {
        "on_submit": "dcr.api.sales_order_hooks.on_submit"
    },
    ```
  - Remove `"Sales Order-Home Build Request"` from the `DocType Link` fixtures filter list (line ~29)
  - Remove all 4 `Sales Order-*` entries from the `Custom Field` fixtures filter list:
    - `Sales Order-home_build_request`
    - `Sales Order-home_type`
    - `Sales Order-financing_type`
    - `Sales Order-property_type`

- [ ] **Step 3:** Remove all 4 Sales Order custom field entries from `custom_field.json` (match on `"dt": "Sales Order"`)

- [ ] **Step 4:** Remove `Sales Order-Home Build Request` entry from `doctype_link.json` (the entry with `"parent": "Sales Order"`)

- [ ] **Step 5:** In `home_build_request.json`:
  - Remove `sales_order` from the `field_order` array
  - Remove the `sales_order` field object from the `fields` array
  - Remove the Sales Order entry from the `links` array: `{"group": "Orders", "link_doctype": "Sales Order", "link_fieldname": "home_build_request"}`

- [ ] **Step 6:** In `home_build_request.py`, add Loan Application auto-creation on submit for Floored deals. Add these methods to the `HomeBuildRequest` class:
```python
def on_submit(self):
    if self.financing_type == "Floored":
        self._create_loan_application()

def _create_loan_application(self):
    """Auto-create Loan Application for Floored deals on HBR submit."""
    existing = frappe.db.exists("Loan Application", {
        "home_build_request": self.name,
        "docstatus": ["!=", 2]
    })
    if existing:
        frappe.msgprint(
            _("Loan Application {0} already exists for this Home Build Request.").format(existing),
            indicator="orange"
        )
        return

    la = frappe.new_doc("Loan Application")
    la.applicant_type = "Customer"
    la.applicant = self.customer
    la.home_build_request = self.name
    la.home_type = self.home_type

    # Set loan product from customer default
    default_product = frappe.db.get_value("Customer", self.customer, "default_loan_product")
    if default_product:
        la.loan_product = default_product

    # Set loan amount from home invoice if available
    if self.home_invoice_plus_freight:
        la.loan_amount = self.home_invoice_plus_freight

    la.insert()

    # Link back
    self.db_set("loan_application", la.name)

    frappe.msgprint(
        _("Loan Application {0} created for flooring.").format(
            f'<a href="/app/loan-application/{la.name}">{la.name}</a>'
        ),
        indicator="green",
        alert=True,
    )
```

- [ ] **Step 7:** Also add a whitelisted method for the manual fallback button (add below the class):
```python
@frappe.whitelist()
def create_loan_application_from_hbr(hbr_name):
    """Manual fallback to create Loan Application from a submitted HBR."""
    hbr = frappe.get_doc("Home Build Request", hbr_name)
    if hbr.docstatus != 1:
        frappe.throw(_("Home Build Request must be submitted first."))
    if hbr.financing_type != "Floored":
        frappe.throw(_("Loan Applications are only created for Floored deals."))
    hbr._create_loan_application()
    return {"success": True}
```

- [ ] **Step 8:** In `home_build_request.js`, replace the entire "Create → Sales Order" block (lines 13-23) with:
```javascript
// Create → Loan Application (Floored only, no existing LA)
if (frm.doc.docstatus === 1 && frm.doc.financing_type === 'Floored' && !frm.doc.loan_application) {
    frm.add_custom_button(__('Loan Application'), function() {
        frappe.call({
            method: 'dcr.dcr.doctype.home_build_request.home_build_request.create_loan_application_from_hbr',
            args: { hbr_name: frm.doc.name },
            freeze: true,
            freeze_message: __('Creating Loan Application...'),
            callback: function(r) {
                if (r.message && r.message.success) {
                    frm.reload_doc();
                }
            }
        });
    }, __('Create'));
}

// Create → Supplier Quotation (submitted, no factory_quote linked, factory set)
if (frm.doc.docstatus === 1 && !frm.doc.factory_quote && frm.doc.factory) {
    frm.add_custom_button(__('Supplier Quotation'), function() {
        frappe.new_doc('Supplier Quotation', {
            supplier: frm.doc.factory,
            home_build_request: frm.doc.name
        });
    }, __('Create'));
}
```
Note: This also adds the Supplier Quotation button (was Task 15), since both live in the same refresh block.

- [ ] **Step 9:** Create a data migration patch `dcr/patches/remove_sales_order_fields.py`:
```python
import frappe

def execute():
    """Remove Sales Order custom fields and DocType Link that are no longer needed."""
    for field in ["Sales Order-home_build_request", "Sales Order-home_type",
                  "Sales Order-financing_type", "Sales Order-property_type"]:
        if frappe.db.exists("Custom Field", field):
            frappe.delete_doc("Custom Field", field, force=True)

    if frappe.db.exists("DocType Link", "Sales Order-Home Build Request"):
        frappe.delete_doc("DocType Link", "Sales Order-Home Build Request", force=True)

    frappe.db.commit()
```

- [ ] **Step 10:** Add the patch to `dcr/patches.txt`: `dcr.patches.remove_sales_order_fields`

---

## Chunk 5: Loan Application Improvements

### Task 8: Add fetch_from fields on Loan Application

**Files:**
- Modify: `dcr/fixtures/custom_field.json`

**Context:** These fields already exist in custom_field.json. We are adding `fetch_from` properties so they auto-populate when `home_build_request` is set.
- `Loan Application-floor_plan` (line 642): Data field, currently no fetch_from
- `Loan Application-buyer_name` (line 659): Data field, currently no fetch_from
- `Loan Application-requested_advance_amount` (line 320): Currency field, currently no fetch_from

- [ ] **Step 1:** Update `Loan Application-floor_plan`:
  - Add `"fetch_from": "home_build_request.model_name"`
  - Set `"read_only": 1`
  - Note: `model_name` is a Link to "Model" doctype — fetch_from will get the Model name (ID), which is the desired behavior for a floor plan identifier

- [ ] **Step 2:** Update `Loan Application-buyer_name`:
  - Add `"fetch_from": "home_build_request.home_buyer"`
  - Keep editable (`read_only` NOT set) — `home_buyer` is a Link to Customer; fetch gets the Customer name/ID, but staff may need to type a different name

- [ ] **Step 3:** Update `Loan Application-requested_advance_amount`:
  - Add `"fetch_from": "home_build_request.home_invoice_plus_freight"`
  - Add `"fetch_if_empty": 1`

### Task 9: Clean up Loan Application fields

**Files:**
- Modify: `dcr/hooks.py`
- Modify: `dcr/fixtures/custom_field.json`

**Context:** `doc_checklist` on LA duplicates the HBR checklist. `signed_packet` (line 368 of custom_field.json) is currently `"hidden": 1` — it stores the signed PDF attachment URL set by the DocuSign webhook.

- [ ] **Step 1:** Remove these from BOTH `hooks.py` filter list AND `custom_field.json`:
  - `Loan Application-dcr_documents_section`
  - `Loan Application-doc_checklist`

- [ ] **Step 2:** Update `Loan Application-signed_packet` in `custom_field.json`:
  - Change `"hidden": 1` to `"hidden": 0`
  - Add `"read_only": 1`
  - This makes the signed packet visible (so users can see/download it) but non-editable

### Task 10: Require submission before send buttons

**Files:**
- Modify: `dcr/public/js/loan_application.js`

**Context:** Current guards (lines 12-13 of loan_application.js): `if (frm.is_new()) return;` then `if (!frm.doc.home_build_request) return;`. The "Create → Loan" button already checks `docstatus === 1` (line 22), but "Send for Signature" and "Send Pre-Approval" show on any saved (non-new) LA.

- [ ] **Step 1:** Change the first guard from:
```javascript
if (frm.is_new()) return;
```
to:
```javascript
if (frm.doc.docstatus !== 1) return;
```
Keep the existing `if (!frm.doc.home_build_request) return;` guard on the line after — this prevents DCR buttons from showing on non-DCR loan applications.

### Task 11: Auto-calculate pre-approval fields

**Files:**
- Modify: `dcr/api/lending.py`

**Context:** `validate_loan_application` (line 45 of lending.py) currently handles credit checks and advance date validation. The pre-approval fields (`custom_projected_equity`, `custom_projected_ltv`) are in custom_field.json but never calculated server-side.

- [ ] **Step 1:** At the end of `validate_loan_application` (after line 88), add:
```python
# Auto-calculate pre-approval fields
investment = doc.get("custom_projected_investment") or 0
sales_price = doc.get("custom_projected_sales_price") or 0

if investment and sales_price:
    doc.custom_projected_equity = sales_price - investment
    doc.custom_projected_ltv = (investment / sales_price) * 100
```

---

## Chunk 6: Loan fetch_from and Print Format Updates

### Task 12: Add Loan validate hook for deal reference fields

**Files:**
- Modify: `dcr/api/lending.py`
- Modify: `dcr/hooks.py`

**Context:** Frappe Lending's `create_loan` mapped doc only copies standard Loan Application fields. Our custom fields (`home_serial_no`, `buyer_name`, `factory`) on Loan are not in that mapping. We need a validate hook to populate them from the Loan Application.

- [ ] **Step 1:** Add to `dcr/api/lending.py`:
```python
def on_loan_validate(doc, method):
    """Populate deal reference fields from Loan Application."""
    if not doc.loan_application:
        return
    la = frappe.db.get_value("Loan Application", doc.loan_application,
        ["home_serial_no", "buyer_name", "home_build_request"], as_dict=True)
    if not la:
        return
    if not doc.home_serial_no and la.home_serial_no:
        doc.home_serial_no = la.home_serial_no
    if not doc.buyer_name and la.buyer_name:
        doc.buyer_name = la.buyer_name
    if la.home_build_request:
        factory = frappe.db.get_value("Home Build Request", la.home_build_request, "factory")
        if factory and not doc.factory:
            doc.factory = factory
```

- [ ] **Step 2:** Add to `hooks.py` `doc_events` (alongside the existing `"Loan Application"` entry):
```python
"Loan": {
    "validate": "dcr.api.lending.on_loan_validate"
},
```

### Task 13: Update payoff print formats for Loan Product

**Files:**
- Modify: `dcr/dcr/print_format/dealer_flooring_loan_payoff/dealer_flooring_loan_payoff.json`
- Modify: `dcr/dcr/print_format/dealer_cod_payoff/dealer_cod_payoff.json`

**Context:** Both templates currently read `doc.rebate_percentage` directly (a custom field on Loan). We're moving rebate_percentage to Loan Product. Must handle legacy loans that don't have `loan_product` set.

- [ ] **Step 1:** In **dealer_flooring_loan_payoff**, within the `html` field, replace:
```jinja
{% set rebate = (doc.qualifying_amount or 0) * (doc.rebate_percentage or 0) / 100 %}
```
with:
```jinja
{% set loan_product_rebate = frappe.db.get_value("Loan Product", doc.loan_product, "rebate_percentage") if doc.loan_product else 0 %}
{% set loan_product_rebate = loan_product_rebate or 0 %}
{% set rebate = (doc.qualifying_amount or 0) * loan_product_rebate / 100 %}
```
And replace the rebate percentage display:
```jinja
{{ doc.rebate_percentage or 0 }}%
```
with:
```jinja
{{ loan_product_rebate }}%
```

- [ ] **Step 2:** In **dealer_cod_payoff**, within the `html` field, make the same two replacements:
  - Replace `{% set rebate = (doc.qualifying_amount or 0) * (doc.rebate_percentage or 0) / 100 %}` with the same 3-line version above
  - Replace `{{ doc.rebate_percentage or 0 }}%` with `{{ loan_product_rebate }}%`

---

## Chunk 7: Home Build Request Cleanup

### Task 14: HBR field cleanup

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`

**Context:** `home_name` (line 59-63) is a Data field used for "document naming" but appears unused in practice. `status` (line 66-73) is a Select field with no `read_only`. `space_number` (line 154-157) has label "Space #".

- [ ] **Step 1:** Remove `home_name` from `field_order` array AND remove the field object from `fields` array

- [ ] **Step 2:** Set `"read_only": 1` on the `status` field object

- [ ] **Step 3:** Change `space_number` label from `"Space #"` to `"Space No"`

---

## Chunk 8: Loan Disbursement Field Rename

### Task 15: Rename factory_po label on Loan Disbursement

**Files:**
- Modify: `dcr/fixtures/custom_field.json`

**Context:** `Loan Disbursement-factory_po` is currently a Link field. The flow is changing from Purchase Order to Purchase Invoice.

- [ ] **Step 1:** Update the `Loan Disbursement-factory_po` entry in `custom_field.json`:
  - Change `"label"` to `"Purchase Invoice"`
  - Change `"options"` to `"Purchase Invoice"` (if currently set to `Purchase Order`)
  - Keep `fieldname` as `factory_po` to avoid migration

---

## Chunk 9: UX Improvements

### Task 16: Primary button styling

**Files:**
- Modify: `dcr/public/js/home_build_request.js`
- Modify: `dcr/public/js/customer.js`
- Modify: `dcr/public/js/loan_application.js`
- Modify: `dcr/public/js/mifa.js`

**Context:** Each file has `frm.add_custom_button()` calls with `__('Create')` group. The `change_custom_button_type` call must come after the button is added, using the exact label passed to `add_custom_button`.

- [ ] **Step 1:** In each JS file, after every `frm.add_custom_button()` call that uses `__('Create')` group, add:
```javascript
frm.change_custom_button_type(__('<Button Label>'), __('Create'), 'primary');
```
Where `<Button Label>` matches the first argument to `add_custom_button`. Specific buttons:
- `home_build_request.js`: `Loan Application`, `Supplier Quotation`
- `customer.js`: `MIFA`, `Factory Assignment`
- `loan_application.js`: `Loan`
- `mifa.js`: (no Create buttons — skip)

### Task 17: Signing status indicators

**Files:**
- Modify: `dcr/public/js/customer.js`
- Modify: `dcr/public/js/mifa.js`
- Modify: `dcr/public/js/loan_application.js`

- [ ] **Step 1:** In `customer.js` refresh, add after the `customer_group !== 'Dealer'` guard (line 13), before the buttons:
```javascript
// Signing status indicator
if (frm.doc.dealer_agreement_status === 'Signed') {
    frm.page.set_indicator(__('Agreement Signed'), 'green');
} else if (frm.doc.dealer_agreement_status === 'Sent') {
    frm.page.set_indicator(__('Awaiting Signature'), 'orange');
}
```

- [ ] **Step 2:** In `mifa.js`, the signed indicator already exists (line 11-13). Replace the entire indicator block with:
```javascript
if (frm.doc.signed_mifa) {
    frm.page.set_indicator(__('Signed'), 'green');
} else {
    frappe.db.get_value('Signature Request',
        {reference_doctype: 'MIFA', reference_name: frm.doc.name, status: 'Sent'},
        'name', function(r) {
            if (r && r.name) {
                frm.page.set_indicator(__('Awaiting Signature'), 'orange');
            }
        });
}
```
Note: This code runs before the `docstatus !== 1` guard added in Task 5, so move the indicator code to run for any saved (non-new) MIFA, then gate the buttons after.

- [ ] **Step 3:** In `loan_application.js` refresh, add after the `docstatus !== 1` guard but before buttons:
```javascript
// Signing status indicator
if (frm.doc.signed_packet) {
    frm.page.set_indicator(__('Signed'), 'green');
} else {
    frappe.db.get_value('Signature Request',
        {reference_doctype: 'Loan Application', reference_name: frm.doc.name, status: 'Sent'},
        'name', function(r) {
            if (r && r.name) {
                frm.page.set_indicator(__('Awaiting Signature'), 'orange');
            }
        });
}
```
**Wait** — if the docstatus guard returns early for non-submitted LAs, the indicator won't show. Restructure: move the indicator code *before* the docstatus guard, gated only by `!frm.is_new()`:
```javascript
refresh: function(frm) {
    if (!frm.is_new() && frm.doc.home_build_request) {
        // Signing status indicator (show on any saved LA)
        if (frm.doc.signed_packet) {
            frm.page.set_indicator(__('Signed'), 'green');
        } else {
            frappe.db.get_value('Signature Request',
                {reference_doctype: 'Loan Application', reference_name: frm.doc.name, status: 'Sent'},
                'name', function(r) {
                    if (r && r.name) {
                        frm.page.set_indicator(__('Awaiting Signature'), 'orange');
                    }
                });
        }
    }

    // Buttons require submission
    if (frm.doc.docstatus !== 1) return;
    if (!frm.doc.home_build_request) return;

    // ... existing button code ...
}
```

---

## Chunk 10: Welcome Email Wiring

### Task 18: Wire dealer welcome email

**Files:**
- Modify: `dcr/api/dcr_email.py`
- Modify: `dcr/api/docusign.py`

**Context:** `send_dealer_welcome` (line 165 of dcr_email.py) currently takes `dcr_account_no` parameter. The `dcr_account_no` field is being removed from Customer. Use `customer.name` (the Customer ID like "CUST-0001") instead. In `docusign.py`, `_update_reference_document` (line 396) handles the Dealer Agreement signed case at line 402-405, calling `_send_signed_email(sig_req)`. The welcome email should fire after the signed confirmation email.

- [ ] **Step 1:** In `dcr_email.py`, update `send_dealer_welcome` signature (line 165):
```python
def send_dealer_welcome(customer_name, account_id, to_email, reference_name=None):
    """Send dealer welcome email after account approval."""
    return _send_dcr_email(
        template="dealer-welcome",
        to_email=to_email,
        subject="Welcome to Dealer Capital Resources",
        data={
            "customer_name": customer_name,
            "account_id": account_id,
        },
        reference_doctype="Customer",
        reference_name=reference_name,
    )
```

- [ ] **Step 2:** In `docusign.py` `_update_reference_document`, after line 405 (`_send_signed_email(sig_req)`), add within the same `if` block:
```python
            # Send welcome email after dealer agreement signed
            try:
                customer_doc = frappe.get_doc("Customer", sig_req.reference_name)
                if customer_doc.email_id:
                    from dcr.api.dcr_email import send_dealer_welcome
                    send_dealer_welcome(
                        customer_name=customer_doc.customer_name,
                        account_id=customer_doc.name,
                        to_email=customer_doc.email_id,
                        reference_name=sig_req.reference_name,
                    )
            except Exception as e:
                frappe.log_error(
                    f"Failed to send welcome email for {sig_req.reference_name}: {str(e)}",
                    "Dealer Welcome Email"
                )
```
This is wrapped in its own try/except so a welcome email failure doesn't block the signed confirmation flow.

---

## Chunk 11: Hide Lending Module Noise

This chunk uses patches to hide irrelevant fields added by the Lending module.

### Task 19: Create noise-hiding patch

**Files:**
- Create: `dcr/patches/hide_lending_noise.py`
- Modify: `dcr/patches.txt`

**Context:** The Lending module adds fields and connections that don't apply to DCR's dealer flooring workflow. Custom Fields can be hidden directly. Connections defined in DocType `links` arrays require Property Setter to hide.

- [ ] **Step 1:** Create `dcr/patches/hide_lending_noise.py`:
```python
import frappe

def execute():
    """Hide irrelevant Lending module fields and sections from DCR forms."""
    # Custom Fields to hide
    fields_to_hide = [
        # Customer - Loan Details tab (from Lending module)
        "Customer-loan_details_tab",
    ]

    for field_name in fields_to_hide:
        if frappe.db.exists("Custom Field", field_name):
            frappe.db.set_value("Custom Field", field_name, "hidden", 1)

    # Property Setters to hide connections panel links that come from Lending module
    # These are DocType-level links, not Custom Fields, so we use Property Setter
    links_to_hide = [
        # (parent_doctype, link_doctype_to_hide)
        # Add specific entries as discovered during testing
    ]

    for parent_dt, link_dt in links_to_hide:
        # Property Setter approach: set the link's "hidden" property
        # Note: This may need adjustment based on Frappe version behavior
        pass

    frappe.db.commit()
```

- [ ] **Step 2:** Add to `dcr/patches.txt`: `dcr.patches.hide_lending_noise`

**NOTE:** The full list of fields and connections to hide needs to be verified on the live instance. The testing notes list specific items (Loan Classification Details, Loan Security Pledge/Unpledge, Loan Write Off, Loan Restructure, Days Past Due Log) but these need their exact Custom Field names or DocType Link identifiers confirmed. Update the patch after discovery.

---

## Blocked Items (Waiting on DCR)

These items cannot be implemented until DCR provides answers:

1. **GL Account Setup for Loan Product** — Need to know: disbursement bank account, loan receivable account, repayment account. Currently blocking Loan Disbursement submission.

2. **ACHQ Sandbox Credentials** — Merchant ID, Gate ID, Gate Key needed for ACH testing.

3. **Bryt Data Migration** — Need export of active loans with current balances, repayment history, and dealer credit limits.

## Deferred Items (Future Work)

These items from the testing session notes are **not** in this plan:

1. **Replace Loan custom fee fields with native Loan Charges** (testing note #17) — Requires spike into Frappe Lending's Loan Charges feature to understand compatibility.

2. **"Is Term Loan" default from Loan Product** (testing note #18) — Configuration, not code. Set manually on Loan Product.

3. **Purchase Invoice button on Loan** (testing note #24) — Flow unclear; may belong on Loan Disbursement instead. Needs design discussion.

4. **Loan `rebate_percentage` field cleanup** — After print formats are updated (Task 13), the `Loan-rebate_percentage` custom field becomes orphaned. Remove it in a follow-up once confirmed no other code reads it.

---

## Verification Plan

After all changes are deployed, recreate the **Goldey / West View MH** deal end-to-end as the acceptance test:

1. Create Customer "West View Manufactured Homes" with dealer fields
2. Set default_loan_product to "DCR Standard"
3. Create MIFA with credit limit, verify interest rate fetches from Loan Product
4. Submit MIFA, send for signature → DocuSign → sign → webhook
5. Send Dealer Agreement → DocuSign → sign → webhook → welcome email fires
6. Create HBR: Customer Sold, Floored, Park → verify 8-doc checklist
7. Mark docs received, submit HBR → Loan Application auto-created
8. Verify LA fields fetched from HBR (buyer, model, amount)
9. Submit LA, send flooring packet → DocuSign → sign → webhook → signed_packet visible
10. Create Loan → verify deal reference fields populated (home_serial_no, buyer_name, factory)
11. Create Loan Disbursement → verify accounting entries
12. Generate FL Payoff Letter → verify rebate reads from Loan Product
13. Generate COD Payoff Letter → verify rebate reads from Loan Product
14. Verify all "Create →" buttons are primary styled
15. Verify signing indicators show on Customer, MIFA, and Loan Application
16. Compare all generated documents against the uploaded Goldey/West View PDFs
