# 2026-03-24 Implementation Plan — Bug Fixes + Features

**Repo:** Alumicraft/payments-for-lending
**Context:** Found during Goldey deal end-to-end walkthrough. Issues span the full chain: HBR → LA → Loan → Loan Disbursement.

**Chunks:** 7 (Web Form deferred to separate PR)
**Execution order:** 1 → 7. Chunk 1 is the foundation.

---

## Chunk 1: fetch_from Chain — HBR → LA → Loan → Loan Disbursement

Deal reference data (HBR, factory, serial #, buyer) must flow through every step. Currently broken at multiple points.

### Task 1: Add factory field to Loan Application

**File:** `dcr/fixtures/custom_field.json`

Add new custom field entry (and register in `hooks.py` fixtures filter):

```json
{
  "doctype": "Custom Field",
  "name": "Loan Application-factory",
  "dt": "Loan Application",
  "fieldname": "factory",
  "fieldtype": "Link",
  "options": "Supplier",
  "label": "Factory",
  "insert_after": "home_type",
  "fetch_from": "home_build_request.factory",
  "read_only": 1
}
```

**Also update `hooks.py`** — add `"Loan Application-factory"` to the fixtures filter list.

### Task 2: Add home_build_request field to Loan

**File:** `dcr/fixtures/custom_field.json`

Add new custom field:

```json
{
  "doctype": "Custom Field",
  "name": "Loan-home_build_request",
  "dt": "Loan",
  "fieldname": "home_build_request",
  "fieldtype": "Link",
  "options": "Home Build Request",
  "label": "Home Build Request",
  "insert_after": "home_deal_reference_section"
}
```

**Also update `hooks.py`** — add `"Loan-home_build_request"` to the fixtures filter list.

### Task 3: Extend on_loan_validate to copy home_build_request

**File:** `dcr/api/lending.py` — `on_loan_validate()` (line 120)

The existing function already copies `home_serial_no`, `buyer_name`, and `factory` from the LA. It fetches `home_build_request` from LA but only uses it to look up the factory on HBR.

**Change:** Also copy `home_build_request` directly to the Loan. Update the `get_value` fields list and add assignment:

```python
def on_loan_validate(doc, method):
    """Populate deal reference fields from Loan Application."""
    if not doc.loan_application:
        return
    la = frappe.db.get_value("Loan Application", doc.loan_application,
        ["home_serial_no", "buyer_name", "home_build_request", "factory"], as_dict=True)
    if not la:
        return
    if not doc.home_serial_no and la.home_serial_no:
        doc.home_serial_no = la.home_serial_no
    if not doc.buyer_name and la.buyer_name:
        doc.buyer_name = la.buyer_name
    if not doc.home_build_request and la.home_build_request:
        doc.home_build_request = la.home_build_request
    if not doc.factory and la.factory:
        doc.factory = la.factory
```

**Note:** This replaces the original approach of looking up factory via HBR. Now that LA has its own `factory` field (Task 1), we can read it directly. Simpler and fewer queries.

### Task 4: Add fetch_from on Loan Disbursement fields

**File:** `dcr/fixtures/custom_field.json`

Update existing Loan Disbursement custom fields to add `fetch_from`:

**`Loan Disbursement-home_build_request`** (line 462) — add:
```json
"fetch_from": "against_loan.home_build_request"
```

**`Loan Disbursement-factory`** (line 482) — add:
```json
"fetch_from": "against_loan.factory"
```

### Task 5: Set factory on LA in HBR on_submit

**File:** `dcr/dcr/doctype/home_build_request/home_build_request.py` — `_create_loan_application()` (line 55)

After `la.home_type = self.home_type` (line 72), add:

```python
if self.factory:
    la.factory = self.factory
```

This ensures factory is set on LA creation even before `fetch_from` fires (since `fetch_from` only triggers on UI Link field changes, not programmatic `insert()`).

---

## Chunk 2: Create Button Styling on Loan Application

### Task 6: Make "Create" group button primary (black)

**File:** `dcr/public/js/loan_application.js` — line 51

After the existing:
```js
frm.change_custom_button_type(__('Loan'), __('Create'), 'primary');
```

Add:
```js
frm.change_custom_button_type('Create', null, 'primary');
```

This must be inside the `if (frm.doc.signed_packet && frm.doc.docstatus === 1)` block (line 44) since that's the only place the Create group exists.

---

## Chunk 3: Disbursement Notice Button on Loan

### Task 7: Fix "Send Disbursement Notice" button visibility

**File:** `dcr/public/js/loan.js` — line 18

**Problem:** The button checks `frm.doc.status === 'Disbursed'`, but Frappe Lending may use a different status string after disbursement (e.g. "Sanctioned", "Partially Disbursed").

**Fix:** Replace the status-based check with a Loan Disbursement existence check:

```js
// Replace lines 17-22 with:
// Top-level: Send Disbursement Notice — show if any disbursement exists
frappe.db.count('Loan Disbursement', {
    filters: { against_loan: frm.doc.name, docstatus: 1 }
}).then(count => {
    if (count > 0) {
        frm.add_custom_button(__('Send Disbursement Notice'), function() {
            send_disbursement_notice(frm);
        });
    }
});
```

**Dependency:** `send_disbursement_notice()` (line 512) references `frm.doc.factory` and `frm.doc.home_build_request` — both require Chunk 1 to be completed first.

---

## Chunk 4: Plaid Link Token Error

### Task 8: Fix System Settings attribute error

**File:** `dcr/api/achq_integration.py` — line 768

**Problem:** `frappe.get_single("System Settings").company` — System Settings has no `company` attribute.

**Replace:**
```python
"client_name": frappe.get_single("System Settings").company or "Payment System",
```

**With:**
```python
"client_name": frappe.defaults.get_global_default("company") or "Dealer Capital Resources",
```

---

## Chunk 5: Auto-link ACH on Loan Creation

### Task 9: Add after_insert hook for ACH auto-linking

This logic should only run once (on Loan creation), not on every save. So it belongs in `after_insert`, separate from the field-copying in `on_loan_validate`.

**File:** `dcr/hooks.py` — update `doc_events`:

```python
doc_events = {
    "Loan Application": {
        "validate": "dcr.api.lending.validate_loan_application"
    },
    "Loan": {
        "validate": "dcr.api.lending.on_loan_validate",
        "after_insert": "dcr.api.lending.on_loan_after_insert"
    },
}
```

**File:** `dcr/api/lending.py` — add new function:

```python
def on_loan_after_insert(doc, method):
    """Auto-link ACH payment account or send Plaid setup email on loan creation."""
    if not doc.applicant:
        return

    # Check for existing ACH Authorization on this customer
    existing_auth = frappe.db.get_value(
        "ACH Authorization",
        {"customer": doc.applicant, "status": "Active", "is_default": 1},
        ["name", "bank_name", "bank_account_last4"],
        as_dict=True
    )

    if existing_auth:
        # Auto-link the existing default bank account to this loan
        doc.db_set("ach_payment_account", existing_auth.name, update_modified=False)
        frappe.msgprint(
            _("Auto-Pay linked to {0} ending in {1}").format(
                existing_auth.bank_name, existing_auth.bank_account_last4
            ),
            indicator="green",
            alert=True
        )
    else:
        # No bank account on file — send email with Plaid link
        send_plaid_setup_email(doc)


def send_plaid_setup_email(loan_doc):
    """Send dealer an email to connect their bank account via Plaid."""
    customer_email = frappe.db.get_value("Customer", loan_doc.applicant, "email_id")
    if not customer_email:
        frappe.log_error(
            f"Cannot send Plaid setup email: no email on Customer {loan_doc.applicant}",
            "ACH Setup"
        )
        return

    plaid_setup_url = frappe.utils.get_url(f"/plaid-setup?loan={loan_doc.name}")

    frappe.sendmail(
        recipients=[customer_email],
        subject=f"Set Up Auto-Pay for Loan {loan_doc.name}",
        template="plaid_setup",
        args={
            "customer_name": loan_doc.applicant_name or loan_doc.applicant,
            "loan_name": loan_doc.name,
            "loan_amount": loan_doc.loan_amount,
            "setup_url": plaid_setup_url
        },
        reference_doctype="Loan",
        reference_name=loan_doc.name
    )
```

**Prerequisite:** Create `plaid_setup` email template before deploying, or the sendmail call will error. Add as a sub-task.

**Note:** The Plaid setup portal page (`/plaid-setup`) is future work. The email will link to a placeholder for now. The auto-link logic for returning dealers works immediately.

---

## Chunk 6: LA Validation — Reject Draft HBRs

### Task 10: Add HBR docstatus check to existing validate_loan_application

**File:** `dcr/api/lending.py` — `validate_loan_application()` (line 45)

The function and hook registration already exist. Add HBR docstatus validation at the top of the function, before the balance calculations:

```python
def validate_loan_application(doc, method):
    """Hook called on Loan Application validate."""
    # Ensure linked HBR is submitted
    if doc.get("home_build_request"):
        hbr_status = frappe.db.get_value(
            "Home Build Request", doc.home_build_request, "docstatus"
        )
        if hbr_status != 1:
            frappe.throw(
                _("Home Build Request {0} must be submitted before linking to a Loan Application.").format(
                    doc.home_build_request
                )
            )

    # ... rest of existing function unchanged ...
```

**Also update fixture** — add `link_filters` to the `Loan Application-home_build_request` custom field (line 191) so the UI only shows submitted HBRs:

```json
"link_filters": "{\"docstatus\": 1}"
```

---

## Chunk 7: Auto-Create Supplier Quotation on HBR Submit

### Task 11: Add SQ creation to HBR on_submit

**File:** `dcr/dcr/doctype/home_build_request/home_build_request.py`

Update `on_submit` to create SQ for ALL deals, then LA for Floored only:

```python
def on_submit(self):
    # Create Supplier Quotation for all deals (floored + cash)
    self._create_supplier_quotation()

    # Create Loan Application for Floored deals only
    if self.financing_type == "Floored":
        self._create_loan_application()


def _create_supplier_quotation(self):
    """Auto-create Supplier Quotation from HBR on submit."""
    if not self.factory:
        frappe.msgprint(
            _("No factory assigned — Supplier Quotation not created."),
            indicator="orange"
        )
        return

    # Check for existing SQ
    existing = frappe.db.exists("Supplier Quotation", {
        "home_build_request": self.name,
        "docstatus": ["!=", 2]
    })
    if existing:
        frappe.msgprint(
            _("Supplier Quotation {0} already exists for this Home Build Request.").format(existing),
            indicator="orange"
        )
        return

    # Get the "Manufactured Home" item (must exist)
    item_code = "Manufactured Home"
    if not frappe.db.exists("Item", item_code):
        frappe.throw(
            _('Item "{0}" does not exist. Please create it first (non-stock service item).').format(
                item_code
            )
        )

    sq = frappe.new_doc("Supplier Quotation")
    sq.supplier = self.factory
    sq.home_build_request = self.name
    sq.company = frappe.defaults.get_global_default("company")

    # Add line item
    amount = self.home_invoice_plus_freight or 0
    sq.append("items", {
        "item_code": item_code,
        "qty": 1,
        "rate": amount,
        "amount": amount,
    })

    sq.insert()

    # Copy factory quote attachment from checklist if exists
    self._copy_factory_quote_to_sq(sq.name)

    # Link back
    self.db_set("factory_quote", sq.name)

    frappe.msgprint(
        _("Supplier Quotation {0} created.").format(
            f'<a href="/app/supplier-quotation/{sq.name}">{sq.name}</a>'
        ),
        indicator="green",
        alert=True,
    )


def _copy_factory_quote_to_sq(self, sq_name):
    """Copy the Factory Quote attachment from the HBR checklist to the SQ."""
    for row in self.doc_checklist:
        if row.document_type == "Factory Quote" and row.attach:
            try:
                frappe.get_doc({
                    "doctype": "File",
                    "file_url": row.attach,
                    "attached_to_doctype": "Supplier Quotation",
                    "attached_to_name": sq_name,
                }).insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(
                    f"Failed to copy factory quote attachment to SQ {sq_name}",
                    "HBR Submit"
                )
            break
```

**Note:** `factory_quote` is a native Link field on HBR (in `home_build_request.json`, line 110) pointing to Supplier Quotation. The `hasattr` check from the original plan is unnecessary — the field always exists.

### Task 12: Remove manual "Create → Supplier Quotation" button from HBR JS

**File:** `dcr/public/js/home_build_request.js` — lines 30-42

Remove the entire block:

```js
// Create → Supplier Quotation (submitted, no factory_quote linked, factory set)
if (frm.doc.docstatus === 1 && !frm.doc.factory_quote && frm.doc.factory) {
    frm.add_custom_button(__('Supplier Quotation'), function() {
        frappe.new_doc('Supplier Quotation', {
            supplier: frm.doc.factory,
            home_build_request: frm.doc.name
        });
    }, __('Create'));
    // Only primary if Loan Application button isn't showing
    if (!(frm.doc.financing_type === 'Floored' && !frm.doc.loan_application)) {
        frm.change_custom_button_type(__('Supplier Quotation'), __('Create'), 'primary');
    }
}
```

The Create group will still appear for the "Loan Application" fallback button on Floored deals.

---

## Cleanup: Remove sales_order_hooks.py

**File:** `dcr/api/sales_order_hooks.py` — DELETE

This file creates Loan Applications from Sales Orders, a feature that has been removed. The HBR on_submit path is now the only LA creation path.

**Also check `hooks.py`** for any Sales Order doc_events referencing this file and remove them. (Currently none exist in hooks.py — the file is orphaned.)

---

## Deployment Notes

After deploying to Frappe Cloud:
1. `bench migrate` runs automatically on app update
2. Verify "Manufactured Home" Item exists — create manually if not (non-stock service item)
3. Create `plaid_setup` email template (required by Task 9)
4. Test full chain: HBR submit → SQ auto-creates + LA auto-creates (Floored) → Loan → Disbursement
5. Verify factory/HBR fields flow through to Loan Disbursement

## Files Changed Summary

| File | Changes |
|---|---|
| `dcr/fixtures/custom_field.json` | Add `Loan Application-factory`, `Loan-home_build_request`; add `fetch_from` to 2 Loan Disbursement fields; add `link_filters` to LA-home_build_request |
| `dcr/hooks.py` | Add 2 fixture filter entries; add `after_insert` hook for Loan |
| `dcr/api/lending.py` | Extend `on_loan_validate`; add HBR validation to `validate_loan_application`; add `on_loan_after_insert` + `send_plaid_setup_email` |
| `dcr/dcr/doctype/home_build_request/home_build_request.py` | Set factory on LA in `_create_loan_application`; add `_create_supplier_quotation` + `_copy_factory_quote_to_sq`; update `on_submit` |
| `dcr/public/js/loan_application.js` | Add Create group button primary styling |
| `dcr/public/js/loan.js` | Replace status check with Loan Disbursement count |
| `dcr/public/js/home_build_request.js` | Remove manual SQ creation button |
| `dcr/api/achq_integration.py` | Fix Plaid client_name |
| `dcr/api/sales_order_hooks.py` | DELETE |
