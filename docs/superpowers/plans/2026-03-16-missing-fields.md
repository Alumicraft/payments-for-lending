# Missing Fields Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add all fields that print formats assume but don't yet exist — one new Park doctype, new fields on HBR and MIFA, new custom fields on Loan Application and Customer, and new Supplier/Customer groups.

**Architecture:** Declarative-only changes — doctype JSON edits for custom doctypes (Park, HBR, MIFA), fixture entries for standard doctypes (Loan Application, Customer), and setup.py for group creation. No Python logic changes. All custom fields use Frappe's `custom_field.json` fixture pattern already established in the codebase.

**Tech Stack:** Frappe v15, ERPNext, Lending module, Frappe Cloud deployment

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `dcr/dcr/doctype/park/park.json` | Park doctype definition |
| Create | `dcr/dcr/doctype/park/park.py` | Park controller (minimal) |
| Create | `dcr/dcr/doctype/park/__init__.py` | Package init |
| Modify | `dcr/dcr/doctype/home_build_request/home_build_request.json` | Add Park, Buyer, Escrow, Home Info sections |
| Modify | `dcr/dcr/doctype/mifa/mifa.json` | Add entity_type, effective_date, dealer_signer_title |
| Modify | `dcr/fixtures/custom_field.json` | Add Loan Application + Customer custom fields |
| Modify | `dcr/setup.py` | Create Escrow supplier group + Home Buyer customer group |

---

## Chunk 1: Park Doctype + HBR Fields + MIFA Fields

### Task 1: Create Park Doctype

**Files:**
- Create: `dcr/dcr/doctype/park/__init__.py`
- Create: `dcr/dcr/doctype/park/park.py`
- Create: `dcr/dcr/doctype/park/park.json`

- [ ] **Step 1: Create the Park doctype directory**

```bash
mkdir -p dcr/dcr/doctype/park
```

- [ ] **Step 2: Create `__init__.py`**

Create empty file: `dcr/dcr/doctype/park/__init__.py`

- [ ] **Step 3: Create `park.py`**

```python
import frappe
from frappe.model.document import Document


class Park(Document):
	pass
```

- [ ] **Step 4: Create `park.json`**

```json
{
 "actions": [],
 "autoname": "field:park_name",
 "creation": "2024-01-01 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "park_name",
  "column_break_1",
  "office_phone",
  "contact_name",
  "address_section",
  "address",
  "city_state_zip",
  "access_section",
  "gated",
  "access_code"
 ],
 "fields": [
  {
   "fieldname": "park_name",
   "fieldtype": "Data",
   "label": "Park Name",
   "reqd": 1,
   "unique": 1,
   "in_list_view": 1
  },
  {
   "fieldname": "column_break_1",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "office_phone",
   "fieldtype": "Data",
   "label": "Office Phone",
   "options": "Phone"
  },
  {
   "fieldname": "contact_name",
   "fieldtype": "Data",
   "label": "Contact Name"
  },
  {
   "fieldname": "address_section",
   "fieldtype": "Section Break",
   "label": "Address"
  },
  {
   "fieldname": "address",
   "fieldtype": "Data",
   "label": "Address"
  },
  {
   "fieldname": "city_state_zip",
   "fieldtype": "Data",
   "label": "City, St Zip"
  },
  {
   "fieldname": "access_section",
   "fieldtype": "Section Break",
   "label": "Access"
  },
  {
   "fieldname": "gated",
   "fieldtype": "Check",
   "label": "Gated Community"
  },
  {
   "fieldname": "access_code",
   "fieldtype": "Data",
   "label": "Access Code",
   "depends_on": "gated"
  }
 ],
 "index_web_pages_for_search": 1,
 "links": [],
 "modified": "2024-01-01 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "DCR",
 "name": "Park",
 "naming_rule": "By fieldname",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "delete": 1,
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "System Manager",
   "share": 1,
   "write": 1
  },
  {
   "create": 1,
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "Accounts Manager",
   "share": 1,
   "write": 1
  }
 ],
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 1
}
```

- [ ] **Step 5: Commit**

```bash
git add dcr/dcr/doctype/park/
git commit -m "feat: add Park doctype for mobile home parks/communities"
```

---

### Task 2: Add New Fields to Home Build Request

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`

The HBR currently has these fields in `field_order`:
```
customer, home_name, status, column_break_1, home_type, financing_type, property_type,
references_section, factory, factory_quote, column_break_refs, sales_order, loan_application,
documents_section, doc_checklist
```

We add 4 new sections between `loan_application` and `documents_section`:
1. **Park Section** (depends_on: property_type == "Park")
2. **Buyer Section** (depends_on: home_type == "Customer Sold")
3. **Escrow Section** (depends_on: home_type == "Customer Sold")
4. **Home Info Section** (always shown)

- [ ] **Step 1: Add new fields to `field_order` array**

Insert these entries after `"loan_application"` and before `"documents_section"`:

```json
"park_section",
"park",
"space_number",
"buyer_section",
"home_buyer",
"escrow_section",
"escrow_company",
"escrow_number",
"column_break_escrow",
"escrow_contact",
"escrow_phone",
"escrow_financials_section",
"customer_deposit",
"selling_price",
"column_break_escrow_fin",
"end_buyer_lender",
"broker_section",
"broker",
"column_break_broker",
"broker_contact",
"broker_phone",
"home_info_section",
"model_name",
"column_break_home_info",
"home_invoice_plus_freight",
```

- [ ] **Step 2: Add the field definitions to the `fields` array**

Insert these field objects after the `loan_application` field and before the `documents_section` field:

```json
{
 "fieldname": "park_section",
 "fieldtype": "Section Break",
 "label": "Park",
 "depends_on": "eval:doc.property_type=='Park'"
},
{
 "fieldname": "park",
 "fieldtype": "Link",
 "label": "Park",
 "options": "Park"
},
{
 "fieldname": "space_number",
 "fieldtype": "Data",
 "label": "Space #"
},
{
 "fieldname": "buyer_section",
 "fieldtype": "Section Break",
 "label": "Buyer",
 "depends_on": "eval:doc.home_type=='Customer Sold'"
},
{
 "fieldname": "home_buyer",
 "fieldtype": "Link",
 "label": "Home Buyer",
 "options": "Customer"
},
{
 "fieldname": "escrow_section",
 "fieldtype": "Section Break",
 "label": "Escrow",
 "depends_on": "eval:doc.home_type=='Customer Sold'"
},
{
 "fieldname": "escrow_company",
 "fieldtype": "Link",
 "label": "Escrow Company",
 "options": "Supplier"
},
{
 "fieldname": "escrow_number",
 "fieldtype": "Data",
 "label": "Escrow Number"
},
{
 "fieldname": "column_break_escrow",
 "fieldtype": "Column Break"
},
{
 "fieldname": "escrow_contact",
 "fieldtype": "Data",
 "label": "Escrow Contact"
},
{
 "fieldname": "escrow_phone",
 "fieldtype": "Data",
 "label": "Escrow Phone",
 "options": "Phone"
},
{
 "fieldname": "escrow_financials_section",
 "fieldtype": "Section Break",
 "label": "Escrow Financials",
 "depends_on": "eval:doc.home_type=='Customer Sold'"
},
{
 "fieldname": "customer_deposit",
 "fieldtype": "Currency",
 "label": "Customer Deposit in Escrow"
},
{
 "fieldname": "selling_price",
 "fieldtype": "Currency",
 "label": "Selling Price of Home"
},
{
 "fieldname": "column_break_escrow_fin",
 "fieldtype": "Column Break"
},
{
 "fieldname": "end_buyer_lender",
 "fieldtype": "Data",
 "label": "Lender",
 "description": "Buyer's financing source (e.g. Cash, FHA, Wells Fargo)"
},
{
 "fieldname": "broker_section",
 "fieldtype": "Section Break",
 "label": "Broker",
 "depends_on": "eval:doc.home_type=='Customer Sold'",
 "collapsible": 1
},
{
 "fieldname": "broker",
 "fieldtype": "Data",
 "label": "Broker"
},
{
 "fieldname": "column_break_broker",
 "fieldtype": "Column Break"
},
{
 "fieldname": "broker_contact",
 "fieldtype": "Data",
 "label": "Broker Contact"
},
{
 "fieldname": "broker_phone",
 "fieldtype": "Data",
 "label": "Broker Phone",
 "options": "Phone"
},
{
 "fieldname": "home_info_section",
 "fieldtype": "Section Break",
 "label": "Home Info"
},
{
 "fieldname": "model_name",
 "fieldtype": "Data",
 "label": "Model"
},
{
 "fieldname": "column_break_home_info",
 "fieldtype": "Column Break"
},
{
 "fieldname": "home_invoice_plus_freight",
 "fieldtype": "Currency",
 "label": "Home Invoice plus Freight"
}
```

- [ ] **Step 3: Commit**

```bash
git add dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "feat: add Park, Buyer, Escrow, and Home Info sections to HBR"
```

---

### Task 3: Add New Fields to MIFA

**Files:**
- Modify: `dcr/dcr/doctype/mifa/mifa.json`

Add 3 fields. Insert `entity_type` and `effective_date` after `interest_rate` (before `terms_section`), and `dealer_signer_title` after `signed_mifa`.

- [ ] **Step 1: Update `field_order`**

Current:
```json
"customer", "mifa_date", "column_break_1", "credit_limit", "interest_rate",
"terms_section", "payment_terms", "signature_section", "signed_mifa"
```

New:
```json
"customer", "mifa_date", "column_break_1", "credit_limit", "interest_rate",
"entity_type", "effective_date",
"terms_section", "payment_terms", "signature_section", "signed_mifa",
"dealer_signer_title"
```

- [ ] **Step 2: Add field definitions**

Insert after `interest_rate` field:

```json
{
 "fieldname": "entity_type",
 "fieldtype": "Select",
 "label": "Entity Type",
 "options": "\nLLC\nCorporation\nPartnership\nTrust",
 "description": "Can also be fetched from Customer.entity_type"
},
{
 "fieldname": "effective_date",
 "fieldtype": "Date",
 "label": "Effective Date",
 "description": "Effective date of agreement (may differ from MIFA date)"
}
```

Insert after `signed_mifa` field:

```json
{
 "fieldname": "dealer_signer_title",
 "fieldtype": "Data",
 "label": "Dealer Signer Title"
}
```

- [ ] **Step 3: Commit**

```bash
git add dcr/dcr/doctype/mifa/mifa.json
git commit -m "feat: add entity_type, effective_date, and dealer_signer_title to MIFA"
```

---

## Chunk 2: Custom Fields (Fixtures) + Groups

### Task 4: Add Loan Application Custom Fields to Fixture

**Files:**
- Modify: `dcr/fixtures/custom_field.json`

Add 11 new custom fields to Loan Application. These go after the existing `Loan Application-doc_checklist` entry. The existing fixture already has `dcr_lending_section` with `requested_advance_amount`, `advance_date_requested`, `outstanding_loan_balance`, `available_credit`, `signed_packet`. The new fields add an Exhibit A / ACH section and an Advance Pre-Approval section.

- [ ] **Step 1: Add Exhibit A + ACH fields**

Append these entries to the `custom_field.json` array, after the last `Loan Application` entry (`Loan Application-doc_checklist`):

```json
{
  "doctype": "Custom Field",
  "name": "Loan Application-exhibit_a_section",
  "dt": "Loan Application",
  "fieldname": "exhibit_a_section",
  "fieldtype": "Section Break",
  "label": "Exhibit A / ACH",
  "insert_after": "doc_checklist"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-serial_no",
  "dt": "Loan Application",
  "fieldname": "serial_no",
  "fieldtype": "Data",
  "label": "Serial No",
  "insert_after": "exhibit_a_section"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-quote_no",
  "dt": "Loan Application",
  "fieldname": "quote_no",
  "fieldtype": "Data",
  "label": "Quote No",
  "insert_after": "serial_no"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-floor_plan",
  "dt": "Loan Application",
  "fieldname": "floor_plan",
  "fieldtype": "Data",
  "label": "Floor Plan",
  "insert_after": "quote_no"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-column_break_exhibit_a",
  "dt": "Loan Application",
  "fieldname": "column_break_exhibit_a",
  "fieldtype": "Column Break",
  "insert_after": "floor_plan"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-buyer_name",
  "dt": "Loan Application",
  "fieldname": "buyer_name",
  "fieldtype": "Data",
  "label": "Buyer Name (End Customer)",
  "insert_after": "column_break_exhibit_a",
  "description": "End customer buying the home"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-monthly_interest_amount",
  "dt": "Loan Application",
  "fieldname": "monthly_interest_amount",
  "fieldtype": "Currency",
  "label": "Monthly Interest Amount",
  "insert_after": "buyer_name"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-monthly_insurance_amount",
  "dt": "Loan Application",
  "fieldname": "monthly_insurance_amount",
  "fieldtype": "Currency",
  "label": "Monthly Insurance Amount",
  "insert_after": "monthly_interest_amount"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-first_autopay_description",
  "dt": "Loan Application",
  "fieldname": "first_autopay_description",
  "fieldtype": "Data",
  "label": "First Autopay Description",
  "insert_after": "monthly_insurance_amount"
}
```

- [ ] **Step 2: Add Advance Pre-Approval fields**

Continue appending to the array:

```json
{
  "doctype": "Custom Field",
  "name": "Loan Application-advance_preapproval_section",
  "dt": "Loan Application",
  "fieldname": "advance_preapproval_section",
  "fieldtype": "Section Break",
  "label": "Advance Pre-Approval",
  "insert_after": "first_autopay_description"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-custom_current_yn",
  "dt": "Loan Application",
  "fieldname": "custom_current_yn",
  "fieldtype": "Select",
  "label": "Current Y/N",
  "options": "\nYes\nNo",
  "insert_after": "advance_preapproval_section"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-custom_projected_investment",
  "dt": "Loan Application",
  "fieldname": "custom_projected_investment",
  "fieldtype": "Currency",
  "label": "Projected Investment",
  "insert_after": "custom_current_yn",
  "description": "Spec variant only"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-custom_projected_sales_price",
  "dt": "Loan Application",
  "fieldname": "custom_projected_sales_price",
  "fieldtype": "Currency",
  "label": "Projected Sales Price",
  "insert_after": "custom_projected_investment",
  "description": "Spec variant only"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-column_break_preapproval",
  "dt": "Loan Application",
  "fieldname": "column_break_preapproval",
  "fieldtype": "Column Break",
  "insert_after": "custom_projected_sales_price"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-custom_projected_equity",
  "dt": "Loan Application",
  "fieldname": "custom_projected_equity",
  "fieldtype": "Currency",
  "label": "Projected Equity",
  "insert_after": "column_break_preapproval",
  "description": "Spec variant — calculated"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-custom_projected_ltv",
  "dt": "Loan Application",
  "fieldname": "custom_projected_ltv",
  "fieldtype": "Percent",
  "label": "Projected LTV",
  "insert_after": "custom_projected_equity",
  "description": "Spec variant — calculated"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-custom_monthly_space_rent",
  "dt": "Loan Application",
  "fieldname": "custom_monthly_space_rent",
  "fieldtype": "Currency",
  "label": "Monthly Space Rent",
  "insert_after": "custom_projected_ltv",
  "description": "Spec variant only"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-custom_projected_payoff",
  "dt": "Loan Application",
  "fieldname": "custom_projected_payoff",
  "fieldtype": "Data",
  "label": "Projected Payoff",
  "insert_after": "custom_monthly_space_rent",
  "description": "e.g. 9-12 Months, 60-90 days"
},
{
  "doctype": "Custom Field",
  "name": "Loan Application-custom_notes",
  "dt": "Loan Application",
  "fieldname": "custom_notes",
  "fieldtype": "Small Text",
  "label": "Notes",
  "insert_after": "custom_projected_payoff"
}
```

- [ ] **Step 3: Commit**

```bash
git add dcr/fixtures/custom_field.json
git commit -m "feat: add Exhibit A, ACH, and Advance Pre-Approval custom fields to Loan Application"
```

---

### Task 5: Add Customer Custom Fields to Fixture

**Files:**
- Modify: `dcr/fixtures/custom_field.json`

Add 13 new fields for Dealers: contact/address info, bank info (Plaid-populated), and dealer agreement fields. These go after the existing `Customer-retailer_application_copy` entry.

- [ ] **Step 1: Add Dealer Contact & Address fields**

Append to the array:

```json
{
  "doctype": "Custom Field",
  "name": "Customer-dealer_contact_section",
  "dt": "Customer",
  "fieldname": "dealer_contact_section",
  "fieldtype": "Section Break",
  "label": "Dealer Contact & Address",
  "insert_after": "retailer_application_copy",
  "depends_on": "eval:doc.customer_group=='Dealer'"
},
{
  "doctype": "Custom Field",
  "name": "Customer-dealer_contact_name",
  "dt": "Customer",
  "fieldname": "dealer_contact_name",
  "fieldtype": "Data",
  "label": "Dealer Contact Name",
  "insert_after": "dealer_contact_section"
},
{
  "doctype": "Custom Field",
  "name": "Customer-dealer_address",
  "dt": "Customer",
  "fieldname": "dealer_address",
  "fieldtype": "Data",
  "label": "Dealer Address",
  "insert_after": "dealer_contact_name"
},
{
  "doctype": "Custom Field",
  "name": "Customer-dealer_city_state_zip",
  "dt": "Customer",
  "fieldname": "dealer_city_state_zip",
  "fieldtype": "Data",
  "label": "Dealer City, State, Zip",
  "insert_after": "dealer_address"
},
{
  "doctype": "Custom Field",
  "name": "Customer-column_break_dealer_contact",
  "dt": "Customer",
  "fieldname": "column_break_dealer_contact",
  "fieldtype": "Column Break",
  "insert_after": "dealer_city_state_zip"
},
{
  "doctype": "Custom Field",
  "name": "Customer-dealer_phone",
  "dt": "Customer",
  "fieldname": "dealer_phone",
  "fieldtype": "Data",
  "label": "Dealer Phone",
  "options": "Phone",
  "insert_after": "column_break_dealer_contact"
},
{
  "doctype": "Custom Field",
  "name": "Customer-dealer_email",
  "dt": "Customer",
  "fieldname": "dealer_email",
  "fieldtype": "Data",
  "label": "Dealer Email",
  "options": "Email",
  "insert_after": "dealer_phone"
}
```

- [ ] **Step 2: Add Bank Info fields (Plaid-populated)**

```json
{
  "doctype": "Custom Field",
  "name": "Customer-bank_info_section",
  "dt": "Customer",
  "fieldname": "bank_info_section",
  "fieldtype": "Section Break",
  "label": "Bank Information",
  "insert_after": "dealer_email",
  "depends_on": "eval:doc.customer_group=='Dealer'"
},
{
  "doctype": "Custom Field",
  "name": "Customer-bank_name",
  "dt": "Customer",
  "fieldname": "bank_name",
  "fieldtype": "Data",
  "label": "Bank Name",
  "insert_after": "bank_info_section"
},
{
  "doctype": "Custom Field",
  "name": "Customer-bank_account_last4",
  "dt": "Customer",
  "fieldname": "bank_account_last4",
  "fieldtype": "Data",
  "label": "Account Last 4",
  "insert_after": "bank_name"
},
{
  "doctype": "Custom Field",
  "name": "Customer-bank_routing_last4",
  "dt": "Customer",
  "fieldname": "bank_routing_last4",
  "fieldtype": "Data",
  "label": "Routing Last 4",
  "insert_after": "bank_account_last4"
},
{
  "doctype": "Custom Field",
  "name": "Customer-column_break_bank",
  "dt": "Customer",
  "fieldname": "column_break_bank",
  "fieldtype": "Column Break",
  "insert_after": "bank_routing_last4"
},
{
  "doctype": "Custom Field",
  "name": "Customer-bank_account_type",
  "dt": "Customer",
  "fieldname": "bank_account_type",
  "fieldtype": "Select",
  "label": "Account Type",
  "options": "\nChecking\nSavings",
  "insert_after": "column_break_bank"
},
{
  "doctype": "Custom Field",
  "name": "Customer-bank_city_state",
  "dt": "Customer",
  "fieldname": "bank_city_state",
  "fieldtype": "Data",
  "label": "Bank City/State",
  "insert_after": "bank_account_type"
},
{
  "doctype": "Custom Field",
  "name": "Customer-bank_account_holder_name",
  "dt": "Customer",
  "fieldname": "bank_account_holder_name",
  "fieldtype": "Data",
  "label": "Name on Account",
  "insert_after": "bank_city_state"
}
```

- [ ] **Step 3: Add Dealer Agreement fields**

```json
{
  "doctype": "Custom Field",
  "name": "Customer-dealer_agreement_section",
  "dt": "Customer",
  "fieldname": "dealer_agreement_section",
  "fieldtype": "Section Break",
  "label": "Dealer Agreement",
  "insert_after": "bank_account_holder_name",
  "depends_on": "eval:doc.customer_group=='Dealer'"
},
{
  "doctype": "Custom Field",
  "name": "Customer-rebate_percentage",
  "dt": "Customer",
  "fieldname": "rebate_percentage",
  "fieldtype": "Percent",
  "label": "Rebate Percentage",
  "insert_after": "dealer_agreement_section"
},
{
  "doctype": "Custom Field",
  "name": "Customer-entity_type",
  "dt": "Customer",
  "fieldname": "entity_type",
  "fieldtype": "Select",
  "label": "Entity Type",
  "options": "\nLLC\nCorporation\nPartnership\nTrust",
  "insert_after": "rebate_percentage"
}
```

- [ ] **Step 4: Commit**

```bash
git add dcr/fixtures/custom_field.json
git commit -m "feat: add Dealer contact, bank info, and agreement custom fields to Customer"
```

---

### Task 6: Create Supplier and Customer Groups in setup.py

**Files:**
- Modify: `dcr/setup.py`

Add creation of "Escrow" Supplier Group and "Home Buyer" Customer Group. These run on `after_install` and `after_migrate` (already wired in hooks.py).

- [ ] **Step 1: Update `after_install()` in `setup.py`**

Replace the current `after_install` function with:

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
    for group_name in ("Escrow",):
        if not frappe.db.exists("Supplier Group", group_name):
            frappe.get_doc({
                "doctype": "Supplier Group",
                "supplier_group_name": group_name,
            }).insert(ignore_permissions=True)

    # Customer Groups
    for group_name in ("Home Buyer",):
        if not frappe.db.exists("Customer Group", group_name):
            frappe.get_doc({
                "doctype": "Customer Group",
                "customer_group_name": group_name,
            }).insert(ignore_permissions=True)

    frappe.db.commit()
```

- [ ] **Step 2: Commit**

```bash
git add dcr/setup.py
git commit -m "feat: auto-create Escrow supplier group and Home Buyer customer group"
```

---

## Notes

### Fields NOT duplicated (already exist)
Per the spec, these Loan Application fields already exist and should be reused as-is:
- `outstanding_loan_balance` — use for "Borrower balance"
- `requested_advance_amount` — use for "Projected advance amount"
- `advance_date_requested` — use for "Projected advance date"

### Jinja fetch patterns for print formats
Once these fields exist, print formats can use:
```jinja
{# Park fields #}
{% set park = frappe.get_doc("Park", doc.park) if doc.park else None %}
{{ park.park_name }}    {{ park.address }}    {{ park.access_code }}

{# Buyer fields #}
{% set buyer = frappe.get_doc("Customer", doc.home_buyer) if doc.home_buyer else None %}
{{ buyer.customer_name }}    {{ buyer.customer_primary_address }}

{# Escrow company name #}
{% set escrow_name = frappe.db.get_value("Supplier", doc.escrow_company, "supplier_name") %}
```

### Link filters (applied in client script, not JSON)
The `home_buyer` Link field on HBR should filter to `customer_group = "Home Buyer"` and `escrow_company` should filter to `supplier_group = "Escrow"`. These filters are set in `home_build_request.js` client script — not in the doctype JSON. This plan does not modify client scripts; that can be done as a follow-up.

### Loan Partner
Per the spec: no custom fields needed. Use the existing Frappe Lending `Loan Partner` doctype as-is for investor-funded loans.
