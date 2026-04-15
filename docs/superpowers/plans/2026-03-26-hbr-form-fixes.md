# HBR Form Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix field ordering, labels, filters, and layout issues on the Home Build Request form discovered during Goldey deal testing.

**Architecture:** All changes are to DocType JSON files (field order, labels, properties), one JS file (link filters, escrow contact fetch), and custom_field.json fixtures (Title Case fixes). No schema migrations — Frappe handles field reordering and label changes on deploy.

**Tech Stack:** Frappe v15, ERPNext + Lending module, deployed via Frappe Cloud

**Spec:** `/Users/tristanfleming/Downloads/2026-03-26-hbr-form-fixes.md`

---

### Task 1: Title Case — Fix "Deal reference" Across All DocTypes

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json` (line 111)
- Modify: `dcr/fixtures/custom_field.json` (3 occurrences of "Deal reference")

- [ ] **Step 1: Fix HBR section label**

In `home_build_request.json`, change the `home_section` field label from `"Deal reference"` to `"Deal Reference"`.

- [ ] **Step 2: Fix custom_field.json — Loan Application, Loan, Loan Disbursement**

In `custom_field.json`, find all three `"Deal reference"` labels and change to `"Deal Reference"`:
- `Loan Application-deal_reference_section`
- `Loan Disbursement-deal_reference_section`
- `Loan-home_deal_reference_section`

- [ ] **Step 3: Commit**

```
git add dcr/dcr/doctype/home_build_request/home_build_request.json dcr/fixtures/custom_field.json
git commit -m "fix: Title Case section headers — Deal Reference across all DocTypes"
```

---

### Task 2: Deal Reference Section — Field Reordering, Labels, Read-Only

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`

**Current field_order in Deal Reference section:**
```
home_section, factory, model_name, home_invoice_plus_freight, column_break_home, home_serial_no, quote_no
```

**Target field_order:**
```
home_section, model_name, home_serial_no, column_break_home, factory, quote_no, home_invoice_plus_freight
```

- [ ] **Step 1: Update field_order array**

In `home_build_request.json`, replace the Deal Reference portion of `field_order` (lines 15-20):

From:
```json
"factory",
"model_name",
"home_invoice_plus_freight",
"column_break_home",
"home_serial_no",
"quote_no",
```

To:
```json
"model_name",
"home_serial_no",
"column_break_home",
"factory",
"quote_no",
"home_invoice_plus_freight",
```

- [ ] **Step 2: Set Factory read_only**

In the `factory` field object, add `"read_only": 1`.

- [ ] **Step 3: Rename labels**

- `quote_no` field: change label from `"Quote No"` to `"Factory Quote No"`
- `home_invoice_plus_freight` field: change label from `"Home Total"` to `"Quoted Amount"`
- `home_serial_no` field: change label from `"Home Serial No"` to `"Serial No"`

- [ ] **Step 4: Commit**

```
git add dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "feat: reorder Deal Reference section — Model first, Factory read-only, rename labels"
```

---

### Task 3: Hide Status Field

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`

The `status` field (Select: Draft/Submitted, read_only) duplicates `docstatus`. No logic depends on it beyond list_view display.

- [ ] **Step 1: Hide the status field**

Add `"hidden": 1` to the `status` field object. Keep `in_list_view` and `in_standard_filter` so it still works in list views.

- [ ] **Step 2: Commit**

```
git add dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "fix: hide redundant status field from HBR form"
```

---

### Task 4: Document Checklist — Move Waived Column to Last

**Files:**
- Modify: `dcr/dcr/doctype/document_checklist/document_checklist.json`

**Current field_order:**
```json
["document_type", "waived", "column_break_1", "attachment", "received_date"]
```

**Target field_order:**
```json
["document_type", "column_break_1", "attachment", "received_date", "waived"]
```

- [ ] **Step 1: Update field_order**

Move `"waived"` from position 2 to the end of the array.

- [ ] **Step 2: Commit**

```
git add dcr/dcr/doctype/document_checklist/document_checklist.json
git commit -m "fix: move Waived column to last position in Document Checklist"
```

---

### Task 5: Financials Section — Layout Restructure and Rename

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`

**Current field_order in Financials section:**
```
financials_section, customer_deposit, selling_price, column_break_financials, end_buyer_lender
```

**Target field_order:**
```
financials_section, end_buyer_lender, column_break_financials, selling_price, customer_deposit
```

Left column: Financing Source (alone). Right column: Selling Price, then Deposit In Escrow.

- [ ] **Step 1: Update field_order**

Replace the Financials portion of `field_order`:

From:
```json
"customer_deposit",
"selling_price",
"column_break_financials",
"end_buyer_lender",
```

To:
```json
"end_buyer_lender",
"column_break_financials",
"selling_price",
"customer_deposit",
```

- [ ] **Step 2: Rename labels**

- `end_buyer_lender`: change label from `"Lender"` to `"Financing Source"`
- `customer_deposit`: change label from `"Customer Deposit in Escrow"` to `"Deposit In Escrow"`
- `selling_price`: change label from `"Selling Price of Home"` to `"Selling Price"`

- [ ] **Step 3: Commit**

```
git add dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "feat: restructure Financials section — Financing Source left, prices right"
```

---

### Task 6: Home Buyer Link Filter

**Files:**
- Modify: `dcr/public/js/home_build_request.js`

**Note:** The "Home Buyer" Customer Group already exists — created by `dcr/setup.py:after_install` (line 22), which runs on every `after_migrate`. No fixture work needed.

- [ ] **Step 1: Add set_query for home_buyer in JS**

In `home_build_request.js`, inside the `refresh` handler (after the factory filter block), add:

```javascript
frm.set_query('home_buyer', function() {
    return {
        filters: {
            'customer_group': 'Home Buyer'
        }
    };
});
```

- [ ] **Step 3: Commit**

```
git add dcr/public/js/home_build_request.js
git commit -m "feat: filter Home Buyer field to Home Buyer customer group"
```

---

### Task 7: Escrow Company Link Filter + Contact Auto-Fetch

**Files:**
- Modify: `dcr/public/js/home_build_request.js`

- [ ] **Step 1: Add set_query for escrow_company in JS**

In `home_build_request.js`, inside the `refresh` handler, add:

```javascript
frm.set_query('escrow_company', function() {
    return {
        filters: {
            'supplier_group': 'Escrow'
        }
    };
});
```

- [ ] **Step 2: Add escrow_company onchange handler**

Add a new handler in the `frappe.ui.form.on('Home Build Request', { ... })` block.

**Important:** Frappe Contact uses a Dynamic Link child table — you cannot filter Contact directly by `link_doctype`/`link_name`. Query the `Dynamic Link` child table first to find the Contact parent, then fetch contact details.

```javascript
escrow_company: function(frm) {
    if (!frm.doc.escrow_company) {
        frm.set_value('escrow_contact', '');
        frm.set_value('escrow_phone', '');
        return;
    }
    // Step 1: Find Contact via Dynamic Link child table
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Dynamic Link',
            filters: {
                parenttype: 'Contact',
                link_doctype: 'Supplier',
                link_name: frm.doc.escrow_company
            },
            fields: ['parent'],
            limit_page_length: 1
        },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                // Step 2: Fetch contact details
                frappe.db.get_value('Contact', r.message[0].parent,
                    ['first_name', 'last_name', 'mobile_no', 'phone'],
                    function(contact) {
                        let name = contact.first_name || '';
                        if (contact.last_name) name += ' ' + contact.last_name;
                        frm.set_value('escrow_contact', name.trim());
                        frm.set_value('escrow_phone', contact.mobile_no || contact.phone || '');
                    }
                );
            }
        }
    });
},
```

- [ ] **Step 3: Commit**

```
git add dcr/public/js/home_build_request.js
git commit -m "feat: filter Escrow Company to Escrow supplier group, auto-fetch contact"
```

---

### Task 8: Broker Section — Remove Collapsible

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`

- [ ] **Step 1: Set collapsible to 0**

In the `broker_section` field object, change `"collapsible": 1` to `"collapsible": 0`.

- [ ] **Step 2: Commit**

```
git add dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "fix: make Broker section always visible (not collapsible)"
```

---

### Task 9: Verification

- [ ] **Step 1: Review all HBR JSON changes holistically**

Read the final `home_build_request.json` and verify:
- field_order matches expected layout
- All section labels are Title Case
- Factory is read_only
- Status is hidden
- Broker is not collapsible
- Labels renamed correctly

- [ ] **Step 2: Review JS changes**

Read the final `home_build_request.js` and verify:
- `home_buyer` filter is present
- `escrow_company` filter is present
- `escrow_company` onchange handler fetches contact

- [ ] **Step 3: Review custom_field.json**

Verify all "Deal reference" → "Deal Reference" changes in fixture file.

- [ ] **Step 4: Verify downstream fetch_from chains are unbroken**

Confirm in `custom_field.json` that these fetch_from references still use the correct fieldnames (fieldnames did NOT change, only labels):
- `home_build_request.home_invoice_plus_freight` (label changed to "Quoted Amount" — fetch_from uses fieldname, unaffected)
- `home_build_request.quote_no` (label changed to "Factory Quote No" — fetch_from uses fieldname, unaffected)
- `home_build_request.home_serial_no` (label changed to "Serial No" — fetch_from uses fieldname, unaffected)
- `home_build_request.factory` (now read_only — fetch_from unaffected)

- [ ] **Step 5: Final commit if any fixups needed**
