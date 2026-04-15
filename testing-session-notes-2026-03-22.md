# DCR Testing Session Notes — March 22, 2026

## Questions for DCR

1. **Bank accounts for lending operations:**
   - Which bank account does DCR disburse factory payments from? (e.g., Chase Trust 9016, or a different account?)
   - Does DCR have a separate ledger account for tracking what dealers owe? (like a "Loans Receivable" or "Dealer Floor Plan Receivable" account — this is the accounting ledger that tracks outstanding dealer balances, not a bank account)
   - Which account receives dealer loan repayments (ACH debits)?
   - These map to the Loan Product setup in ERPNext and need to be correct before disbursements and repayments can be processed.

2. **Supplier Quotation custom fields** — does DCR need `plot_plan`, `signed_by_dealer`, and `signature_date` on factory quotes? These were built but never wired into the flow. Recommend keeping them since we're adding Supplier Quotation → Purchase Invoice to the formal flow.

3. **Credit limit warning** — when a dealer requests more than their MIFA credit limit, should the system block it (hard stop) or just warn (soft warning, currently implemented)?

4. **Bryt replacement scope** — What exactly does Bryt handle today? We believe it's the full loan system end-to-end (origination, servicing, payments, payoffs). Confirm this. Also: how many active loans are currently in Bryt? We need a data export of all open loans with current balances, repayment history, and dealer credit limits for migration.

4. **Set up a Loan Product based on the Goldey/West View deal:**
   - Reference docs: Flooring Loan Worksheet, Exhibit A, ACH Approval (all in project files)
   - Key terms from Goldey deal: $278,100 advance, 12% interest, monthly ACH payments ($2,781 interest + $278 insurance)
   - Check "Is Term Loan", set repayment schedule type, cyclic day of month
   - Configure correct GL accounts (Disbursement Account, Loan Account, Repayment Account, Interest accounts) — depends on DCR's answer to question #1
   - Add `rebate_percentage` custom field once item #5 below is implemented
   - This Loan Product becomes the "Standard" product assigned to dealers via `default_loan_product`

---

## Repo Changes Needed (for Claude Code)

### Customer DocType Cleanup
1. Remove fields: `mifa_required`, `master_dealer_list_updated`, `dcr_application_status`, `dcr_account_no`, `rebate_percentage` — from `hooks.py` and `custom_field.json`
2. Set `dealer_agreement_status` to `read_only: 1` in `custom_field.json`
3. Move `dealer_agreement_status` into Dealer Agreement section with `entity_type`; remove the now-empty Application section break (`dcr_application_section`)
4. Add `Customer-default_loan_product` (Link → Loan Product) in `custom_field.json` and `hooks.py`

### Loan Product
5. Add `rebate_percentage` (Percent) custom field to Loan Product doctype

### MIFA
6. Add `loan_product` Link field to MIFA doctype; set `interest_rate` to `fetch_from: loan_product.rate_of_interest`, read-only
7. Make MIFA submittable (`is_submittable: 1`); require submission before "Send for Signature" button shows in `mifa.js`

### Emails
8. Update `dcr_email.py` `send_dealer_welcome` to use Customer `name` instead of `dcr_account_no`
9. Wire `send_dealer_welcome` into `docusign.py` `_update_reference_document` after Dealer Agreement is signed

### Loan Application
10. Add `fetch_from` on Loan Application: `floor_plan` from `home_build_request.model_name`, `buyer_name` from `home_build_request.home_buyer`, `requested_advance_amount` from `home_build_request.home_invoice_plus_freight`
11. Remove `doc_checklist` (Document Checklist table) from Loan Application — HBR is the source of truth
12. Set `signed_packet` to `read_only: 1`
13. Auto-calculate `custom_projected_equity` (sales price - investment) and `custom_projected_ltv` (investment / sales price) via validate hook in `lending.py`
14. Require Loan Application to be submitted (`docstatus === 1`) before showing "Send for Signature" and "Send Pre-Approval" buttons in `loan_application.js`

### Loan
15. Add `fetch_from` on Loan: `home_serial_no`, `buyer_name`, `factory` from Loan Application
16. Update payoff print formats to read `rebate_percentage` from Loan Product instead of Loan custom field
17. Evaluate replacing Loan custom fee fields (`service_fee_amount`, `late_fees_collected`) with native Loan Charges
18. Set "Is Term Loan" default based on Loan Product

### Home Build Request
19. Remove `home_name` field from HBR doctype
20. Set `status` to `read_only: 1` (and eventually wire auto-update based on checklist + docstatus)
21. Rename `space_number` label from "Space #" to "Space No"

### Sales Order Removal
22. Remove Sales Order from the flow entirely:
    - Delete `sales_order_hooks.py`
    - Remove Sales Order `on_submit` hook from `hooks.py` `doc_events`
    - Remove Sales Order custom fields from fixtures (`home_build_request`, `home_type`, `financing_type`, `property_type`)
    - Remove "Create → Sales Order" button from `home_build_request.js`
    - Remove `sales_order` Link field from HBR doctype
    - Remove `Sales Order-Home Build Request` from DocType Link fixtures
    - Create Loan Application directly from HBR `on_submit` for Floored deals (move logic into `home_build_request.py`)

### Supplier Quotation / Purchase Invoice Flow
23. Wire Supplier Quotation into the HBR flow — add "Create → Supplier Quotation" button on HBR
24. Wire Purchase Invoice into the Loan/Disbursement flow — add "Create → Purchase Invoice" button on Loan, link to Loan Disbursement
25. Keep Supplier Quotation custom fields; rename `factory_po` on Loan Disbursement to `purchase_invoice`

### UX / Buttons
26. Make all "Create →" buttons primary style across all JS files (using `frm.change_custom_button_type`)
27. Set `order_type: 'Sales'` when creating Sales Order from HBR — SKIP, Sales Order being removed
28. Add status indicators on Loan Application, Customer, and MIFA based on signing state (Pending → Sent → Signed → Declined)
29. Add field validation on MIFA "Send for Signature" — require `credit_limit` and `loan_product` before sending

### Hide Lending App Noise
30. Hide irrelevant Lending app sections/connections across doctypes:
    - **Customer:** Loan Details tab, Loyalty Points section
    - **Loan:** Loan Classification Details, Loan Security Pledge/Unpledge in connections, Loan Write Off, Loan Restructure, Days Past Due Log connections
    - **Loan Application:** Loan Security Pledge in connections
    - **Loan Disbursement:** Loan Security Deposit in connections, Withhold Security Deposit checkbox, Is Term Loan checkbox

---

## Manual Changes on Live Instance (Customize Form)

These are NOT in the repo — they were added manually on the live ERPNext instance and need to be deleted via Customize Form:

- Delete **Dealer Contact & Address** section and all fields within: `dealer_contact_name`, `dealer_phone`, `dealer_address`, `dealer_email`, `dealer_city_state_zip`
- Delete **Bank Information** section and all fields within: `bank_name`, `account_type`, `account_last_4`, `bank_city_state`, `routing_last_4`, `name_on_account`
- Hide **Loan Details** tab on Customer (from Lending app) — set `loan_details_tab` to hidden

---

## Testing Results Summary

### Passed ✅
- Document Checklist auto-population (all 8 combinations)
- Submission gate (blocks when docs incomplete)
- MIFA credit calculation ($100k limit - $0 outstanding = $100k available)
- Credit limit warning on over-limit Loan Application
- DocuSign flooring packet (3 docs rendered + envelope sent)
- Webhook completion (Signature Request updated to Signed, signed PDF attached)
- Loan creation from signed Loan Application
- Loan Disbursement creation

### Blocked / Needs Fix 🔴
- Loan Disbursement submit fails: "Party Type and Party can only be set for Receivable/Payable account" — Loan Account on Loan Product is set to a bank account instead of a receivable account. Needs correct GL account from DCR.

### Not Yet Tested ⏳
- Loan buttons (Send Disbursement Notice, FL Payoff, COD Payoff) — blocked by disbursement issue
- Manage Auto-Pay dialog
- Print format previews for payoff letters
- ACH scheduled tasks

---

## Future Track

- **Dealer Portal** via Frappe Web Forms:
  - Doc uploads (W-9, license, permit) during onboarding
  - HBR submission (dealer self-service new home requests)
  - Doc checklist uploads per HBR
  - Include portal link in welcome email
  - Native Frappe portal first, custom frontend later if needed
