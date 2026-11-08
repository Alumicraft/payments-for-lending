# DCR testing handoff

Updated November 8, 2026. This document distinguishes a workflow that is ready to exercise from a test that has already passed. Production collection and accounting approval are separate milestones. Do not reset or delete submitted financial or signed history to make the demo look clean.

## Environment and boundaries

- Hosted app: https://backdesk.dealercapital.net/portal and https://backdesk.dealercapital.net/desk.
- Frappe Cloud Apps readback confirms DCR a6ad9b80f1777569bc8b508ef6b5a93fce44292f. The redesigned portal is installed. The November 8 financial and packet follow-up is awaiting review and deployment.
- DocuSign, Plaid and ACHQ are Sandbox. ACH scope is Controlled Pilot, its pilot loan is blank, and automatic debits are off. Do not enable real collections for testing.
- Status notifications are off. There are 75 Recorded historical notices and zero Queued notices. Enabling the existing global queue would send the backlog to the override recipient. Select a bounded testing window before acceptance of automated status email.
- Dealer identity is Portal Test, customer `DEMO ONLY - Fresh Dealer 20261006`, with the owner's `send2tristan@gmail.com` mailbox. Use the normal email-link sign-in, not shared Administrator credentials. Keep dealer and staff in separate browser sessions.
- The intended staff tester and role are awaiting the owner's answer. Administrator checks do not prove restricted-role acceptance. The earlier Purchase User test account remains disabled.

## Approved financial rules

Actual/360 interest starts at the supplier invoice date. The financed basis includes invoice total and additional financed DCR fees not already on the invoice. Beginning with payment 13, regular monthly principal reduction is 1% of the original financed basis. It continues after an extra payment and beyond the 36-month forecast horizon without an automatic balloon. Extra payments reduce principal immediately; earned unpaid interest remains payable. Round a period or dated payoff total once, and reconcile daily accruals to it. Changed financial terms require a new signed packet.

For Loan 26 the original financed basis is $225,000 and the monthly principal reduction is $2,250. The designer's phrase "original invoice" must not silently change this to $2,200.

## Test records and expected checkpoints

| Record | Purpose | Expected checkpoint |
| --- | --- | --- |
| HBR 37 / application 15 / Loan 26 / funding 13 | Monthly payments, extra principal, payoff and reversal | Fourteen original receipts remain submitted; $220,500 principal; $36,426.75 cash collected. |
| Loan 26 original schedule LN-RS-2026-00020 | Clean continuation after reversal recovery | Active. February 1, 2028 shows $2,250 principal plus $2,278.50 interest, total $4,528.50, demand not yet generated. |
| Loan 26 native repost, November 8 at 13:11:57.981473 | Recovery from the old cancellation path | Completed. No active accruals or demands from January 15, 2028 onward. Valid earned interest through January 14 remains $32,955.75; $31,926.75 collected. All 471 active vouchers balance. |
| HBR 30 / application 14-1 / invoice 10-1 / Loan 27 / draft funding 14 | Revised invoice and replacement signing | $275,000 invoice plus $5,000 fees equals $280,000 financed. Invoice date October 11, 2026; first payment November 1, $1,960. Old signature must not permit funding. |
| HBR 32 / PO 19 | Customer Sold Cash | Saved scenario and normal delivery/reversal path. Cash ownership policy still needs the owner. |
| HBR 33 / PO 20 / cancelled receipt 6 | Inventory and dealer live updates | Ordered after receipt cancellation; submitting a fresh authorized test receipt should move it to Delivered without dealer refresh. |
| HBR 34 | Incomplete intake and insurance upload | Keep as an incomplete example. An uploaded file and a staff waiver must remain distinct. |
| Loan 25 | Month 37, missed payments, charges and normal restructure | Prior bounded cases passed. Do not submit its old advance-payment drafts. |

The Loan 26 dates are synthetic future value dates. Existing GL posting dates reflect when the trial was entered. These cases do not prove calendar rollover or bank settlement.

Private proof is under the original checkout's `output/testing-readiness-2026-11-08/`. The recovered-state verifier checks the interest cutoff and original future schedule, in addition to native principal, cash and complete-voucher balances. It rejects the old incomplete reversal export.

## Acceptance script

Record the tester, role, installed revision, request/loan IDs, expected result, actual result and evidence for each case. A failure stays open; a balance or screenshot alone does not accept its accounting or provider consequences.

| Case | Action and expected result | Position |
| --- | --- | --- |
| T01 Login and ownership | Dealer signs in by email link. A different dealer's records and private files must be denied. Staff uses the intended role. | Dealer path covered; intended staff role open. |
| T02 Customer Sold financed | Save, reload, review, approve and obtain the required documents without presenting review as financing approval. | Implementation and bounded scenarios covered; staff rehearsal open. |
| T03 Customer Sold Cash/COD | Complete native request, order, invoice, delivery and cancellation. Confirm who collects money before posting that variant. | Saved/delivery variants covered; money-handling policy open. |
| T04 Spec | Buyer stays blank, serial may be TBD, quote and final invoice remain distinct. | Covered; revised funding completion open. |
| T05 Inventory | Save/reload, order, receipt and reversal; dealer stage follows source documents. | Covered. |
| T06 Serial checks | Repeated TBD variants are allowed; duplicate assigned serial is rejected appropriately. | Covered. |
| T07 Filters/history | Dealer, factory, quote, serial fragment and dates find active, Closed and Cancelled records and survive reload. | Administrator covered; intended role open. |
| T08 Purchase Order | Inspect native tabs, pricing and amendments. Hidden empty sections must not hide populated data or required draft inputs. | Covered; intended role open. |
| T09 Dates | Invoice interest date, first payment and Off Line Date survive save and reload with an audit trail. | Covered. |
| T10 Map | Verify address, park/space, cards and request navigation, including return after an edit. | Covered. |
| T11 Factory assignment | Confirm real plant/contact and documents, then deliberately send a reviewed packet to the controlled recipient. Assignment submission alone stays quiet. | Final contacts/documents and delivery open. |
| T12 Bank | Complete Plaid return/session and manual-bank path. Connection must not enable autopay. | Existing Sandbox account covered; fresh callback/manual acceptance open. |
| T13 Documents | Staff uploads privately; owner dealer can view/download identical bytes. Waiver is a separate state. | Covered. |
| T14 Signing | Open every PDF, confirm recipient and amounts, sign in embedded flow, return to the same request/session, receive delayed callback once and compare executed copies. | Original email signatures and pending return covered; fresh completed embedded return open. |
| T15 Revised invoice | Original signed record stays available. Replacement sheet shows $275,000 invoice and Exhibit A $280,000 financed. Sign replacement, then fund its matching amount/date. | New sheet mismatch found and fixed in source; deploy and signing open. |
| T16 Funding/fees | Native funding, factory payable/payment and financed fee invoice agree with the packet and general ledger. | Original cases covered; revised funding open. |
| T17 Monthly receipts | Twelve separate interest-only receipts must leave original principal outstanding. | Covered on Loan 26. |
| T18 Curtailment boundary | Payment 12 remains interest-only. Payments 13 and 14 each reduce principal $2,250. | Covered. |
| T19 Long horizon | Payment 37 is an ordinary installment, not a balloon. | Arrears case covered; separate on-time long sequence open. |
| T20 Rounding | Dated schedules, demands, accruals and payoff agree after rounding a period total once. | Covered in bounded examples. |
| T21 Extra principal | $5,000 immediately reduces principal to $215,500; regular curtailment continues. Editing the draft must produce the right carry on the first save. | Forward posting covered; first-save source regression passes, hosted follow-up open. |
| T22 Payoff | Dated letter agrees with actual principal and earned interest; closure reaches zero; dealer status follows. | Covered on Loan 26. |
| T23 Reversal | Cancel later receipts before the extra payment. Native repost must cancel affected future interest/demands and restore the active original schedule. | Manual native recovery covered; automatic follow-up needs hosted acceptance. |
| T24 Financial exceptions | Positive penalty, capitalization, applicable waivers and reversal variants must reconcile all postings. Never alter a global rate just to manufacture a pass. | Charge/tax variants covered; remaining variants and policies open. |
| T25 Notifications | One controlled transition creates one queue record and one delivered email; retry/replay does not duplicate it or release historical notices. | Local behavior covered; bounded hosted delivery open. |
| T26 Phone and themes | Use the real device/browser for navigation, tables, upload/download, signing and bank return. | Dashboard light/dark/phone fixtures covered; full device journey open. |
| T27 Historical loans | Reconcile original contracts, principal events and posted GL per loan, including Loan 14. Preserve valid history. | Exceptions inventoried; accounting review open. |
| T28 Cutover/recovery | Agree collection owner, mappings, opening balances, parallel run, recovery, UCC/insurance/inspection responsibilities and final document wording. | Owner/accounting acceptance after testing. |

## Human inputs and product scope

The owner must sign the replacement Sandbox packet. Staff testing needs a named person and intended role; do not grant broad accounting access to make a test pass. Cash/COD handling, insurance collection/remittance, tax applicability, final legal wording and real factory contacts require business answers. They can be explicit test cases without being treated as production-approved policy.

The setup screen does not block new builds. Enforcing a gate requires approved mandatory items and waivers. Dealers can request payoff letters; the portal does not fabricate a dated quote. Past-due rows contact DCR because dealer payment submission is not implemented. Those are deliberate scope limits, not tested features.

Source checks pass 863 Python tests, 44 subtests and 17 Node test files. Project preflight and v16 reviews found no blockers. Review follow-ups capture dependencies before native cancellation, exclude the payment's own due-date demand as a repost trigger, retain native settlement/LOC handling and require account names in exported proof. Hosted installation, real provider outcomes, human signatures and accounting approval remain separate evidence.
