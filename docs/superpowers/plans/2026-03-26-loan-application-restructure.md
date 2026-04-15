# Loan Application Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the Loan Application form layout, merge Exhibit A into Lending, add auto-calculations, fix bugs, and clean up field naming.

**Architecture:** Changes span 4 files: `custom_field.json` (reorder/add/remove custom fields), `property_setter.json` (hide/default standard fields, rename sections), `loan_application.js` (auto-calculations, link filters), and `lending.py` (update validate to use `loan_amount`). Also adds `space_rent` field to Park DocType and renames HBR field.

**Tech Stack:** Frappe v15, ERPNext + Lending module, deployed via Frappe Cloud

**Spec:** `/Users/tristanfleming/Downloads/loan-application-field-order.md`

**Standard field ordering constraint:** The Loan Application DocType is owned by the `lending` module. Standard fields cannot be reordered — only hidden, relabeled, or given defaults via Property Setters. Custom fields are positioned via `insert_after`. The plan achieves the spec's intent within these constraints.

**Standard Loan Application field order (for reference):**
```
applicant_type, applicant, applicant_name, column_break_2, company, posting_date, status,
section_break_4 ("Loan Info"), loan_product, is_term_loan, loan_amount, is_secured_loan, rate_of_interest,
column_break_7, description,
loan_security_details_section, proposed_pledges, maximum_loan_amount,
repayment_info, repayment_method, total_payable_amount, repayment_periods, repayment_amount, total_payable_interest,
amended_from
```

---

### Task 1: Park DocType — Add `space_rent` Field

**Files:**
- Modify: `dcr/dcr/doctype/park/park.json`

- [ ] **Step 1: Add space_rent to field_order**

In `park.json`, add `"space_rent"` to `field_order` after `"contact_name"` (header section, right column):

```json
"park_name",
"column_break_1",
"office_phone",
"contact_name",
"space_rent",
"address_section",
```

- [ ] **Step 2: Add field definition**

Add to the `fields` array after the `contact_name` field object:

```json
{
  "fieldname": "space_rent",
  "fieldtype": "Currency",
  "label": "Monthly Space Rent"
}
```

- [ ] **Step 3: Commit**

```
git add dcr/dcr/doctype/park/park.json
git commit -m "feat: add Monthly Space Rent field to Park DocType"
```

---

### Task 2: HBR — Rename `monthly_space_rent` to `park_space_rent` + Fetch

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`
- Modify: `dcr/fixtures/custom_field.json` (LA fetch_from reference)

The fetch chain is: Park.space_rent → HBR.park_space_rent → LA.custom_monthly_space_rent.

- [ ] **Step 1: Rename in HBR field_order and field definition**

In `home_build_request.json`:
- In `field_order`, change `"monthly_space_rent"` to `"park_space_rent"`
- In the `fields` array, update the field object:

```json
{
  "fetch_from": "park.space_rent",
  "fieldname": "park_space_rent",
  "fieldtype": "Currency",
  "label": "Monthly Space Rent",
  "read_only": 1
}
```

- [ ] **Step 2: Update LA fixture fetch_from**

In `custom_field.json`, find `Loan Application-custom_monthly_space_rent` and change:
- `fetch_from` from `"home_build_request.monthly_space_rent"` to `"home_build_request.park_space_rent"`

- [ ] **Step 3: Commit**

```
git add dcr/dcr/doctype/home_build_request/home_build_request.json dcr/fixtures/custom_field.json
git commit -m "feat: rename monthly_space_rent to park_space_rent with fetch chain from Park"
```

---

### Task 3: Custom Fields — Restructure LA Sections and Field Order

**Files:**
- Modify: `dcr/fixtures/custom_field.json`
- Modify: `dcr/hooks.py` (fixture filter list)

This is the largest task. It reorganizes the LA custom field layout.

#### Fields to REMOVE from custom_field.json:

| Name | Reason |
|------|--------|
| `Loan Application-dcr_lending_section` | Replaced by standard `section_break_4` (renamed to "Lending") |
| `Loan Application-requested_advance_amount` | Replaced by standard `loan_amount` |
| `Loan Application-column_break_dcr_lending` | No longer needed; standard `column_break_7` + new `column_break_lending_calc` |
| `Loan Application-exhibit_a_section` | Merged into Lending section |
| `Loan Application-column_break_exhibit_a` | Merged into Lending section |
| `Loan Application-first_autopay_description` | Hardcoded in print format |
| `Loan Application-custom_projected_investment` | Equals `loan_amount`; use that directly |

#### Fields to ADD to custom_field.json:

```json
{
  "doctype": "Custom Field",
  "name": "Loan Application-lending_calculations_section",
  "dt": "Loan Application",
  "fieldname": "lending_calculations_section",
  "fieldtype": "Section Break",
  "label": "Lending Calculations",
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
  "label": "Signed Documents",
  "insert_after": "custom_notes"
}
```

#### Fields to UPDATE (insert_after, labels, properties):

| Field | Changes |
|-------|---------|
| `deal_reference_section` | `insert_after` → `"status"` (was `"applicant_name"`) |
| `advance_date_requested` | `insert_after` → `"rate_of_interest"` (was `"requested_advance_amount"`), `label` → `"Advance Date"` |
| `home_serial_no` | `insert_after` → `"advance_date_requested"` (was `"exhibit_a_section"`) |
| `quote_no` | `insert_after` → `"home_serial_no"` (unchanged) |
| `floor_plan` | `insert_after` → `"quote_no"` (unchanged), `label` → `"Model"` (was `"Floor Plan"`) |
| `buyer_name` | `insert_after` → `"description"` (was `"column_break_exhibit_a"`), `label` → `"Buyer Name"` (was `"Buyer Name (End Customer)"`), remove `description` property |
| `available_credit` | `insert_after` → `"lending_calculations_section"` (was `"outstanding_loan_balance"`) |
| `outstanding_loan_balance` | `insert_after` → `"available_credit"` (was `"column_break_dcr_lending"`) |
| `custom_current_yn` | `insert_after` → `"outstanding_loan_balance"` (was `"advance_preapproval_section"`), `label` → `"Current"` (was `"Current Y/N"`) |
| `monthly_interest_amount` | `insert_after` → `"column_break_lending_calc"` (was `"buyer_name"`), add `read_only: 1` |
| `monthly_insurance_amount` | `insert_after` → `"monthly_interest_amount"` (unchanged) |
| `advance_preapproval_section` | `insert_after` → `"maximum_loan_amount"` (was `"first_autopay_description"`), `label` → `"Pre-Approval Letter"` (was `"Advance Pre-Approval"`) |
| `custom_projected_sales_price` | `insert_after` → `"advance_preapproval_section"` (was `"custom_projected_investment"`), add `fetch_from: "home_build_request.selling_price"`, add `fetch_if_empty: 1` |
| `custom_projected_equity` | `insert_after` → `"custom_projected_sales_price"` (was `"column_break_preapproval"`), add `read_only: 1` |
| `custom_projected_ltv` | `insert_after` → `"custom_projected_equity"` (unchanged), add `read_only: 1` |
| `custom_projected_payoff` | `insert_after` → `"custom_projected_ltv"` (was `"custom_monthly_space_rent"`) |
| `column_break_preapproval` | `insert_after` → `"custom_projected_payoff"` (was `"custom_projected_sales_price"`) |
| `custom_monthly_space_rent` | `insert_after` → `"column_break_preapproval"` (unchanged), add `read_only: 1` |
| `custom_notes` | `insert_after` → `"custom_monthly_space_rent"` (unchanged) |
| `signed_packet` | `insert_after` → `"dcr_documents_section"` (was `"doc_checklist"`) |

#### Complete insert_after chain (for verification):

```
status → deal_reference_section → home_build_request → home_type → column_break_deal_ref → factory
[standard: section_break_4, loan_product, is_term_loan(H), loan_amount, is_secured_loan(H), rate_of_interest]
rate_of_interest → advance_date_requested → home_serial_no → quote_no → floor_plan
[standard: column_break_7, description(H)]
description → buyer_name
buyer_name → lending_calculations_section → available_credit → outstanding_loan_balance → custom_current_yn → column_break_lending_calc → monthly_interest_amount → monthly_insurance_amount
[standard: loan_security_details_section(H), proposed_pledges(H), maximum_loan_amount(H)]
maximum_loan_amount → advance_preapproval_section → custom_projected_sales_price → custom_projected_equity → custom_projected_ltv → custom_projected_payoff → column_break_preapproval → custom_monthly_space_rent → custom_notes
custom_notes → dcr_documents_section → signed_packet
[standard: repayment_info, repayment_method(H), total_payable_amount, repayment_periods(H), repayment_amount, total_payable_interest, amended_from]
```

- [ ] **Step 1: Remove 7 custom field entries from custom_field.json**

Delete the JSON objects for:
- `Loan Application-dcr_lending_section`
- `Loan Application-requested_advance_amount`
- `Loan Application-column_break_dcr_lending`
- `Loan Application-exhibit_a_section`
- `Loan Application-column_break_exhibit_a`
- `Loan Application-first_autopay_description`
- `Loan Application-custom_projected_investment`

- [ ] **Step 2: Add 3 new custom field entries to custom_field.json**

Add `lending_calculations_section`, `column_break_lending_calc`, and `dcr_documents_section` as shown above.

- [ ] **Step 3: Update all remaining custom field entries**

Update `insert_after`, `label`, `read_only`, `fetch_from`, `fetch_if_empty`, and `description` properties as listed in the update table above.

- [ ] **Step 4: Update hooks.py fixture filter list**

In `hooks.py`, update the Custom Field fixture filter list:

Remove these 7 names:
```
"Loan Application-dcr_lending_section",
"Loan Application-requested_advance_amount",
"Loan Application-column_break_dcr_lending",
"Loan Application-exhibit_a_section",
"Loan Application-column_break_exhibit_a",
"Loan Application-first_autopay_description",
"Loan Application-custom_projected_investment",
```

Add these 3 names:
```
"Loan Application-lending_calculations_section",
"Loan Application-column_break_lending_calc",
"Loan Application-dcr_documents_section",
```

- [ ] **Step 5: Commit**

```
git add dcr/fixtures/custom_field.json dcr/hooks.py
git commit -m "feat: restructure LA custom fields — merge Exhibit A into Lending, add Lending Calculations section"
```

---

### Task 4: Property Setters — Hide/Default/Rename Standard LA Fields

**Files:**
- Modify: `dcr/fixtures/property_setter.json`
- Modify: `dcr/hooks.py` (Property Setter fixture filter list)

#### Property Setters to create:

| Name | Field | Property | Value | Notes |
|------|-------|----------|-------|-------|
| `Loan Application-section_break_4-label` | section_break_4 | label | Lending | Rename "Loan Info" → "Lending" |
| `Loan Application-is_term_loan-hidden` | is_term_loan | hidden | 1 | Hide |
| `Loan Application-is_secured_loan-hidden` | is_secured_loan | hidden | 1 | Hide |
| `Loan Application-description-hidden` | description | hidden | 1 | Hide "Reason" field |
| `Loan Application-loan_security_details_section-hidden` | loan_security_details_section | hidden | 1 | Hide entire section |
| `Loan Application-proposed_pledges-hidden` | proposed_pledges | hidden | 1 | Hide |
| `Loan Application-maximum_loan_amount-hidden` | maximum_loan_amount | hidden | 1 | Hide |
| `Loan Application-repayment_method-hidden` | repayment_method | hidden | 1 | Hide |
| `Loan Application-repayment_method-default` | repayment_method | default | Repay Over Number of Periods | Default |
| `Loan Application-repayment_periods-hidden` | repayment_periods | hidden | 1 | Hide |
| `Loan Application-repayment_periods-default` | repayment_periods | default | 12 | Default |
| `Loan Application-applicant_type-hidden` | applicant_type | hidden | 1 | Hide |
| `Loan Application-applicant_type-default` | applicant_type | default | Customer | Default |
| `Loan Application-loan_amount-fetch_from` | loan_amount | fetch_from | home_build_request.home_invoice_plus_freight | Auto-fill from HBR quoted amount |
| `Loan Application-loan_amount-fetch_if_empty` | loan_amount | fetch_if_empty | 1 | Only fetch if empty |

- [ ] **Step 1: Add Property Setter entries to property_setter.json**

Read `dcr/fixtures/property_setter.json`. Add all 15 Property Setter entries. Each entry follows this format:

```json
{
  "doctype": "Property Setter",
  "name": "Loan Application-{field}-{property}",
  "doc_type": "Loan Application",
  "field_name": "{field}",
  "property": "{property}",
  "property_type": "Check|Data|Small Text",
  "value": "{value}"
}
```

Use `property_type: "Check"` for hidden, `"Small Text"` for default/fetch_from, `"Data"` for label.

- [ ] **Step 2: Update hooks.py Property Setter filter list**

Add all 15 new Property Setter names to the Property Setter fixture filter in `hooks.py`.

- [ ] **Step 3: Commit**

```
git add dcr/fixtures/property_setter.json dcr/hooks.py
git commit -m "feat: Property Setters — hide/default standard LA fields, rename Loan Info to Lending"
```

---

### Task 5: JS — Auto-Calculations and Link Filters

**Files:**
- Modify: `dcr/public/js/loan_application.js`

#### 5a: HBR link filter (fix "HBR link does not work on blank LA")

Add `set_query` for `home_build_request` in the `refresh` handler, BEFORE the `docstatus !== 1` early return:

```javascript
frm.set_query('home_build_request', function() {
    return {
        filters: {
            'docstatus': 1
        }
    };
});
```

This ensures the link field only shows submitted HBRs and works on new (unsaved) LAs.

#### 5b: Monthly interest amount calculation

Add handlers for `loan_amount` and `rate_of_interest` changes:

```javascript
loan_amount: function(frm) {
    calculate_monthly_interest(frm);
    calculate_preapproval(frm);
},
rate_of_interest: function(frm) {
    calculate_monthly_interest(frm);
},
custom_projected_sales_price: function(frm) {
    calculate_preapproval(frm);
},
```

Add helper functions:

```javascript
function calculate_monthly_interest(frm) {
    let rate = frm.doc.rate_of_interest || 0;
    let amount = frm.doc.loan_amount || 0;
    frm.set_value('monthly_interest_amount', (rate / 100) * amount / 12);
}

function calculate_preapproval(frm) {
    let sales_price = frm.doc.custom_projected_sales_price || 0;
    let loan_amount = frm.doc.loan_amount || 0;
    if (sales_price > 0) {
        frm.set_value('custom_projected_equity', sales_price - loan_amount);
        frm.set_value('custom_projected_ltv', (loan_amount / sales_price) * 100);
    }
}
```

**Note:** `outstanding_loan_balance`, `available_credit`, and `custom_current_yn` are already calculated server-side in `validate_loan_application`. The spec wants them on form load too. This would require a whitelisted server method called from JS. However, the current Python validate already handles this — the fields update on save. Leave this as server-side-only for now; client-side calculation would require a new API endpoint.

- [ ] **Step 1: Add set_query for home_build_request in refresh handler**

Place it at the top of the `refresh` function, before the signing status indicator block.

- [ ] **Step 2: Add loan_amount, rate_of_interest, custom_projected_sales_price handlers**

Add them as properties in the `frappe.ui.form.on('Loan Application', { ... })` block.

- [ ] **Step 3: Add calculate_monthly_interest and calculate_preapproval helper functions**

Add them as standalone functions after the existing `send_pre_approval` function.

- [ ] **Step 4: Commit**

```
git add dcr/public/js/loan_application.js
git commit -m "feat: add auto-calculations and HBR link filter to Loan Application JS"
```

---

### Task 6: Python — Update `validate_loan_application`

**Files:**
- Modify: `dcr/api/lending.py`

#### Changes:

1. Update the credit warning to use `loan_amount` instead of `requested_advance_amount`:

```python
# Change this line:
requested = doc.get("requested_advance_amount") or doc.get("loan_amount") or 0
# To:
requested = doc.get("loan_amount") or 0
```

2. Update pre-approval calculation to use `loan_amount` instead of `custom_projected_investment`:

```python
# Change:
investment = doc.get("custom_projected_investment") or 0
sales_price = doc.get("custom_projected_sales_price") or 0
if investment and sales_price:
    doc.custom_projected_equity = sales_price - investment
    doc.custom_projected_ltv = (investment / sales_price) * 100

# To:
loan_amount = doc.get("loan_amount") or 0
sales_price = doc.get("custom_projected_sales_price") or 0
if loan_amount and sales_price:
    doc.custom_projected_equity = sales_price - loan_amount
    doc.custom_projected_ltv = (loan_amount / sales_price) * 100
```

3. Add monthly interest calculation:

```python
# After the pre-approval calculation:
rate = doc.get("rate_of_interest") or 0
if rate and loan_amount:
    doc.monthly_interest_amount = (rate / 100) * loan_amount / 12
```

- [ ] **Step 1: Read lending.py and make the changes**

- [ ] **Step 2: Commit**

```
git add dcr/api/lending.py
git commit -m "fix: update LA validate to use loan_amount, fix pre-approval calcs"
```

---

### Task 7: Print Format Updates

**Files:**
- Modify: `dcr/dcr/print_format/advance_pre_approval/advance_pre_approval.json`
- Modify: `dcr/dcr/print_format/ach_recurring_payment_authorization/ach_recurring_payment_authorization.json`

#### Advance Pre-Approval print format:

Two references to removed fields need updating in the Jinja `html`:

1. **`custom_projected_investment`** — In the Spec variant "Key Information" table:
   - Change `doc.custom_projected_investment or 0` → `doc.loan_amount or 0`
   - The label "Projected investment" can stay (it's the print format's label, not a field label)

2. **`requested_advance_amount`** — Two references:
   - In "Projected advance amount": change `doc.requested_advance_amount or doc.loan_amount or 0` → `doc.loan_amount or 0`
   - In "Loan-to-value" (Sold variant): change `doc.requested_advance_amount / hbr.selling_price * 100` → `doc.loan_amount / hbr.selling_price * 100`
   - Also update the condition: `doc.requested_advance_amount` → `doc.loan_amount`

#### ACH print format:

The `first_autopay_description` reference already has a fallback:
```
doc.first_autopay_description or '30 days after the earlier of funding...'
```
Once the field is removed, the fallback text will always render. **No change strictly needed**, but for cleanliness, simplify to just the hardcoded text:
```
30 days after the earlier of funding of the loan or factory invoice date of the home.
```

- [ ] **Step 1: Update Advance Pre-Approval print format**

Replace `custom_projected_investment` and `requested_advance_amount` references with `loan_amount`.

- [ ] **Step 2: Update ACH print format**

Replace the `doc.first_autopay_description or '...'` with just the hardcoded fallback text.

- [ ] **Step 3: Commit**

```
git add dcr/dcr/print_format/advance_pre_approval/advance_pre_approval.json dcr/dcr/print_format/ach_recurring_payment_authorization/ach_recurring_payment_authorization.json
git commit -m "fix: update print formats to use loan_amount, remove references to deleted fields"
```

---

### Task 8: Verification

- [ ] **Step 1: Verify custom_field.json**

Read the full file and confirm:
- 7 removed fields are gone
- 3 new fields are present with correct properties
- All insert_after values form a valid chain (no orphans, no cycles)
- Labels match spec: "Model", "Buyer Name", "Current", "Pre-Approval Letter", "Lending Calculations", "Signed Documents", "Advance Date"
- fetch_from values: custom_projected_sales_price → home_build_request.selling_price, custom_monthly_space_rent → home_build_request.park_space_rent
- read_only flags on: monthly_interest_amount, custom_projected_equity, custom_projected_ltv, custom_monthly_space_rent

- [ ] **Step 2: Verify hooks.py**

Confirm fixture filter lists match the custom fields and property setters that exist in the fixture files.

- [ ] **Step 3: Verify property_setter.json**

Confirm all 15 property setters are present with correct doc_type, field_name, property, value.

- [ ] **Step 4: Verify JS**

Read loan_application.js and confirm:
- set_query for home_build_request (docstatus: 1)
- loan_amount handler calls calculate_monthly_interest + calculate_preapproval
- rate_of_interest handler calls calculate_monthly_interest
- custom_projected_sales_price handler calls calculate_preapproval
- Both helper functions have correct formulas

- [ ] **Step 5: Verify Python**

Read lending.py and confirm:
- No references to `requested_advance_amount` or `custom_projected_investment`
- Pre-approval calc uses `loan_amount`
- Monthly interest calc is present

- [ ] **Step 6: Verify Park and HBR**

- Park.json has `space_rent` field
- HBR.json has `park_space_rent` with `fetch_from: "park.space_rent"` and `read_only: 1`
