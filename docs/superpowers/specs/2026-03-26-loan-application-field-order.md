# Loan Application — Definitive Field Order

This is the exact field order for implementation. Every field, every section break, every column break.

---

## Section 1: Header (no label — top of form)

| # | Label | Fieldname | Type | Notes |
|---|-------|-----------|------|-------|
| 1 | Applicant Type | `applicant_type` | Select | **Hidden** ✓, default "Customer" via code |
| 2 | Applicant | `applicant` | Dynamic Link | Mandatory |
| 3 | Applicant Name | `applicant_name` | Data | Read-only |
| 4 | | `column_break_header` | Column Break | |
| 5 | Posting Date | `posting_date` | Date | Moved from row 39 |
| 6 | Status | `status` | Select | Moved from row 40 |

---

## Section 2: Deal reference

| # | Label | Fieldname | Type | Notes |
|---|-------|-----------|------|-------|
| 7 | Deal reference | `deal_reference_section` | Section Break | Renamed from "Deal Reference" → sentence case |
| 8 | Home Build Request | `home_build_request` | Link → Home Build Request | Mandatory |
| 9 | Home Type | `home_type` | Select | RO, fetch_from `home_build_request.home_type` |
| 10 | | `column_break_deal_ref` | Column Break | |
| 11 | Factory | `factory` | Link → Supplier | RO, fetch_from `home_build_request.factory` |

---

## Section 3: Lending

| # | Label | Fieldname | Type | Notes |
|---|-------|-----------|------|-------|
| 12 | Lending | `lending_section` | Section Break | Combined Lending Overview + old Exhibit A fields |
| 13 | Loan Product | `loan_product` | Link → Loan Product | Mandatory |
| 14 | Loan Amount | `loan_amount` | Currency | Replaces `requested_advance_amount` |
| 15 | Advance Date | `advance_date_requested` | Date | |
| 16 | Serial No | `home_serial_no` | Data | RO, fetch_from `home_build_request.home_serial_no`. Moved from Exhibit A |
| 17 | Quote No | `quote_no` | Data | RO, fetch_from `home_build_request.quote_no`. Moved from Exhibit A |
| 18 | Model | `floor_plan` | Data | RO, fetch_from `home_build_request.model_name`. **Renamed from "Floor Plan" to "Model"** to match HBR |
| 19 | | `column_break_lending` | Column Break | |
| 20 | Rate of Interest | `rate_of_interest` | Percent | RO, fetched from Loan Product |
| 21 | Buyer Name | `buyer_name` | Data | RO, fetch_from `home_build_request.home_buyer`. **Relabeled from "Buyer Name (End Customer)"**. Moved from Exhibit A |

---

## Section 4: Lending calculations

| # | Label | Fieldname | Type | Notes |
|---|-------|-----------|------|-------|
| 22 | Lending calculations | `lending_calculations_section` | Section Break | |
| 23 | Available Credit | `available_credit` | Currency | RO, calculated (MIFA credit_limit − outstanding_balance) |
| 24 | Outstanding Loan Balance | `outstanding_loan_balance` | Currency | RO, calculated (SUM active loans) |
| 25 | Current | `custom_current_yn` | Select | RO, calculated (no overdue repayments = Yes). **Renamed from "Current Y/N"**. Moved from Pre-Approval section |
| 26 | | `column_break_lending_calc` | Column Break | |
| 27 | Monthly Interest Amount | `monthly_interest_amount` | Currency | RO, calculated = (rate / 100) × loan_amount / 12 |
| 28 | Monthly Insurance Amount | `monthly_insurance_amount` | Currency | Manual entry |
| 29 | Monthly Repayment Amount | `repayment_amount` | Currency | Standard ERPNext field, RO calculated |
| 30 | Total Payable Amount | `total_payable_amount` | Currency | Standard ERPNext field, RO calculated |
| 31 | Total Payable Interest | `total_payable_interest` | Currency | Standard ERPNext field, RO calculated |

---

## Section 5: Pre-approval letter

| # | Label | Fieldname | Type | Notes |
|---|-------|-----------|------|-------|
| 32 | Pre-approval letter | `advance_preapproval_section` | Section Break | **Renamed from "Advance Pre-Approval"**. depends_on: `eval:doc.home_type=='Spec'` |
| 33 | Projected Sales Price | `custom_projected_sales_price` | Currency | fetch_from `home_build_request.selling_price`. Editable for Spec. |
| 34 | Projected Equity | `custom_projected_equity` | Currency | RO, calc = sales_price − loan_amount |
| 35 | Projected LTV | `custom_projected_ltv` | Percent | RO, calc = loan_amount / sales_price × 100 |
| 36 | Projected Payoff | `custom_projected_payoff` | Data | Manual text (e.g. "60-90 days") |
| 37 | | `column_break_preapproval` | Column Break | |
| 38 | Monthly Space Rent | `custom_monthly_space_rent` | Currency | RO, fetch_from `home_build_request.park_space_rent` |
| 39 | Notes | `custom_notes` | Small Text | |

---

## Section 6: Signed documents

| # | Label | Fieldname | Type | Notes |
|---|-------|-----------|------|-------|
| 40 | Signed documents | `dcr_documents_section` | Section Break | Renamed from "Documents" |
| 41 | Signed Packet | `signed_packet` | Attach | RO (populated by DocuSign webhook) |

---

## Section 7: Repayment info (standard ERPNext — hidden/defaulted)

| # | Label | Fieldname | Type | Notes |
|---|-------|-----------|------|-------|
| 42 | Repayment info | `repayment_info` | Section Break | Keep section, contains standard fields |
| 43 | Repayment Method | `repayment_method` | Select | **Hidden**, default "Repay Over Number of Periods" |
| 44 | | `column_break_repayment` | Column Break | |
| 45 | Repayment Period in Months | `repayment_periods` | Int | **Hidden**, default 12 |
| 46 | Company | `company` | Link → Company | Mandatory. **Moved here from old Documents section** |

---

## Hidden fields (keep in form but hidden)

| Fieldname | Notes |
|-----------|-------|
| `applicant_type` | Hidden, default "Customer" |
| `is_term_loan` | Hidden ✓ |
| `is_secured_loan` | Hidden ✓ |
| `description` (Reason) | Hide |
| `loan_security_details_section` | Hide entire section |
| `proposed_pledges` | Hide |
| `maximum_loan_amount` | Hide |
| `repayment_method` | Hidden, default value |
| `repayment_periods` | Hidden, default value |

---

## Removed fields

| Fieldname | Reason |
|-----------|--------|
| `requested_advance_amount` | Redundant with `loan_amount` |
| `first_autopay_description` | Hardcoded in print format |
| `custom_projected_investment` | Equals `loan_amount` |
| `doc_checklist` | Belongs on HBR only |

---

## Notes

- Standard ERPNext fields that appear in Lending Calculations (Monthly Repayment, Total Payable Amount, Total Payable Interest) should NOT also appear in the Repayment Info section — avoid duplicates. If they're visible in Lending Calculations, hide them in Repayment Info.
- `Amended From` (standard ERPNext) — keep at the very bottom, no changes needed.

## Critical implementation notes

**DO NOT create duplicate custom fields with `dcr_` prefixes.** The previous attempt created `dcr_loan_amount`, `dcr_loan_product`, `dcr_company`, `dcr_repayment_amount`, `dcr_total_payable_amount`, `dcr_total_payable_interest` — all duplicates of standard fields. These must be deleted if they still exist.

**Standard ERPNext fields cannot be deleted — only hidden and repositioned.** Use `insert_after` in custom field fixtures to control position. Use Property Setter or Customize Form to set `hidden`, `read_only`, `default`, and `label` on standard fields.

**First step before any changes:** Delete all `dcr_` prefixed custom fields on Loan Application. Revert Customize Form to clean state.

---

## Complete standard field disposition

The standard Loan Application DocType has ~71 fields. Here is the disposition for EVERY standard field. Fields marked "VISIBLE — placed in section X" appear in the numbered field order above. All others are hidden.

### Standard fields — VISIBLE (placed in layout above)

| Fieldname | Placed in section | Row # |
|-----------|------------------|-------|
| `applicant_type` | Header | 1 (hidden but functional) |
| `applicant` | Header | 2 |
| `applicant_name` | Header | 3 |
| `posting_date` | Header | 5 |
| `status` | Header | 6 |
| `loan_product` | Lending | 13 |
| `loan_amount` | Lending | 14 |
| `rate_of_interest` | Lending | 20 |
| `repayment_amount` | Lending calculations | 29 |
| `total_payable_amount` | Lending calculations | 30 |
| `total_payable_interest` | Lending calculations | 31 |
| `company` | Repayment info | 46 |

### Standard fields — HIDDEN

| Fieldname | Label | Reason |
|-----------|-------|--------|
| `is_term_loan` | Is Term Loan | DCR doesn't use |
| `is_secured_loan` | Is Secured Loan | DCR doesn't use |
| `description` | Reason | DCR doesn't use |
| `loan_security_details_section` | Loan Security Details | DCR doesn't do secured loans |
| `proposed_pledges` | Proposed Pledges | DCR doesn't do secured loans |
| `maximum_loan_amount` | Maximum Loan Amount | Not used |
| `repayment_method` | Repayment Method | Default "Repay Over Number of Periods", hidden |
| `repayment_periods` | Repayment Period in Months | Default 12, hidden |
| `repayment_info` | Repayment Info (section) | Section hidden but contains Company |
| `amended_from` | Amended From | Keep at bottom, standard ERPNext |

### Standard fields — hide any others not listed above

Any standard Loan Application field not listed in either table above should be **hidden**. This includes standard section breaks, column breaks, and any other native fields that appear in the form. The goal is: only the 46 fields in the numbered layout above are visible.

---

### General
- **Any renamed fields must be matched on other doctypes if shared** — e.g. if "Deal reference" is the section name on LA, use the same name on Loan, Loan Disbursement, etc.

### Deal reference section
- **HBR link does not work on a blank LA** — starting from a new LA, the Home Build Request link field doesn't connect. Needs investigation — may be a `get_query` or filter issue, or the Link field options aren't set correctly.

### Lending section
- **Merge Exhibit A / ACH fields into Lending section** — Serial No, Quote No, Floor Plan (→ rename to "Model"), Buyer Name should move into the Lending section instead of having a separate Exhibit A / ACH section. Cleaner layout. ✅ Done in field order above.
- **Monthly Interest Amount does not auto-calculate** — needs client-side `on_change` handler wired to `loan_amount` and `rate_of_interest`. ✅ Calculation spec below.

### Exhibit A section (being merged into Lending)
- **"Floor Plan" should be "Model"** — match the label on HBR where the field is called "Model". ✅ Done in field order above.

---

## Auto-calculation logic (client-side JS)

### Lending calculations section

| Field | Formula | Trigger |
|-------|---------|---------|
| `outstanding_loan_balance` | SUM of `outstanding_amount` on all active Loans for this Customer (docstatus=1, status in [Disbursed, Partially Paid]) | On form load + `applicant` change |
| `available_credit` | MIFA `credit_limit` − `outstanding_loan_balance` | Recalculates when `outstanding_loan_balance` changes |
| `custom_current_yn` | Query all active Loans for Customer. Check `Loan Repayment Schedule` for any rows where `payment_date < today()` and `is_paid = 0`. If none overdue → "Yes". If any overdue → "No". | On form load + `applicant` change |
| `monthly_interest_amount` | `(rate_of_interest / 100) × loan_amount / 12` | On `loan_amount` or `rate_of_interest` change |

### Pre-approval letter section

| Field | Formula | Trigger |
|-------|---------|---------|
| `custom_projected_equity` | `custom_projected_sales_price − loan_amount` | On `loan_amount` or `custom_projected_sales_price` change |
| `custom_projected_ltv` | `loan_amount / custom_projected_sales_price × 100` | On `loan_amount` or `custom_projected_sales_price` change |

---

## Fields to default (via client script or fixture)

| Field | Default value |
|-------|--------------|
| `applicant_type` | "Customer" |
| `repayment_method` | "Repay Over Number of Periods" |
| `repayment_periods` | 12 |

---

## fetch_from wiring (all read-only)

| Field on LA | fetch_from | Notes |
|-------------|-----------|-------|
| `home_type` | `home_build_request.home_type` | Already wired |
| `factory` | `home_build_request.factory` | Already wired |
| `home_serial_no` | `home_build_request.home_serial_no` | New — field moving to HBR |
| `quote_no` | `home_build_request.quote_no` | New — field moving to HBR |
| `floor_plan` (label: "Model") | `home_build_request.model_name` | Already wired |
| `buyer_name` | `home_build_request.home_buyer` | Already wired |
| `custom_projected_sales_price` | `home_build_request.selling_price` | Editable for Spec deals |
| `custom_monthly_space_rent` | `home_build_request.park_space_rent` | New — needs `space_rent` field on Park DocType, `park_space_rent` fetch on HBR |

---

## New fields needed on other doctypes

| DocType | Field | Type | Notes |
|---------|-------|------|-------|
| Park | `space_rent` | Currency | Monthly space rent. Label: "Monthly space rent" |
| HBR | `park_space_rent` | Currency | RO, fetch_from `park.space_rent` |
| HBR | `home_serial_no` | Data | Unique, not mandatory |
| HBR | `quote_no` | Data | |

---

## Print format field sources (Pre-Approval letter)

These fields appear on the Advance Pre-Approval print format but are NOT on the LA form. The print format Jinja template pulls them directly from the linked HBR:

| Print format field | Source |
|-------------------|--------|
| Escrow Company | HBR `escrow_company` |
| Escrow Number | HBR `escrow_number` |
| Customer Deposit | HBR `customer_deposit` |
| Lender | HBR `end_buyer_lender` |

---

## Print format changes

- `first_autopay_description` removed from form. ACH Approval print format should hardcode the text and inject the date from `Loan.repayment_start_date`:
  ```
  The first autopay debits will occur on {{ frappe.utils.formatdate(doc.repayment_start_date) }}.
  ```
- `custom_projected_investment` removed from form. Pre-Approval print format should reference `doc.loan_amount` directly.

---

## Connections sidebar

- Add "Lending" as group label for Loan and Loan Security Pledge connections
