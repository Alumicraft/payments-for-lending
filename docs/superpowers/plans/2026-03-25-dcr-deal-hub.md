# DCR Deal Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Home Build Request the single source of truth for all deal data, with downstream records fetching from it.

**Architecture:** HBR owns deal data. SQ writes back serial/quote. LA, Loan, Loan Disbursement fetch from HBR via fetch_from chains. Park gets address split + quick_entry. Factory Assignment gets rebate_percentage and auto-status.

**Tech Stack:** Frappe v15 + ERPNext + Lending module. No bench — Frappe Cloud deployment. Changes are doctype JSON, custom_field fixtures, Python hooks, and client scripts.

**Spec:** `docs/superpowers/specs/2026-03-25-dcr-deal-hub-design.md`

---

### Task 1: Park Doctype — Address Split + Quick Entry

**Files:**
- Modify: `dcr/dcr/doctype/park/park.json`
- Create: `dcr/patches/park_address_split.py`
- Modify: `dcr/patches.txt` (register migration patch)

- [ ] **Step 1: Update Park JSON — add new fields, keep old fields hidden for migration**

In `dcr/dcr/doctype/park/park.json`: Keep `address` and `city_state_zip` but mark them `hidden: 1` (needed by migration patch — Frappe syncs JSON before running patches). Add `address_line1`, `address_line2`, `city`, `state`, `zip`. Add `quick_entry: 1`. Old fields will be removed in a follow-up after the patch runs.

New `field_order`:
```json
[
  "park_name",
  "column_break_1",
  "office_phone",
  "contact_name",
  "address_section",
  "address_line1",
  "address_line2",
  "column_break_address",
  "city",
  "state",
  "zip",
  "old_fields_section",
  "address",
  "city_state_zip",
  "access_section",
  "gated",
  "access_code"
]
```

Old fields kept temporarily (hidden):
```json
{
  "fieldname": "old_fields_section",
  "fieldtype": "Section Break",
  "hidden": 1
},
{
  "fieldname": "address",
  "fieldtype": "Data",
  "label": "Address (Old)",
  "hidden": 1
},
{
  "fieldname": "city_state_zip",
  "fieldtype": "Data",
  "label": "City, St Zip (Old)",
  "hidden": 1
}
```

New fields to add (replacing `address` and `city_state_zip`):
```json
{
  "fieldname": "address_line1",
  "fieldtype": "Data",
  "label": "Address Line 1"
},
{
  "fieldname": "address_line2",
  "fieldtype": "Data",
  "label": "Address Line 2"
},
{
  "fieldname": "column_break_address",
  "fieldtype": "Column Break"
},
{
  "fieldname": "city",
  "fieldtype": "Data",
  "label": "City"
},
{
  "fieldname": "state",
  "fieldtype": "Data",
  "label": "State"
},
{
  "fieldname": "zip",
  "fieldtype": "Data",
  "label": "Zip"
}
```

Add top-level property: `"quick_entry": 1`

- [ ] **Step 2: Write data migration patch**

Create `dcr/patches/park_address_split.py`:
```python
import frappe


def execute():
    """Migrate Park address/city_state_zip to split fields."""
    parks = frappe.get_all("Park", fields=["name", "address", "city_state_zip"])

    for park in parks:
        updates = {}

        # Copy address -> address_line1
        if park.get("address"):
            updates["address_line1"] = park.address

        # Parse city_state_zip -> city, state, zip
        csz = park.get("city_state_zip") or ""
        if csz.strip():
            try:
                if "," in csz:
                    # "City Name, ST 12345" or "City Name, ST"
                    city_part, remainder = csz.rsplit(",", 1)
                    updates["city"] = city_part.strip()
                    tokens = remainder.strip().split()
                    if len(tokens) >= 2:
                        updates["zip"] = tokens[-1]
                        updates["state"] = " ".join(tokens[:-1])
                    elif len(tokens) == 1:
                        updates["state"] = tokens[0]
                else:
                    # No comma — try "City ST 12345"
                    tokens = csz.strip().split()
                    if len(tokens) >= 3:
                        updates["zip"] = tokens[-1]
                        updates["state"] = tokens[-2]
                        updates["city"] = " ".join(tokens[:-2])
                    else:
                        frappe.log_error(
                            f"Park {park.name}: unparseable city_state_zip '{csz}'",
                            "Park Address Migration"
                        )
            except Exception:
                frappe.log_error(
                    f"Park {park.name}: failed to parse '{csz}'",
                    "Park Address Migration"
                )

        if updates:
            frappe.db.set_value("Park", park.name, updates, update_modified=False)

    frappe.db.commit()
```

- [ ] **Step 3: Register patch in patches.txt**

Add to `dcr/patches.txt`:
```
dcr.patches.park_address_split
```

- [ ] **Step 4: Commit**

```bash
git add dcr/dcr/doctype/park/park.json dcr/patches/park_address_split.py dcr/patches.txt
git commit -m "feat: split Park address fields + enable quick_entry"
```

---

### Task 2: HBR — New Fields + Form Reorganization

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`

- [ ] **Step 1: Add new fields and reorganize HBR JSON**

Replace the entire `field_order` and `fields` arrays in `home_build_request.json` with the new layout from the spec.

New `field_order`:
```json
[
  "customer",
  "status",
  "column_break_1",
  "home_type",
  "financing_type",
  "property_type",
  "home_section",
  "model_name",
  "factory",
  "column_break_home",
  "home_serial_no",
  "quote_no",
  "home_invoice_plus_freight",
  "park_section",
  "park",
  "space_number",
  "park_details_section",
  "park_address_line1",
  "park_address_line2",
  "column_break_park_addr",
  "park_city",
  "park_state",
  "park_zip",
  "park_contact_section",
  "park_contact_name",
  "park_phone",
  "column_break_park_contact",
  "park_gated",
  "park_access_code",
  "buyer_section",
  "home_buyer",
  "end_buyer_lender",
  "column_break_buyer",
  "customer_deposit",
  "selling_price",
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
  "factory_order_section",
  "factory_quote",
  "column_break_factory_order",
  "loan_application",
  "documents_section",
  "doc_checklist"
]
```

New fields to ADD (keep all existing fields, just add these):
```json
{
  "fieldname": "home_serial_no",
  "fieldtype": "Data",
  "label": "Home Serial No",
  "in_list_view": 1
},
{
  "fieldname": "quote_no",
  "fieldtype": "Data",
  "label": "Quote No"
}
```

Section/layout changes:
- Remove `references_section`, `column_break_refs`, `home_info_section`, `column_break_home_info`, `escrow_financials_section`, `column_break_escrow2`
- Add `home_section` (Section Break, label "Home")
- Add `column_break_home` (Column Break)
- Add `read_only_depends_on: "eval:doc.factory_quote"` to `home_invoice_plus_freight`
- Add `park_details_section` (Section Break, label "Park Details", `depends_on: "eval:doc.property_type=='Park'"`)
- Add `park_contact_section` (Section Break, `depends_on: "eval:doc.property_type=='Park'"`) — Frappe sections are not nested; each needs its own depends_on
- Add `"read_only": 1` to `factory_quote` field (set programmatically on HBR submit)
- Enforce `home_serial_no` uniqueness in HBR `validate()` (not via `unique: 1` on the field, because empty values cause duplicate key violations in Frappe)
- Add all `park_*` fetch_from fields (9 fields, all read_only, fetch_from park.*)
- Add `park_contact_section`, column breaks for park layout
- Add `factory_order_section` (Section Break, label "Factory Order")
- Add `column_break_factory_order` (Column Break)
- Move `escrow_financials_section` fields (`customer_deposit`, `selling_price`, `end_buyer_lender`) into buyer_section
- Add `depends_on: "eval:doc.home_type=='Customer Sold'"` to `escrow_section` (already has it)

Park fetch_from fields:
```json
{
  "fieldname": "park_address_line1",
  "fieldtype": "Data",
  "label": "Address Line 1",
  "fetch_from": "park.address_line1",
  "read_only": 1
},
{
  "fieldname": "park_address_line2",
  "fieldtype": "Data",
  "label": "Address Line 2",
  "fetch_from": "park.address_line2",
  "read_only": 1
},
{
  "fieldname": "park_city",
  "fieldtype": "Data",
  "label": "City",
  "fetch_from": "park.city",
  "read_only": 1
},
{
  "fieldname": "park_state",
  "fieldtype": "Data",
  "label": "State",
  "fetch_from": "park.state",
  "read_only": 1
},
{
  "fieldname": "park_zip",
  "fieldtype": "Data",
  "label": "Zip",
  "fetch_from": "park.zip",
  "read_only": 1
},
{
  "fieldname": "park_contact_name",
  "fieldtype": "Data",
  "label": "Contact Name",
  "fetch_from": "park.contact_name",
  "read_only": 1
},
{
  "fieldname": "park_phone",
  "fieldtype": "Data",
  "label": "Phone",
  "fetch_from": "park.office_phone",
  "read_only": 1,
  "options": "Phone"
},
{
  "fieldname": "park_gated",
  "fieldtype": "Check",
  "label": "Gated",
  "fetch_from": "park.gated",
  "read_only": 1
},
{
  "fieldname": "park_access_code",
  "fieldtype": "Data",
  "label": "Access Code",
  "fetch_from": "park.access_code",
  "read_only": 1
}
```

- [ ] **Step 2: Verify JSON is valid**

```bash
python -m json.tool dcr/dcr/doctype/home_build_request/home_build_request.json > /dev/null
```

- [ ] **Step 3: Commit**

```bash
git add dcr/dcr/doctype/home_build_request/home_build_request.json
git commit -m "feat: reorganize HBR form, add serial/quote fields and park fetch_from"
```

---

### Task 3: HBR — Factory Filter + Validate

**Files:**
- Modify: `dcr/public/js/home_build_request.js`
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.py`

- [ ] **Step 1: Add factory set_query filter in JS**

In `dcr/public/js/home_build_request.js`, add to the `refresh` handler (after the existing Create button logic):

```javascript
// Filter factory by dealer's approved Factory Assignments
if (frm.doc.customer) {
    frm.set_query('factory', function() {
        return {
            query: 'dcr.dcr.doctype.home_build_request.home_build_request.get_assigned_factories',
            filters: { customer: frm.doc.customer }
        };
    });
}
```

Also add a `customer` change handler to re-apply the filter:
```javascript
customer: function(frm) {
    if (frm.doc.customer) {
        frm.set_query('factory', function() {
            return {
                query: 'dcr.dcr.doctype.home_build_request.home_build_request.get_assigned_factories',
                filters: { customer: frm.doc.customer }
            };
        });
    }
},
```

- [ ] **Step 2: Add server-side query + validate in Python**

In `dcr/dcr/doctype/home_build_request/home_build_request.py`, add:

```python
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_assigned_factories(doctype, txt, searchfield, start, page_len, filters):
    """Return factories where this customer has an approved Factory Assignment."""
    customer = filters.get("customer")
    if not customer:
        return []

    return frappe.db.sql("""
        SELECT DISTINCT fa.factory, fa.factory
        FROM `tabFactory Assignment` fa
        WHERE fa.customer = %(customer)s
            AND fa.docstatus = 1
            AND fa.active = 1
            AND fa.factory LIKE %(txt)s
        ORDER BY fa.factory
        LIMIT %(page_len)s OFFSET %(start)s
    """, {
        "customer": customer,
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len
    })
```

In the `validate` method of `HomeBuildRequest`, add a warning check:

```python
def validate(self):
    if self.financing_type == "Floored" and not self.property_type:
        frappe.throw(_("Property Type is required"))

    # Warn if factory has no approved Factory Assignment for this dealer
    if self.factory and self.customer:
        has_fa = frappe.db.exists("Factory Assignment", {
            "customer": self.customer,
            "factory": self.factory,
            "docstatus": 1,
            "active": 1
        })
        if not has_fa:
            frappe.msgprint(
                _("Factory {0} has no approved Factory Assignment for dealer {1}.").format(
                    self.factory, self.customer
                ),
                indicator="orange",
                title=_("Missing Factory Assignment")
            )
```

- [ ] **Step 3: Commit**

```bash
git add dcr/public/js/home_build_request.js dcr/dcr/doctype/home_build_request/home_build_request.py
git commit -m "feat: filter HBR factory by dealer's Factory Assignments"
```

---

### Task 4: Supplier Quotation — New Fields + Writeback

**Files:**
- Modify: `dcr/fixtures/custom_field.json`
- Modify: `dcr/hooks.py`
- Modify: `dcr/api/lending.py`

- [ ] **Step 1: Add SQ custom fields to fixtures**

In `dcr/fixtures/custom_field.json`, add two new entries after `Supplier Quotation-signature_date`:

```json
{
  "doctype": "Custom Field",
  "name": "Supplier Quotation-home_serial_no",
  "dt": "Supplier Quotation",
  "fieldname": "home_serial_no",
  "fieldtype": "Data",
  "label": "Serial No",
  "insert_after": "signature_date"
},
{
  "doctype": "Custom Field",
  "name": "Supplier Quotation-quote_no",
  "dt": "Supplier Quotation",
  "fieldname": "quote_no",
  "fieldtype": "Data",
  "label": "Quote No",
  "insert_after": "home_serial_no"
}
```

Also add `link_filters` to the existing SQ `home_build_request` field:
```json
"link_filters": "{\"docstatus\": 1}"
```

Register the new field names in `hooks.py` fixtures filter list:
```python
"Supplier Quotation-home_serial_no",
"Supplier Quotation-quote_no",
```

- [ ] **Step 2: Add SQ writeback hook**

In `dcr/api/lending.py`, add:

```python
def on_sq_before_save(doc, method):
    """Write home_serial_no and quote_no back to linked HBR."""
    if not doc.home_build_request:
        return
    hbr = frappe.get_doc("Home Build Request", doc.home_build_request)
    if doc.home_serial_no and hbr.home_serial_no != doc.home_serial_no:
        hbr.db_set("home_serial_no", doc.home_serial_no)
    if doc.quote_no and hbr.quote_no != doc.quote_no:
        hbr.db_set("quote_no", doc.quote_no)
```

- [ ] **Step 3: Register SQ doc_event in hooks.py**

In `dcr/hooks.py`, add to `doc_events`:

```python
"Supplier Quotation": {
    "before_save": "dcr.api.lending.on_sq_before_save"
},
```

- [ ] **Step 4: Commit**

```bash
git add dcr/fixtures/custom_field.json dcr/hooks.py dcr/api/lending.py
git commit -m "feat: add SQ serial/quote fields with writeback to HBR"
```

---

### Task 5: Downstream Fetch Chain — LA + Loan Fixtures

**Files:**
- Modify: `dcr/fixtures/custom_field.json`
- Modify: `dcr/hooks.py` (fixture names list)
- Modify: `dcr/api/lending.py` (remove redundant Python copies)

- [ ] **Step 1: Update LA fixtures — add fetch_from to serial/quote**

In `dcr/fixtures/custom_field.json`, update `Loan Application-home_serial_no` (line ~527):
```json
{
  "doctype": "Custom Field",
  "name": "Loan Application-home_serial_no",
  "dt": "Loan Application",
  "fieldname": "home_serial_no",
  "fieldtype": "Data",
  "label": "Serial No",
  "insert_after": "exhibit_a_section",
  "fetch_from": "home_build_request.home_serial_no",
  "read_only": 1
}
```

Update `Loan Application-quote_no` (line ~536):
```json
{
  "doctype": "Custom Field",
  "name": "Loan Application-quote_no",
  "dt": "Loan Application",
  "fieldname": "quote_no",
  "fieldtype": "Data",
  "label": "Quote No",
  "insert_after": "home_serial_no",
  "fetch_from": "home_build_request.quote_no",
  "read_only": 1
}
```

Make `home_build_request` and `requested_advance_amount` mandatory on LA:
- On `Loan Application-home_build_request`: add `"reqd": 1`
- On `Loan Application-requested_advance_amount`: add `"reqd": 1`

- [ ] **Step 2: Update Loan fixtures — add fetch_from + read_only + mandatory**

Update `Loan-home_build_request` (line ~328):
```json
{
  "doctype": "Custom Field",
  "name": "Loan-home_build_request",
  "dt": "Loan",
  "fieldname": "home_build_request",
  "fieldtype": "Link",
  "options": "Home Build Request",
  "label": "Home Build Request",
  "insert_after": "home_deal_reference_section",
  "read_only": 1,
  "reqd": 1
}
```

Update `Loan-home_serial_no` (line ~338):
```json
{
  "doctype": "Custom Field",
  "name": "Loan-home_serial_no",
  "dt": "Loan",
  "fieldname": "home_serial_no",
  "fieldtype": "Data",
  "label": "Serial No",
  "insert_after": "home_build_request",
  "fetch_from": "home_build_request.home_serial_no",
  "read_only": 1
}
```

Update `Loan-buyer_name` (line ~347):
```json
{
  "doctype": "Custom Field",
  "name": "Loan-buyer_name",
  "dt": "Loan",
  "fieldname": "buyer_name",
  "fieldtype": "Data",
  "label": "Buyer Name",
  "insert_after": "home_serial_no",
  "fetch_from": "home_build_request.home_buyer",
  "read_only": 1
}
```

Update `Loan-factory` (line ~364):
```json
{
  "doctype": "Custom Field",
  "name": "Loan-factory",
  "dt": "Loan",
  "fieldname": "factory",
  "fieldtype": "Link",
  "label": "Factory",
  "options": "Supplier",
  "insert_after": "column_break_home_deal",
  "fetch_from": "home_build_request.factory",
  "read_only": 1,
  "reqd": 1
}
```

Make Loan Disbursement fields mandatory:
- On `Loan Disbursement-home_build_request`: add `"reqd": 1`
- On `Loan Disbursement-factory`: add `"reqd": 1`

- [ ] **Step 3: Clean up on_loan_validate — remove redundant copies**

In `dcr/api/lending.py`, update `on_loan_validate` (line 132). Remove the field-by-field copy logic for `home_serial_no`, `buyer_name`, `factory`. Keep only the `home_build_request` copy:

```python
def on_loan_validate(doc, method):
    """Populate home_build_request from Loan Application.

    Other deal reference fields (home_serial_no, buyer_name, factory)
    are handled by fetch_from declarations in fixtures.
    """
    if not doc.loan_application:
        return
    if not doc.home_build_request:
        hbr = frappe.db.get_value(
            "Loan Application", doc.loan_application, "home_build_request"
        )
        if hbr:
            doc.home_build_request = hbr
```

- [ ] **Step 4: Commit**

```bash
git add dcr/fixtures/custom_field.json dcr/api/lending.py
git commit -m "feat: wire fetch_from chain for LA/Loan fields, add mandatory, clean up Python copies"
```

---

### Task 6: Factory Assignment — Rebate, Auto-Status, Quick Entry, Dashboard Link

**Files:**
- Modify: `dcr/dcr/doctype/factory_assignment/factory_assignment.json`
- Modify: `dcr/dcr/doctype/factory_assignment/factory_assignment.py`
- Modify: `dcr/fixtures/custom_field.json` (remove Loan Product rebate)
- Modify: `dcr/hooks.py` (remove Loan Product-rebate_percentage from fixtures)

- [ ] **Step 1: Add rebate_percentage to FA JSON + enable quick_entry**

In `dcr/dcr/doctype/factory_assignment/factory_assignment.json`:

Add to `field_order` after `active`:
```json
"rebate_percentage"
```

Add to `fields` array:
```json
{
  "fieldname": "rebate_percentage",
  "fieldtype": "Percent",
  "label": "Rebate Percentage",
  "description": "Per dealer-factory rebate rate"
}
```

Add top-level: `"quick_entry": 1`

- [ ] **Step 2: Auto-set status on submit**

In `dcr/dcr/doctype/factory_assignment/factory_assignment.py`, change `on_submit`:

```python
class FactoryAssignment(Document):
    def on_submit(self):
        # Auto-set status to Submitted
        self.db_set("retailer_application_status", "Submitted")
        self.send_retailer_application()

    def send_retailer_application(self):
        """Send retailer application package to factory via Resend."""
        from dcr.api.resend_integration import send_retailer_application_email
        send_retailer_application_email(self)
```

- [ ] **Step 3: Remove Loan Product rebate from fixtures**

In `dcr/fixtures/custom_field.json`, remove the `Loan Product-rebate_percentage` entry (line ~731-739).

In `dcr/hooks.py`, remove `"Loan Product-rebate_percentage"` from the fixtures filter list (line 103).

- [ ] **Step 4: Add FA to Customer dashboard links**

In `dcr/hooks.py`, add `"Customer-Factory Assignment"` to the DocType Link fixtures filter list (currently has `Customer-Home Build Request`, `Customer-MIFA`, `Customer-Factory Assignment` — check if it's already there, if not add it).

Looking at hooks.py line 17-22, `"Customer-Factory Assignment"` is already in the DocType Link fixtures. The link definition is already registered. Verify the actual link exists in the fixture or add it as needed.

- [ ] **Step 5: Commit**

```bash
git add dcr/dcr/doctype/factory_assignment/factory_assignment.json dcr/dcr/doctype/factory_assignment/factory_assignment.py dcr/fixtures/custom_field.json dcr/hooks.py
git commit -m "feat: FA rebate field, auto-status on submit, quick_entry, remove LP rebate"
```

---

### Task 7: Customer — Mandatory Fields, Multiple FAs, Hide Lending Names

**Files:**
- Modify: `dcr/fixtures/custom_field.json`
- Modify: `dcr/hooks.py`
- Modify: `dcr/public/js/customer.js`

- [ ] **Step 1: Make Customer fields mandatory in fixtures**

In `dcr/fixtures/custom_field.json`:

On `Customer-dealer_license_no` (line ~15): add `"reqd": 1`
On `Customer-entity_type` (line ~711): add `"reqd": 1`
On `Customer-default_loan_product` (line ~720): add `"reqd": 1`

- [ ] **Step 2: Add Property Setter fixtures for hiding Lending names**

In `dcr/hooks.py`, add a new fixture entry for Property Setter:

```python
{
    "doctype": "Property Setter",
    "filters": [
        ["name", "in", [
            "Customer-first_name-hidden",
            "Customer-last_name-hidden",
        ]]
    ]
}
```

Create `dcr/fixtures/property_setter.json`:
```json
[
  {
    "doctype": "Property Setter",
    "name": "Customer-first_name-hidden",
    "doc_type": "Customer",
    "field_name": "first_name",
    "property": "hidden",
    "property_type": "Check",
    "value": "1"
  },
  {
    "doctype": "Property Setter",
    "name": "Customer-last_name-hidden",
    "doc_type": "Customer",
    "field_name": "last_name",
    "property": "hidden",
    "property_type": "Check",
    "value": "1"
  }
]
```

**Note:** Verify that `first_name` and `last_name` are actual field names on the Customer doctype in ERPNext with Lending. If Lending adds them under different names, adjust accordingly during implementation.

- [ ] **Step 3: Allow multiple Factory Assignments in customer.js**

In `dcr/public/js/customer.js`, replace the Factory Assignment button section (lines 46-55). Remove the `count === 0` check:

```javascript
// Create → Factory Assignment (always available for dealers)
frm.add_custom_button(__('Factory Assignment'), function() {
    frappe.new_doc('Factory Assignment', {
        customer: frm.doc.name
    });
}, __('Create'));
```

- [ ] **Step 4: Commit**

```bash
git add dcr/fixtures/custom_field.json dcr/fixtures/property_setter.json dcr/hooks.py dcr/public/js/customer.js
git commit -m "feat: Customer mandatory fields, allow multiple FAs, hide Lending name fields"
```

---

### Task 8: Final Verification + Print Format Check

**Files:**
- Check: Print formats that reference `loan_product.rebate_percentage`

- [ ] **Step 1: Find print formats referencing rebate_percentage**

```bash
grep -r "rebate_percentage" dcr/
```

Identify all print formats (Jinja templates) that use `loan_product.rebate_percentage`. These need to be updated to fetch rebate from the Factory Assignment for the deal instead.

The lookup pattern becomes:
```python
# In print format context, given a Loan with factory and applicant:
rebate = frappe.db.get_value("Factory Assignment", {
    "customer": loan.applicant,
    "factory": loan.factory,
    "docstatus": 1,
    "active": 1
}, "rebate_percentage")
```

Update each affected print format.

- [ ] **Step 2: Validate all JSON files**

```bash
python -m json.tool dcr/dcr/doctype/park/park.json > /dev/null
python -m json.tool dcr/dcr/doctype/home_build_request/home_build_request.json > /dev/null
python -m json.tool dcr/dcr/doctype/factory_assignment/factory_assignment.json > /dev/null
python -m json.tool dcr/fixtures/custom_field.json > /dev/null
python -m json.tool dcr/fixtures/property_setter.json > /dev/null
```

- [ ] **Step 3: Run full grep for stale references**

Check for any remaining references to removed fields or old patterns:
```bash
grep -rn "city_state_zip\|Loan Product.*rebate\|rebate_percentage" dcr/ --include="*.py" --include="*.js" --include="*.html" --include="*.json"
```

Fix any stale references found.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: update print formats for rebate source change, fix stale references"
```

---

## Task Dependency Graph

```
Task 1 (Park) ──────────────────────┐
Task 2 (HBR fields + form) ─────────┤
Task 3 (HBR factory filter) ────────┤──→ Task 8 (Verification)
Task 4 (SQ fields + writeback) ─────┤
Task 5 (LA/Loan fetch_from) ────────┤
Task 6 (FA changes) ────────────────┤
Task 7 (Customer changes) ──────────┘
```

Tasks 1-7 are independent of each other and can be implemented in parallel. Task 8 depends on all others completing.
