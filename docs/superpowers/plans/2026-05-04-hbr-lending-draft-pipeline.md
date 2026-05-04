# HBR Lending Draft Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the HBR deal-flow board so PO/PR state remains the primary operational truth while lending state and custom portal drafts appear as secondary Pending-stage context.

**Architecture:** Store only user-owned intake/lending metadata on Home Build Request; derive board columns from submitted Purchase Order and Purchase Receipt links at read time. Portal drafts should either be regular draft HBRs when the portal can satisfy required fields, or a separate lightweight draft doctype when partial portal saves cannot satisfy HBR validation.

**Tech Stack:** Frappe app doctypes, Python whitelisted API, HBR client scripts, setup.py provisioning helpers, unittest-based regression tests.

---

## Files

- Modify: `docs/superpowers/specs/2026-05-04-hbr-deal-flow-kanban.md`
  - Add the accepted lending/draft rule: Lending state is a substatus inside Pending, not a kanban column.
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`
  - Add HBR metadata fields if portal drafts can be represented as real draft HBR documents.
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.py`
  - Normalize intake/lending status on validate and keep draft/submitted status consistent.
- Modify: `dcr/setup.py`
  - If fields are better treated as custom fields in the deployed site, provision missing HBR custom fields here and leave layout placement to Customize Form.
- Create: `dcr/api/hbr_pipeline.py`
  - Read HBRs with derived board status, lending substatus, portal draft flag, PO/PR links, and aging.
- Modify: `dcr/hooks.py`
  - Expose any new client asset if the board is implemented as a Desk page or Custom HTML Block.
- Create or modify: `dcr/tests/test_hbr_pipeline.py`
  - Unit tests for derived board state and draft/lending status mapping.
- Modify: `dcr/tests/test_lending_guards.py`
  - Keep existing cash/Floored guard tests and add coverage that lending substatus does not bypass Floored-only Loan Application creation.
- Optional create: `dcr/dcr/doctype/home_build_portal_draft/home_build_portal_draft.json`
  - Only use this if the custom portal must save incomplete records that cannot pass HBR required-field validation.

---

## Status Model

Primary board columns are derived, not hand edited:

```text
Pending   = no submitted Purchase Order linked to the HBR
Ordered   = submitted Purchase Order exists, but no submitted Purchase Receipt exists
Delivered = submitted Purchase Receipt exists
```

Lending/intake state is secondary metadata:

```text
Portal Draft
Submitted
Under Review
Approved - Ready for PO
Declined
On Hold
Not Applicable
```

Rules:

- Cash deals default to `Not Applicable` for lending substatus.
- Floored draft HBRs from the portal default to `Portal Draft`.
- Submitted Floored HBRs with no Loan Application default to `Submitted`.
- Loan Application or underwriting changes may update the substatus, but they never move the card to Ordered.
- Only a submitted PO moves the card to Ordered.
- Only a submitted PR moves the card to Delivered.

---

### Task 1: Lock the Product Rule Into the Existing Spec

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-hbr-deal-flow-kanban.md`

- [ ] **Step 1: Add a Lending and Portal Draft section**

Append this after "Primary Board (Ops Truth)":

```markdown
## Lending and Portal Drafts

Lending state is not a board column. It is a badge/substatus shown inside Pending until the HBR has a submitted Purchase Order.

Pending substatus values:
- Portal Draft
- Submitted
- Under Review
- Approved - Ready for PO
- Declined
- On Hold
- Not Applicable

Portal drafts are included in Pending. Ops views may hide `Portal Draft` by default, but intake views should show them so partial custom portal work is not lost.

Decision rule:
- If the state is about intake, portal completion, or underwriting, use the Pending substatus.
- If the state is about purchase execution, derive the board column from PO/PR docstatus.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-04-hbr-deal-flow-kanban.md
git commit -m "docs: define hbr lending draft pipeline rules"
```

---

### Task 2: Add HBR Intake Metadata

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.json`
- Alternative modify: `dcr/setup.py`
- Test: `dcr/tests/test_hbr_pipeline.py`

- [ ] **Step 1: Decide field ownership**

Use app-owned JSON fields if these fields should ship with the HBR DocType everywhere. Use `setup.py` custom-field provisioning if the live site should keep Customize Form as the layout source of truth.

Recommended for this repo: add app-owned JSON fields because `Home Build Request` is a DCR-owned DocType, but keep the fields hidden/list-friendly and let future layout tweaks happen in Customize Form if needed.

- [ ] **Step 2: Write the field-existence test**

Create `dcr/tests/test_hbr_pipeline.py`:

```python
"""Tests for HBR pipeline metadata and board-state derivation."""

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TestHbrPipelineFields(unittest.TestCase):
    def test_hbr_contains_intake_pipeline_fields(self):
        doctype = json.loads(
            (ROOT / "dcr/dcr/doctype/home_build_request/home_build_request.json").read_text()
        )
        fields = {field["fieldname"]: field for field in doctype["fields"]}

        self.assertEqual(fields["intake_source"]["fieldtype"], "Select")
        self.assertIn("Portal", fields["intake_source"]["options"])
        self.assertEqual(fields["pre_po_lending_status"]["fieldtype"], "Select")
        self.assertIn("Approved - Ready for PO", fields["pre_po_lending_status"]["options"])
        self.assertEqual(fields["portal_draft_reference"]["fieldtype"], "Data")
        self.assertTrue(fields["pre_po_lending_status"]["in_standard_filter"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the failing test**

```bash
python3 -m unittest dcr.tests.test_hbr_pipeline.TestHbrPipelineFields.test_hbr_contains_intake_pipeline_fields -v
```

Expected: FAIL with missing `intake_source`.

- [ ] **Step 4: Add fields to the HBR DocType JSON**

In `dcr/dcr/doctype/home_build_request/home_build_request.json`, add these fieldnames after `status` in `field_order`:

```json
"intake_source",
"pre_po_lending_status",
"portal_draft_reference",
```

Add these field definitions after the existing `status` field:

```json
{
 "default": "Desk",
 "fieldname": "intake_source",
 "fieldtype": "Select",
 "in_list_view": 1,
 "in_standard_filter": 1,
 "label": "Intake Source",
 "options": "Desk\nPortal"
},
{
 "default": "Submitted",
 "fieldname": "pre_po_lending_status",
 "fieldtype": "Select",
 "in_list_view": 1,
 "in_standard_filter": 1,
 "label": "Pre-PO Lending Status",
 "options": "Portal Draft\nSubmitted\nUnder Review\nApproved - Ready for PO\nDeclined\nOn Hold\nNot Applicable"
},
{
 "fieldname": "portal_draft_reference",
 "fieldtype": "Data",
 "hidden": 1,
 "label": "Portal Draft Reference",
 "no_copy": 1,
 "read_only": 1
}
```

- [ ] **Step 5: Run field test**

```bash
python3 -m unittest dcr.tests.test_hbr_pipeline.TestHbrPipelineFields.test_hbr_contains_intake_pipeline_fields -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dcr/dcr/doctype/home_build_request/home_build_request.json dcr/tests/test_hbr_pipeline.py
git commit -m "feat: add hbr intake pipeline metadata"
```

---

### Task 3: Normalize HBR Draft and Lending Substatus

**Files:**
- Modify: `dcr/dcr/doctype/home_build_request/home_build_request.py`
- Test: `dcr/tests/test_hbr_pipeline.py`

- [ ] **Step 1: Add failing normalization tests**

Append to `dcr/tests/test_hbr_pipeline.py`:

```python
class _HbrDoc:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def get(self, key, default=None):
        return getattr(self, key, default)


class TestHbrPipelineStatusNormalization(unittest.TestCase):
    def test_portal_draft_defaults_to_portal_draft_substatus(self):
        from dcr.dcr.doctype.home_build_request.home_build_request import normalize_pipeline_fields

        doc = _HbrDoc(
            docstatus=0,
            intake_source="Portal",
            financing_type="Floored",
            pre_po_lending_status=None,
            status=None,
        )

        normalize_pipeline_fields(doc)

        self.assertEqual(doc.status, "Draft")
        self.assertEqual(doc.pre_po_lending_status, "Portal Draft")

    def test_cash_deal_defaults_to_not_applicable(self):
        from dcr.dcr.doctype.home_build_request.home_build_request import normalize_pipeline_fields

        doc = _HbrDoc(
            docstatus=1,
            intake_source="Desk",
            financing_type="Cash",
            pre_po_lending_status="Under Review",
            status=None,
        )

        normalize_pipeline_fields(doc)

        self.assertEqual(doc.status, "Submitted")
        self.assertEqual(doc.pre_po_lending_status, "Not Applicable")

    def test_submitted_floored_defaults_to_submitted(self):
        from dcr.dcr.doctype.home_build_request.home_build_request import normalize_pipeline_fields

        doc = _HbrDoc(
            docstatus=1,
            intake_source="Desk",
            financing_type="Floored",
            pre_po_lending_status=None,
            status=None,
        )

        normalize_pipeline_fields(doc)

        self.assertEqual(doc.status, "Submitted")
        self.assertEqual(doc.pre_po_lending_status, "Submitted")
```

- [ ] **Step 2: Run failing tests**

```bash
python3 -m unittest dcr.tests.test_hbr_pipeline.TestHbrPipelineStatusNormalization -v
```

Expected: FAIL with `cannot import name 'normalize_pipeline_fields'`.

- [ ] **Step 3: Implement normalization**

In `dcr/dcr/doctype/home_build_request/home_build_request.py`, add this function near the top:

```python
def normalize_pipeline_fields(doc):
    """Keep stored HBR intake fields aligned with docstatus and deal type."""
    doc.status = "Submitted" if doc.docstatus == 1 else "Draft"

    if doc.get("financing_type") == "Cash":
        doc.pre_po_lending_status = "Not Applicable"
        return

    if doc.get("intake_source") == "Portal" and doc.docstatus == 0:
        doc.pre_po_lending_status = "Portal Draft"
        return

    if not doc.get("pre_po_lending_status") or doc.pre_po_lending_status == "Portal Draft":
        doc.pre_po_lending_status = "Submitted"
```

Then call it at the start of `HomeBuildRequest.validate`:

```python
class HomeBuildRequest(Document):
    def validate(self):
        normalize_pipeline_fields(self)

        # existing validation follows
```

- [ ] **Step 4: Run normalization tests**

```bash
python3 -m unittest dcr.tests.test_hbr_pipeline.TestHbrPipelineStatusNormalization -v
```

Expected: PASS.

- [ ] **Step 5: Run existing HBR/lending tests**

```bash
python3 -m unittest dcr.tests.test_lending_guards dcr.tests.test_required_docs -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dcr/dcr/doctype/home_build_request/home_build_request.py dcr/tests/test_hbr_pipeline.py
git commit -m "feat: normalize hbr lending draft status"
```

---

### Task 4: Add Derived Pipeline API

**Files:**
- Create: `dcr/api/hbr_pipeline.py`
- Test: `dcr/tests/test_hbr_pipeline.py`

- [ ] **Step 1: Add failing board-derivation tests**

Append to `dcr/tests/test_hbr_pipeline.py`:

```python
class TestHbrPipelineDerivation(unittest.TestCase):
    def test_derive_pending_without_po(self):
        from dcr.api.hbr_pipeline import derive_board_status

        row = {"purchase_order": None, "purchase_receipt": None}

        self.assertEqual(derive_board_status(row), "Pending")

    def test_derive_ordered_with_po_without_pr(self):
        from dcr.api.hbr_pipeline import derive_board_status

        row = {"purchase_order": "PO-001", "purchase_receipt": None}

        self.assertEqual(derive_board_status(row), "Ordered")

    def test_derive_delivered_with_pr(self):
        from dcr.api.hbr_pipeline import derive_board_status

        row = {"purchase_order": "PO-001", "purchase_receipt": "PR-001"}

        self.assertEqual(derive_board_status(row), "Delivered")
```

- [ ] **Step 2: Run failing tests**

```bash
python3 -m unittest dcr.tests.test_hbr_pipeline.TestHbrPipelineDerivation -v
```

Expected: FAIL with missing `dcr.api.hbr_pipeline`.

- [ ] **Step 3: Implement the API module**

Create `dcr/api/hbr_pipeline.py`:

```python
import frappe
from frappe.utils import date_diff, nowdate


def derive_board_status(row):
    if row.get("purchase_receipt"):
        return "Delivered"
    if row.get("purchase_order"):
        return "Ordered"
    return "Pending"


def _days_in_stage(row):
    stage_date = row.get("delivered_date") or row.get("ordered_date") or row.get("modified")
    if not stage_date:
        return 0
    return max(date_diff(nowdate(), stage_date), 0)


@frappe.whitelist()
def get_hbr_pipeline(show_portal_drafts=1, owner=None):
    """Return HBR cards with board status derived from submitted PO/PR links."""
    filters = []
    values = {}

    if not int(show_portal_drafts):
        filters.append("COALESCE(hbr.pre_po_lending_status, '') != 'Portal Draft'")

    if owner:
        filters.append("hbr.owner = %(owner)s")
        values["owner"] = owner

    where = " AND ".join(filters)
    if where:
        where = "WHERE " + where

    rows = frappe.db.sql(
        f"""
        SELECT
            hbr.name,
            hbr.customer,
            hbr.owner,
            hbr.financing_type,
            hbr.intake_source,
            hbr.pre_po_lending_status,
            hbr.home_invoice_plus_freight AS amount,
            hbr.modified,
            po.name AS purchase_order,
            po.transaction_date AS ordered_date,
            pr.name AS purchase_receipt,
            pr.posting_date AS delivered_date
        FROM `tabHome Build Request` hbr
        LEFT JOIN `tabPurchase Order` po
            ON po.custom_home_build_request = hbr.name
            AND po.docstatus = 1
        LEFT JOIN `tabPurchase Receipt` pr
            ON pr.custom_home_build_request = hbr.name
            AND pr.docstatus = 1
        {where}
        ORDER BY hbr.modified DESC
        """,
        values,
        as_dict=True,
    )

    for row in rows:
        row["board_status"] = derive_board_status(row)
        row["days_in_stage"] = _days_in_stage(row)
        row["is_portal_draft"] = row.get("pre_po_lending_status") == "Portal Draft"

    return rows
```

- [ ] **Step 4: Run derivation tests**

```bash
python3 -m unittest dcr.tests.test_hbr_pipeline.TestHbrPipelineDerivation -v
```

Expected: PASS.

- [ ] **Step 5: Run import smoke**

```bash
python3 -m py_compile dcr/api/hbr_pipeline.py dcr/dcr/doctype/home_build_request/home_build_request.py
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add dcr/api/hbr_pipeline.py dcr/tests/test_hbr_pipeline.py
git commit -m "feat: add hbr pipeline derivation api"
```

---

### Task 5: Preserve Existing Lending Guards

**Files:**
- Modify: `dcr/tests/test_lending_guards.py`
- No production code should be needed unless the tests expose a regression.

- [ ] **Step 1: Add regression test proving substatus does not authorize cash lending**

Append this test to `TestLoanApplicationGuards`:

```python
    @patch("dcr.api.lending.validate_advance_date")
    @patch("dcr.api.lending.get_dealer_outstanding_balance")
    @patch("dcr.api.lending.is_dealer_current")
    @patch("dcr.api.lending.frappe")
    def test_lending_substatus_does_not_override_cash_guard(
        self, mock_frappe, mock_current, mock_outstanding, mock_advance
    ):
        from dcr.api.lending import validate_loan_application

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Home Build Request" and fieldname == "docstatus":
                return 1
            if doctype == "Home Build Request" and fieldname == "financing_type":
                return "Cash"
            if doctype == "MIFA":
                return None
            return None

        mock_frappe.db.get_value.side_effect = get_value
        mock_frappe.throw.side_effect = Exception("Loan Application requires Floored HBR")
        mock_current.return_value = "Yes"
        mock_outstanding.return_value = 0

        doc = _Doc(
            home_build_request="HBR-CASH-APPROVED",
            applicant="CUST-001",
            loan_amount=100000,
            advance_date_requested=None,
            rate_of_interest=0,
            repayment_periods=0,
            custom_projected_sales_price=0,
        )

        with self.assertRaises(Exception):
            validate_loan_application(doc, "validate")
```

- [ ] **Step 2: Run lending tests**

```bash
python3 -m unittest dcr.tests.test_lending_guards -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add dcr/tests/test_lending_guards.py
git commit -m "test: guard hbr pipeline lending boundaries"
```

---

### Task 6: Portal Draft Strategy

**Files:**
- Optional create: `dcr/dcr/doctype/home_build_portal_draft/home_build_portal_draft.json`
- Optional create: `dcr/dcr/doctype/home_build_portal_draft/home_build_portal_draft.py`
- Optional modify: `dcr/api/hbr_pipeline.py`

- [ ] **Step 1: Choose the portal draft representation**

Use regular draft HBRs if the custom portal can provide these required HBR fields before saving:

```text
customer
financing_type
home_type
property_type
```

Use a separate `Home Build Portal Draft` DocType if the portal must autosave incomplete records before those required fields exist.

- [ ] **Step 2A: If using regular draft HBRs, enforce portal defaults**

When the portal creates an HBR, set:

```python
{
    "doctype": "Home Build Request",
    "intake_source": "Portal",
    "pre_po_lending_status": "Portal Draft",
}
```

No additional production code is required beyond Tasks 2-4.

- [ ] **Step 2B: If using a separate portal draft doctype, create conversion API**

Create `dcr/dcr/doctype/home_build_portal_draft/home_build_portal_draft.py` with a conversion method:

```python
import frappe


def create_hbr_from_portal_draft(portal_draft):
    hbr = frappe.get_doc({
        "doctype": "Home Build Request",
        "customer": portal_draft.customer,
        "home_type": portal_draft.home_type,
        "financing_type": portal_draft.financing_type,
        "property_type": portal_draft.property_type,
        "intake_source": "Portal",
        "pre_po_lending_status": "Submitted",
        "portal_draft_reference": portal_draft.name,
    })
    hbr.insert(ignore_permissions=True)
    return hbr
```

- [ ] **Step 3: Keep API output consistent**

If `Home Build Portal Draft` is used, update `get_hbr_pipeline()` to union converted/non-converted portal draft rows into Pending with:

```python
{
    "board_status": "Pending",
    "pre_po_lending_status": "Portal Draft",
    "is_portal_draft": True,
    "purchase_order": None,
    "purchase_receipt": None,
}
```

- [ ] **Step 4: Commit**

```bash
git add dcr/dcr/doctype/home_build_portal_draft dcr/api/hbr_pipeline.py
git commit -m "feat: support portal hbr drafts"
```

Skip this commit if Step 2A is chosen and no files changed.

---

### Task 7: Desk/UI View

**Files:**
- Create or modify a Custom HTML Block/Page asset only after the API is stable.
- Suggested create: `dcr/public/js/hbr_pipeline_board.js`
- Suggested modify: `dcr/setup.py`

- [ ] **Step 1: Start with saved list views before custom UI**

Create these Frappe saved filters manually or through setup only if they need to ship:

```text
Ops View: pre_po_lending_status != Portal Draft
Intake View: no filter, group visually by pre_po_lending_status
Management View: all rows, sorted by days_in_stage descending
```

- [ ] **Step 2: If a custom board is needed, use the API instead of duplicating state**

The board should call:

```javascript
frappe.call({
    method: "dcr.api.hbr_pipeline.get_hbr_pipeline",
    args: { show_portal_drafts: 0 }
});
```

Cards should render:

```text
HBR ID
Customer
Amount
Owner
Days in stage
Pre-PO Lending Status badge
PO number when Ordered
PR number when Delivered
```

- [ ] **Step 3: Runtime verification**

In browser console on the DCR site:

```javascript
frappe.call({
    method: "dcr.api.hbr_pipeline.get_hbr_pipeline",
    args: { show_portal_drafts: 1 }
}).then(r => console.table(r.message.map(x => ({
    name: x.name,
    board_status: x.board_status,
    lending: x.pre_po_lending_status,
    po: x.purchase_order,
    pr: x.purchase_receipt
}))));
```

Expected:

```text
Rows with no submitted PO show Pending.
Rows with submitted PO and no submitted PR show Ordered.
Rows with submitted PR show Delivered.
Portal Draft rows show Pending and is_portal_draft=true.
```

- [ ] **Step 4: Commit**

```bash
git add dcr/public/js/hbr_pipeline_board.js dcr/setup.py
git commit -m "feat: add hbr pipeline board view"
```

Skip this commit if saved list views are enough for v1.

---

## Verification

Run focused tests:

```bash
python3 -m unittest \
  dcr.tests.test_hbr_pipeline \
  dcr.tests.test_lending_guards \
  dcr.tests.test_required_docs \
  dcr.tests.test_setup \
  -v
```

Run syntax checks:

```bash
python3 -m py_compile \
  dcr/api/hbr_pipeline.py \
  dcr/dcr/doctype/home_build_request/home_build_request.py \
  dcr/api/lending.py
```

Manual production-style proof points:

```text
Cash HBR: no Loan Application button, no lending connections, API shows Pending/Ordered/Delivered by PO/PR only.
Floored portal draft: API shows Pending + Portal Draft.
Floored submitted HBR with approved lending: API still shows Pending until a submitted PO exists.
Submitted PO: API moves card to Ordered.
Submitted PR: API moves card to Delivered.
Cancelled PO/PR: ignored by board derivation because docstatus != 1.
```

---

## Implementation Notes

- Do not add `Under Review`, `Approved`, or `Portal Draft` as kanban columns.
- Do not let `pre_po_lending_status` create or authorize Loan Applications; existing Floored-only server validation in `dcr/api/lending.py` remains the authority.
- Do not hand-edit board state when PO/PR changes; derive it on read so accounting/order documents stay the source of truth.
- Keep portal drafts visible to intake and hideable for ops. Hidden-by-default is a view preference, not data deletion.
- If a custom portal draft cannot satisfy required HBR fields, use a separate draft doctype and convert it into HBR only when it has enough data to pass HBR validation.
