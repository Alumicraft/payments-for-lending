# DCR Lending — ERPNext Build Plan
*Home Builder Lending Platform · Backdesk · March 2026*

---

## Business Context

**Dealer Capital Resources (DCR)** is a manufactured home floor plan lender operating in California, Arizona, and Oregon. DCR is the client — this is their internal operations system.

DCR serves as the conduit between independent dealers and home manufacturers. **All dealer factory orders route through DCR**, regardless of whether DCR is funding the order. This means:

- **DCR Floored orders** — DCR advances the factory payment on the dealer's behalf. Dealer repays DCR over 12 months via ACH.
- **Cash orders** — Dealer funds the factory payment themselves, but DCR still facilitates the order, collects docs, and coordinates with the factory.

The `financing_type` field determines whether a flooring loan gets originated — not whether DCR is involved. DCR is always involved.

---

## Context & Constraints

- **Platform:** Frappe Cloud (v15)
- **No Server Scripts** — Frappe Cloud disables them. All server-side logic lives in the custom app.
- **Single app** — `payments_for_lending` is renamed to `dcr`. All new doctypes, hooks, and integrations are built directly into this repo.
- **ERPNext Lending module** replaces Bryt entirely — system of record for all loan balances, schedules, repayments, and interest accrual.
- **Flooring loans are term loans** — Frappe Lending auto-generates a fixed repayment schedule on loan creation. 12 months, monthly payments.
- **Third-party factory disbursement** is natively supported in Frappe Lending — the advance goes directly to the factory (Supplier), not through the dealer.
- **AdobeSign** handles all e-signatures via webhook. New account — sandbox setup needed before development starts.
- **Resend** handles all outbound email (Retailer Application, notifications).
- **ACHQ** handles ACH debit origination and payment status tracking. Full integration already built (see below).
- **Custom fields managed via fixtures** in `hooks.py` — not `install.py`. Fixtures auto-sync on `bench migrate`, which Frappe Cloud runs on every deployment.

---

## What's Already Built — payments_for_lending App

A complete ACH autopay system exists in the `payments_for_lending` repo. This is production-quality code, not stubs. The following are **done and do not need to be rebuilt**:

| Component | File | Status |
|---|---|---|
| ACHQ API client | `api/achq_integration.py` | Complete |
| ACH Authorization doctype | `doctype/ach_authorization/` | Complete |
| ACH Transaction doctype | `doctype/ach_transaction/` | Complete |
| ACH Settings doctype | `doctype/ach_settings/` | Complete |
| Scheduled debit initiation | `tasks/scheduled_debits.py` | Complete |
| ACHQ webhook handler | `api/achq_integration.py` | Complete |
| Hourly polling fallback | `tasks/scheduled_debits.py` | Complete |
| Retry logic (R-code aware) | `ach_transaction.py` | Complete |
| Payment Entry creation on success | `ach_transaction.py` | Complete |
| Plaid integration | `api/achq_integration.py` | Complete |
| Autopay management UI | `public/js/loan.js` | Complete |

### Key Architecture Points

**ACH Authorization owns all bank details.** Routing/account numbers are tokenized via ACHQ — only last 4 digits and the ACHQ token are stored. No bank fields on Customer.

**Authorization resolution logic** (`get_loan_payment_account`):
1. Check `loan.ach_payment_account` override (if active) → use it
2. If override exists but is revoked → fail explicitly, no silent fallback
3. Check customer's default Authorization → use it
4. No valid account → return None

**Retry logic** is return-code aware:
- R01, R09 (funding issues) → retry up to `max_retry_attempts`
- R02–R29 (account/authorization issues) → no retry
- D01, S-codes (ACHQ pre-flight rejections) → no retry

### Required Fixes Before Production

The existing code was built with consumer lending assumptions. The following must be corrected for DCR's B2B dealer context:

| Issue | Current | Fix | File |
|---|---|---|---|
| SEC Code default | `WEB` (consumer internet) | `CCD` (corporate debit) | `ach_settings.json` |
| Check Type default | `Personal` | `Business` | `ach_settings.json` + `achq_integration.py` |
| Repayment schedule `is_paid` | Field doesn't exist in Frappe Lending v15 | Query `Loan Repayment` records to determine paid status | `scheduled_debits.py` |
| Repayment amount | Reads `monthly_repayment_amount` (doesn't exist) | Read `row.total_payment` from matched schedule row | `scheduled_debits.py` |
| Duplicate dict key bug | `process_retry_transactions()` has `next_retry_date` twice in filter | Fix to use proper list-based filters | `scheduled_debits.py` |
| Consent language | Consumer-oriented ("my bank account") | B2B language referencing business authorization | `loan.js` |
| Email templates | Referenced but don't exist | Create `ach_payment_success`, `ach_payment_failure`, `ach_payment_upcoming` | New |
| `hooks.py` missing `after_install` | `install.py` functions not wired | Move to fixtures approach, remove `install.py` | `hooks.py` |

**Corrected repayment schedule logic:**
```python
def get_next_unpaid_repayment(loan):
    """Get next unpaid repayment from loan schedule."""
    paid_dates = frappe.get_all("Loan Repayment",
        filters={"against_loan": loan.name, "docstatus": 1},
        pluck="posting_date")
    paid_dates = set(getdate(d) for d in paid_dates)

    for row in loan.repayment_schedule:
        row_date = getdate(row.payment_date)
        if row_date >= getdate(today()) and row_date not in paid_dates:
            return row_date, row.total_payment
    return None, None
```

### Bank Account Management — Moved to Customer Level

Bank account setup happens during **dealer onboarding**, not at the loan level. This is a flow change from the original design:

**During onboarding:**
1. Customer record created for dealer
2. Dealer connects bank account via Plaid (primary) or manual entry (fallback) on the Customer form
3. ACH Authorization created, set as customer default
4. Bank details (bank name, last 4 digits) available for all future print formats
5. When a flooring loan is originated, the ACH Approval print format auto-populates from the existing ACH Authorization

**Account changes:**
1. "Manage Bank Account" button on Customer form (visible when `customer_group = Dealer`)
2. Dealer connects new account via Plaid or manual entry
3. New ACH Authorization created, set as default
4. Old authorization revoked — existing code handles this (cancels pending transactions, warns about active loans)
5. All active loans automatically pick up the new default
6. No re-signing of ACH Approval needed — original authorization covers any account on file

**Per-loan override** remains available for edge cases where a dealer wants a specific loan debited from a different account.

**UI changes:**
- Primary bank account management moves from `loan.js` to new `customer.js`
- Loan form simplified: shows which account is being used (read-only), allows override only if needed

---

## What We're Building (Remaining Scope)

Three interconnected workflows:

```
New Dealer Onboarding
        |
New Home Build Request  <-->  Flooring Loan (if DCR Floored)
        |
Factory PO --> Build --> Delivery --> ACH Repayment  <-- existing payments code handles this
```

| Manual Pain Today | ERPNext Solution |
|---|---|
| Not knowing which docs are required per order | `get_required_docs()` — fill in 3 fields, get the exact checklist |
| Nothing stops a PO going out without all docs | Document Checklist submit validator — system blocks it |
| Dealer onboarding status lives in email | Customer record (Dealer fields) — one record showing everything |
| Manually filling in Exhibit A and ACH Approval | Jinja print formats — auto-populated from ERPNext data |
| Chasing signed docs and filing them manually | AdobeSign webhook — fully automated |
| Checking Bryt for dealer balances | Live ERPNext Loan query — no external system |
| Manual ACH debit initiation | Scheduled jobs — fully automated |

---

## Architecture: Single App

On Frappe Cloud, Server Scripts are disabled. All business logic lives in the custom app. `payments_for_lending` is renamed to `dcr` before development begins. One repo, one install, one place to debug.

### What Lives in the App (`dcr`)
- All existing ACHQ integration code (with B2B fixes)
- All new custom Doctypes (JSON definitions)
- All custom fields on native doctypes (via fixtures)
- All `hooks.py` document event handlers
- `get_required_docs()` server method
- Outstanding balance query
- Submit validators
- AdobeSign webhook endpoint + API calls
- Resend email integration
- All whitelisted API methods

### What Lives in the ERPNext UI
- **Workflows** — Home Build Request + Flooring Loan state machines
- **Print Formats** — Jinja templates, iterated in the UI
- **User Roles & Permissions**

---

## The Three Flows

### Flow 1 — New Dealer Onboarding

1. Create **Customer** record with `customer_group = Dealer` — dealer-specific fields appear via `depends_on` conditions. No separate Dealer doctype.
2. Dealer connects bank account via **Plaid** (or manual entry) on Customer form → ACH Authorization created as default.
3. **Dealer Agreement** auto-generated and sent via AdobeSign on Customer save when `dealer_agreement_status = Not Sent`. Also available as manual **Send Agreement** button.
4. AdobeSign webhook fires on dealer signature → **Signature Request** record updated → signed PDF attached automatically.
5. Complete **DCR Application** section on Customer — doc package fields populated, status updated.
6. If flooring needed (`mifa_required = checked`): generate **MIFA** → same AdobeSign flow. `credit_limit` set on MIFA creation — source of truth for all available_credit calculations.
7. **Factory Assignment** created → Retailer Application email auto-sent via Resend.
8. Factory confirms → LOA saved → Master Dealer List updated.

### Flow 2 — New Home Build Request

> **Why this is separate from the Loan Application:** Not every home build has a loan. Cash deals never touch the Lending module. Creating a Loan Application for every order would pollute the lending ledger and break Frappe Lending's accounting. The Home Build Request is the universal intake form. A Loan Application is only created when `financing_type = DCR Floored`.

1. Dealer contacts you — create **Home Build Request**
2. Set 3 fields: `home_type`, `financing_type`, `property_type`
3. `get_required_docs()` runs → **Document Checklist** auto-populated
4. Collect docs until all rows = Received/Verified
5. Submit validator confirms checklist complete → **Sales Order** created
6. If DCR Floored → Flooring Loan flow triggered

**Doc requirements lookup:**

| home_type | financing_type | property_type | Required Docs |
|---|---|---|---|
| Spec | — | Park | Spec Info Sheet, Storage Agreement, Park Agreement, Factory Quote, Plot Plan |
| Spec | — | Private | Spec Info Sheet, Factory Quote, Plot Plan, 50% Deposit |
| Customer Sold | DCR Floored | — | Triggers Flooring Loan flow |
| Customer Sold | Cash | Park | Retail Sold Info Sheet, Purchase Contract, Escrow, Factory Quote, Plot Plan, Loan Approval, Park Approval, Insurance |
| Customer Sold | Cash | Private | Cash Private Info Sheet, Purchase Contract, Escrow, Factory Quote, 50% Deposit |

### Flow 3 — Flooring Docs & Loan Origination

1. **Loan Application** created from Home Build Request (DCR Floored only)
2. Outstanding balance: `SUM(outstanding_amount) WHERE applicant = customer AND status IN ('Disbursed', 'Active')` — pure ERPNext query
3. `available_credit = MIFA.credit_limit - outstanding_balance`
4. Advance date validated against `Supplier.current_lead_time_days`
5. Generate **Exhibit A** + **ACH Approval** (Jinja print formats — bank details pulled from dealer's default ACH Authorization)
6. Combined packet → AdobeSign → webhook → **Signature Request** record updated → signed packet attached
7. **Loan** created in Frappe Lending — fixed repayment schedule auto-generated (term loan)
8. **Loan Disbursement** — advance goes directly to factory (Supplier) via native third-party disbursement
9. **Purchase Order** created and linked
10. Scheduled jobs handle debit initiation, status tracking, retry, and Payment Entry creation automatically (bank account already set up during onboarding)

---

## Doctypes

### Customer *(native — extended)*
No separate Dealer doctype. Dealer-specific fields added directly to Customer, shown only when `customer_group = Dealer` via `depends_on`. Bank details owned by ACH Authorization (existing doctype). DCR Application fields merged directly into Customer (no separate doctype).

**Dealer Information Fields:**

| Field | Type | Notes |
|---|---|---|
| dealer_license_no | Data | |
| license_expiry_date | Date | Renewal alert trigger |
| sellers_permit_no | Data | |
| w9_status | Select | Pending / Received / Verified |
| mifa_required | Check | Floored dealers only |
| dealer_agreement_status | Select | Not Sent / Sent / Signed |
| master_dealer_list_updated | Check | |

**DCR Application Fields** (merged into Customer — no separate doctype):

| Field | Type | Notes |
|---|---|---|
| dcr_application_status | Select | Initiated / In Review / Approved / Rejected |
| dcr_account_no | Data | |
| dealer_license_copy | Attach | |
| sellers_permit_copy | Attach | |
| w9_copy | Attach | |
| retailer_application_copy | Attach | |

### Signature Request *(custom — standalone)*
Standalone doctype linked to Customer. Tracks the AdobeSign lifecycle for all document types. Appears in Customer's Connections sidebar for full e-signature history.

| Field | Type | Notes |
|---|---|---|
| customer | Link → Customer | |
| reference_doctype | Link → DocType | The originating doctype (Customer, MIFA, Loan Application) |
| reference_name | Dynamic Link | The specific record that triggered this signature |
| document_type | Select | Dealer Agreement / MIFA / Flooring Packet |
| adobesign_envelope_id | Data | Webhook matching key |
| status | Select | Not Sent / Sent / Signed / Declined |
| sent_date | Datetime | |
| signed_date | Datetime | |
| signed_attachment | Attach | Downloaded by webhook on completion |

### Document Checklist *(custom child table)*
One shared child table used across Customer (onboarding), Home Build Request, and Loan Application. Frappe handles `parenttype` natively. Submit validator blocks submission until all required rows are Received/Verified.

| Field | Type | Notes |
|---|---|---|
| document_type | Select | W-9, Dealers License, Voided Check, Purchase Contract, Escrow Proof, Factory Quote, Plot Plan, Park Approval, Loan Approval, Insurance, Storage Agreement, Park Agreement, 50% Deposit Proof |
| status | Select | Pending / Received / Verified / Waived |
| attachment | Attach | |
| received_date | Date | |

### MIFA *(custom)*
Floored dealers only. `credit_limit` is the source of truth for all available_credit calculations. Credit limits were in Bryt — must be entered manually at cutover.

| Field | Type | Notes |
|---|---|---|
| customer | Link → Customer | |
| mifa_date | Date | |
| credit_limit | Currency | Source of truth for available_credit |
| interest_rate | Percent | |
| payment_terms | Text | Confirm with DCR |
| signed_mifa | Attach | Populated by AdobeSign webhook |

### Factory Assignment *(custom)*

| Field | Type | Notes |
|---|---|---|
| customer | Link → Customer | |
| factory | Link → Supplier | |
| assignment_date | Date | |
| retailer_application_status | Select | Not Submitted / Submitted / Approved / Rejected |
| letter_of_authorization | Attach | |
| loa_date | Date | |
| active | Check | |

### Home Build Request *(custom)*
Universal intake form. Loan Application only created if `financing_type = DCR Floored`.

| Field | Type | Notes |
|---|---|---|
| customer | Link → Customer | |
| home_type | Select | Spec / Customer Sold |
| financing_type | Select | Cash / DCR Floored |
| property_type | Select | Park / Private Property |
| home_name | Data | Used for doc naming |
| factory | Link → Supplier | |
| factory_quote | Link → Quotation | |
| sales_order | Link → Sales Order | |
| loan_application | Link → Loan Application | DCR Floored only |
| status | Select | Draft / Docs Pending / Ready to PO / PO Submitted |
| doc_checklist | Table → Document Checklist | Auto-populated by get_required_docs() |

---

## Native Doctypes — Custom Fields Only

All custom fields managed via fixtures in `hooks.py`.

### Supplier
- `standard_lead_time_days` (Int)
- `current_lead_time_days` (Int) — advance date validation

### Quotation
- `home_build_request` (Link), `plot_plan` (Attach), `signed_by_dealer` (Check), `signature_date` (Date)

### Sales Order
- `home_build_request` (Link), `home_type`, `financing_type`, `property_type` (Data, read-only)

### Loan Application *(Frappe Lending)*
- `home_build_request` (Link)
- `home_type` (Select) — drives print format variant
- `requested_advance_amount` (Currency)
- `outstanding_loan_balance` (Currency) — SUM from ERPNext Loan records
- `available_credit` (Currency) — MIFA.credit_limit - outstanding_loan_balance
- `advance_date_requested` (Date)
- `signed_packet` (Attach)
- `doc_checklist` (Table → Document Checklist)

### Loan *(Frappe Lending)*
- `ach_payment_account` (Link → ACH Authorization) — per-loan payment override. Already referenced in existing resolution logic.

### Loan Disbursement *(Frappe Lending)*
- `home_build_request` (Link), `factory_po` (Link → Purchase Order), `factory` (Link → Supplier)

---

## App Code — Key Methods

### `get_required_docs(home_type, financing_type, property_type)`
Client Script on field change in Home Build Request. Returns required document types for the combination. Populates Document Checklist child table.

### `get_dealer_outstanding_balance(customer)`
```python
frappe.db.get_list('Loan',
    filters={'applicant': customer, 'status': ['in', ['Disbursed', 'Active']]},
    fields=['outstanding_amount']
)
# SUM outstanding_amount — no external API
```

### `validate_advance_date(factory, requested_date)`
Reads `Supplier.current_lead_time_days`. Raises hard error if date not achievable. Runs on Loan Application submit.

### `POST /api/method/dcr.api.adobesign_webhook`
Receives `AGREEMENT_ACTION_COMPLETED`. Matches `envelope_id` to Signature Request record. Updates status, downloads signed PDF, attaches to record, triggers workflow transition on the referenced document.

### `send_dealer_agreement(customer)`
Auto-triggered on Customer save when `customer_group = Dealer` and `dealer_agreement_status = Not Sent`. Also exposed as manual **Send Agreement** button. Creates a Signature Request record with `reference_doctype = Customer`.

### `send_retailer_application_email(factory_assignment)`
`on_submit` on Factory Assignment when `retailer_application_status = Submitted`. Sends via Resend.

---

## Print Formats (ERPNext UI — Jinja)

| Format | Source Doctype | Notes |
|---|---|---|
| Exhibit A | Loan Application | Spec vs. Sold conditional blocks from `home_type` |
| ACH Approval | Loan Application | Bank details pulled from dealer's default ACH Authorization (last 4 digits, not raw numbers) |
| New Home Info Sheet | Home Build Request | Single dynamic template — conditional blocks for all 5 variants |
| Dealer Agreement | Customer | Signature Request record created on send |
| MIFA | MIFA | Signature Request record created on send |

---

## File Storage

Signed documents stored on the **Signature Request** record (standalone doctype linked to Customer). Frappe's Connections sidebar on Customer shows all linked Signature Requests, HBRs, Loans, MIFAs, etc. No duplicate attachment filing needed — all documents are accessible through their linked records.

---

## Testing Strategy

Targeted tests for code that handles money or gates critical business logic. Tests written alongside the methods they cover, not as a separate phase.

### Existing Payments Code (~1 day)

| Method | Why |
|---|---|
| `get_loan_payment_account()` | Wrong resolution = wrong account debited |
| `should_retry()` | Wrong R-code routing = missed revenue or harassing closed accounts |
| `create_payment_entry()` | Wrong amount/account/reference = bad books |
| `get_next_unpaid_repayment()` | Reads repayment schedule — must match Frappe Lending v15 schema exactly |
| Transaction state transitions | Invalid transitions must be blocked |

### New Business Logic (~1-1.5 days)

| Method | Why |
|---|---|
| `get_required_docs()` | Core intake logic — wrong checklist = wrong docs collected |
| `get_dealer_outstanding_balance()` + available_credit | Wrong balance = over-lending or blocking valid loans |
| `validate_advance_date()` | Wrong date = wrong disbursement timing |
| Document Checklist submit validator | This is the gate that prevents premature POs |
| AdobeSign webhook handler | Envelope matching, status updates, attachment logic |

### Not Tested
- Basic doctype CRUD (Frappe framework behavior)
- Print format rendering
- UI interactions
- ACHQ/Plaid API calls (mock the HTTP layer, test logic around it)

---

## Recommended Build Order

| # | Component | Notes | Est. Days |
|---|---|---|---|
| 1 | AdobeSign sandbox setup | New account — register webhook URL, get API credentials | 1 |
| 2 | Frappe Lending config | Term loan product, 12mo/monthly, Chart of Accounts (user handles CoA) | 1 |
| 3 | Rename app `payments_for_lending` → `dcr` | Rename directories, update all import paths, module references, hooks, scheduled tasks. Remove `install.py`, move custom fields to fixtures. | 1 |
| 4 | Fix payments code for B2B + verify repayment schedule | SEC code → CCD, check type → Business, fix `is_paid`/`monthly_repayment_amount`, fix retry filter bug, update consent language. Test against real Loan record. | 1 |
| 5 | Customer custom fields + Signature Request doctype | Dealer info fields, DCR Application fields (merged into Customer), bank account management UI (`customer.js`). Signature Request as standalone doctype with `reference_doctype`/`reference_name`. | 1.5 |
| 6 | Document Checklist child table + submit validator | Shared by HBR, Loan Application, Customer. Blocks submission until complete. | 0.5 |
| 7 | Factory Assignment + Supplier custom fields | Lead time fields needed before HBR validation. | 0.5 |
| 8 | Home Build Request + `get_required_docs()` | Core intake doctype + branch logic + tests. | 1.5 |
| 9 | MIFA | Credit limit source of truth + AdobeSign send flow. | 0.5 |
| 10 | Dealer Agreement auto-send + manual button | Depends on Signature Request doctype. | 0.5 |
| 11 | Loan Application custom fields + balance query | Depends on MIFA (credit limit) and Frappe Lending config. | 1 |
| 12 | AdobeSign webhook handler | Matches envelope_id to Signature Request, downloads signed PDF, updates status. | 1.5 |
| 13 | Print formats | Info Sheet (5 variants) + Exhibit A + ACH Approval + Dealer Agreement + MIFA | 2.5 |
| 14 | Resend email integration | Retailer Application email on Factory Assignment submit. | 0.5 |
| 15 | Workflows (ERPNext UI) | Home Build Request + Flooring Loan state machines. | 1 |
| 16 | Tests | Payments tests + new business logic tests (written alongside but final verification here). | 0.5 |
| 17 | QA + integration testing | End-to-end flows: onboarding → HBR → loan origination → ACH debit. AdobeSign sandbox + ACHQ sandbox. | 3 |

---

## Revised Estimate

~5-6 days of ACH work already complete. Remaining scope:

| Phase | Days |
|---|---|
| AdobeSign sandbox + Frappe Lending config | 2 |
| App rename + B2B fixes + repayment schedule verification | 2 |
| Customer fields + Signature Request + bank account UI | 1.5 |
| Document Checklist + Factory Assignment | 1 |
| Home Build Request + `get_required_docs()` | 1.5 |
| MIFA + Dealer Agreement send | 1 |
| Loan Application fields + balance query | 1 |
| AdobeSign webhook handler | 1.5 |
| Print formats | 2.5 |
| Resend email + Workflows | 1.5 |
| Tests + QA + integration testing | 3.5 |
| **Total remaining** | **~19.5 days** |

---

## Decisions Log

| # | Decision | Rationale |
|---|---|---|
| 1 | Customer fields, not separate Dealer doctype | `depends_on = Dealer` — simpler, no extra navigation |
| 2 | HBR separate from Loan Application | Cash deals never touch Lending module |
| 3 | Term loan, 12 months, monthly | Fixed repayment schedule auto-generated |
| 4 | AdobeSign — new account needed | Sandbox setup before development |
| 5 | MIFA.credit_limit is source of truth | Was in Bryt, entered manually at cutover |
| 6 | ACH Authorization owns bank details | Tokenized via ACHQ, not stored on Customer |
| 7 | Signature Request as standalone doctype | Not a child table — scales better, cleaner queries, appears in Connections sidebar |
| 8 | One shared Document Checklist child table | Frappe handles `parenttype` natively across Customer, HBR, Loan Application |
| 9 | Fixtures for custom fields, not install.py | Auto-sync on `bench migrate`, standard for Frappe Cloud |
| 10 | No data migration except contacts | Clean start — credit limits entered manually into MIFAs |
| 11 | Bank account management on Customer form | Dealer links account during onboarding via Plaid (primary) or manual entry. All future loans use this default. |
| 12 | Account on file covers changes | No re-signing of ACH Approval when dealer changes bank account |
| 13 | SEC code = CCD, Check Type = Business | B2B corporate debit, not consumer |
| 14 | DCR Application merged into Customer | Just fields + attachments — not enough for a standalone doctype |
| 15 | No auto-filing PDFs to Customer attachments | Linked docs via Connections sidebar are sufficient |
| 16 | Resend for all outbound email | Not Frappe built-in |
| 17 | Formal ERPNext Workflows | HBR + Flooring Loan state machines configured in UI |
| 18 | Exhibit A and ACH Approval as separate print formats | Kept separate despite being sent as one AdobeSign packet |
| 19 | Targeted tests for money + gates | ~2.5 days total across payments code and new business logic |

---

## Open Questions — Resolved

| # | Question | Resolution |
|---|---|---|
| 1 | Separate Dealer doctype or Customer fields? | Customer fields with `depends_on = Dealer` |
| 2 | Why separate HBR from Loan Application? | Cash deals never touch Lending |
| 3 | Term or demand loan? | Term loan — fixed schedule |
| 4 | AdobeSign account? | New account — sandbox first |
| 5 | Where does credit limit live? | MIFA.credit_limit |
| 6 | Does every dealer have a MIFA? | Floored dealers only |
| 7 | When is Dealer Agreement sent? | Auto on save + manual button |
| 8 | Customer bank fields? | Dropped — ACH Authorization owns all |
| 9 | ACH debit lifecycle? | Done — existing payments code |
| 10 | Payment frequency + term? | 12 months, monthly |
| 11 | Frappe Lending installed? | Yes — confirmed on site |
| 12 | ACHQ credentials? | In progress — sandbox first |
| 13 | E-Signature tracking? | Standalone Signature Request doctype, not child table |
| 14 | Document Checklist shared? | One child table, Frappe handles parenttype |
| 15 | Custom fields via install.py or fixtures? | Fixtures |
| 16 | Data migration? | Contacts only — clean start |
| 17 | Bank account setup flow? | Plaid on Customer form during onboarding |
| 18 | Account change re-signing? | No — account on file covers it |
| 19 | DCR Application? | Merged into Customer fields |

## Open Questions — Still Pending

- [ ] **Bryt credit limit migration** — how many active dealers? Credit limits need to be manually entered into MIFA records at cutover.
- [ ] **ACHQ sandbox credentials** — needed to begin end-to-end ACH testing. Production credentials to follow.
