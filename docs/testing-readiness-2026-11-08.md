# DCR testing handoff

Updated November 8, 2026. This document distinguishes a workflow that is ready to exercise from a test that has already passed. Production collection and accounting approval are separate milestones. Do not reset or delete submitted financial or signed history to make the demo look clean.

## Environment and boundaries

- Hosted app: https://backdesk.dealercapital.net/portal and https://backdesk.dealercapital.net/desk.
- Frappe Cloud Apps readback confirms DCR f07c727dfe3d6dc5b0917ebaa5098dfeb7a46fe4. The redesign, financial/packet fixes and bank reconnect fix are installed. DCR-only deployment 71l1b84eji succeeded in 3m19s. Automatic extra-payment reversal passed hosted acceptance.
- DocuSign, Plaid and ACHQ are Sandbox. ACH scope is Controlled Pilot, its pilot loan is blank, and automatic debits are off. Do not enable real collections for testing.
- Status notifications are off after the controlled trial. Enabling creates a fresh server-time delivery window. None of the 75 historical notices were released. A new HBR 33 storage transition created exactly one native queue record, deokkk26i2, but actual delivery failed because No Reply has no SMTP password. The follow-up routes new pilot notices through the installed Emails service, using a durable claim before the provider call. Sending and Outcome Unknown notices never retry automatically. Dispatch reads the current locked row, accepts one plain email address and processes at most five current-window service notices per run. Verify actual mailbox delivery and replay after deployment.
- Dealer identity is Portal Test, customer `DEMO ONLY - Fresh Dealer 20261006`, with the owner's `send2tristan@gmail.com` mailbox. Use the normal email-link sign-in, not shared Administrator credentials. Keep dealer and staff in separate browser sessions.
- Tristan confirmed that he or Bob will test, and both use Administrator. The intended staff acceptance role is therefore Administrator; a broader restricted-role rollout remains separate. The earlier Purchase User test account remains disabled.

## Approved financial rules

Actual/360 interest starts at the supplier invoice date. The financed basis includes invoice total and additional financed DCR fees not already on the invoice. Beginning with payment 13, regular monthly principal reduction is 1% of the original financed basis. It continues after an extra payment and beyond the 36-month forecast horizon without an automatic balloon. Extra payments reduce principal immediately; earned unpaid interest remains payable. Round a period or dated payoff total once, and reconcile daily accruals to it. Changed financial terms require a new signed packet.

For Loan 26 the original financed basis is $225,000 and the monthly principal reduction is $2,250. The designer's phrase "original invoice" must not silently change this to $2,200.

## Test records and expected checkpoints

| Record | Purpose | Expected checkpoint |
| --- | --- | --- |
| HBR 37 / application 15 / Loan 26 / funding 13 | Monthly payments, extra principal, payoff and reversal | Fourteen original receipts remain submitted; $220,500 principal; $36,426.75 cash collected. |
| Loan 26 original schedule LN-RS-2026-00020 | Clean continuation after reversal recovery | Active. February 1, 2028 shows $2,250 principal plus $2,278.50 interest, total $4,528.50, demand not yet generated. |
| Loan 26 automatic native repost, November 8 at 14:08:40.259039 | Cancellation of amendment LM-REP-0039-1 after generating its future accrual and demand | Completed automatically. Restored $220,500 principal, $36,426.75 cash, the 14 original receipts and the original active schedule. No stale future accruals/demands remain from January 15, 2028 onward. Earned interest through January 14 is $32,955.75; $31,926.75 collected. All 471 active vouchers balance across 945 GL rows. |
| HBR 30 / application 14-1 / invoice 10-1 / Loan 27 / draft funding 14 | Revised invoice and replacement signing | $275,000 invoice plus $5,000 fees equals $280,000 financed. Invoice date October 11, 2026; first payment November 1, $1,960. Old signature must not permit funding. |
| HBR 32 / PO 19 | Customer Sold Cash | Saved scenario and normal delivery/reversal path. Owner confirms DCR collects from the dealer and pays the factory. Verify the collection/payable path under that rule. |
| HBR 33 / PO 20 / cancelled receipt 6 | Inventory and dealer live updates | Ordered after receipt cancellation; submitting a fresh authorized test receipt should move it to Delivered without dealer refresh. |
| HBR 34 | Incomplete intake and insurance upload | Keep as an incomplete example. An uploaded file and a staff waiver must remain distinct. |
| Loan 25 | Month 37, missed payments, charges and normal restructure | Prior bounded cases passed. Do not submit its old advance-payment drafts. |

The Loan 26 dates are synthetic future value dates. Existing GL posting dates reflect when the trial was entered. These cases do not prove calendar rollover or bank settlement.

Private proof is under the original checkout's `output/testing-readiness-2026-11-08/`. The recovered-state verifier checks the interest cutoff and original future schedule, in addition to native principal, cash and complete-voucher balances. It rejects the old incomplete reversal export.

## Acceptance script

Record the tester, role, installed revision, request/loan IDs, expected result, actual result and evidence for each case. A failure stays open; a balance or screenshot alone does not accept its accounting or provider consequences.

| Case | Action and expected result | Position |
| --- | --- | --- |
| T01 Login and ownership | Dealer signs in by email link. A different dealer's records and private files must be denied. Staff uses the intended role. | Fresh dealer login covered November 8; owner confirms Administrator for Tristan/Bob. |
| T02 Customer Sold financed | Save, reload, review, approve and obtain the required documents without presenting review as financing approval. | Implementation and bounded scenarios covered; staff rehearsal open. |
| T03 Customer Sold Cash/COD | DCR collects from the dealer and pays the factory. Complete native request, order, invoice, collection, supplier payment, delivery and cancellation. | Saved/delivery variants covered; owner settled money handling November 8; collection/account mapping acceptance remains. |
| T04 Spec | Buyer stays blank, serial may be TBD, quote and final invoice remain distinct. | Covered; revised funding completion open. |
| T05 Inventory | Save/reload, order, receipt and reversal; dealer stage follows source documents. | Covered. |
| T06 Serial checks | Repeated TBD variants are allowed; duplicate assigned serial is rejected appropriately. | Covered. |
| T07 Filters/history | Dealer, factory, quote, serial fragment and dates find active, Closed and Cancelled records and survive reload. | Administrator covered; intended role open. |
| T08 Purchase Order | Inspect native tabs, pricing and amendments. Hidden empty sections must not hide populated data or required draft inputs. | Covered; intended role open. |
| T09 Dates | Invoice interest date, first payment and Off Line Date survive save and reload with an audit trail. | Covered. |
| T10 Map | Verify address, park/space, cards and request navigation, including return after an edit. | Covered. |
| T11 Factory assignment | Confirm real plant/contact and documents, then deliberately send a reviewed packet to the controlled recipient. Assignment submission alone stays quiet. | Final contacts/documents and delivery open. |
| T12 Bank | Complete Plaid return/session and manual-bank path. Connection must not enable autopay. | Fresh approved Sandbox login, account selection, callback, saved bank and same authenticated portal return passed after PR #135. First Platypus 0000 is the sole default; prior connections are preserved. Autopay remains off. Manual verification now has a staff Customer entry point and no longer requires enabling debits. These accounts remain Paused with no recorded dealer debit consent; resume refuses until authorization is recorded. Follow-up deployment/hosted acceptance pending. |
| T13 Documents | Staff uploads privately; owner dealer can view/download identical bytes. Waiver is a separate state. | Covered. |
| T14 Signing | Open every PDF, confirm recipient and amounts, sign in embedded flow, return to the same request/session, receive delayed callback once and compare executed copies. | Original email signatures and pending return covered; fresh completed embedded return open. |
| T15 Revised invoice | Original signed record stays available. Replacement sheet shows $275,000 invoice and Exhibit A $280,000 financed. Sign replacement, then fund its matching amount/date. | Corrected hosted PDFs visually reviewed on all five pages; SIG-0197 sent and Gmail delivery confirmed. Owner reports signing through the portal, but current DCR readback remains Sent with no signed PDF. Completion reconciliation and revised funding remain. |
| T16 Funding/fees | Native funding, factory payable/payment and financed fee invoice agree with the packet and general ledger. | Original cases covered; revised funding open. |
| T17 Monthly receipts | Twelve separate interest-only receipts must leave original principal outstanding. | Covered on Loan 26. |
| T18 Curtailment boundary | Payment 12 remains interest-only. Payments 13 and 14 each reduce principal $2,250. | Covered. |
| T19 Long horizon | Payment 37 is an ordinary installment, not a balloon. | Arrears case covered; separate on-time long sequence open. |
| T20 Rounding | Dated schedules, demands, accruals and payoff agree after rounding a period total once. | Covered in bounded examples. |
| T21 Extra principal | $5,000 immediately reduces principal to $215,500; regular curtailment continues. Editing the draft must produce the right carry on the first save. | Hosted amendment 39-1 passed first-save changes in both directions: January 16 carry $1,102.50 and next total $4,501.83; reverting to January 15 restored $1,029 and $4,500.17. Submitted extra principal, future accrual and unpaid demand reconcile across 490 complete vouchers. Normal cancellation automatically triggered the scoped native repost and restored the complete clean checkpoint. |
| T22 Payoff | Dated letter agrees with actual principal and earned interest; closure reaches zero; dealer status follows. | Covered on Loan 26. |
| T23 Reversal | Cancel later receipts before the extra payment. Native repost must cancel affected future interest/demands and restore the active original schedule. | Automatic cancellation/repost passed hosted on November 8 after a new submitted extra payment, future accrual and unpaid demand. The original checkpoint is fully restored. |
| T24 Financial exceptions | Positive penalty, capitalization, applicable waivers and reversal variants must reconcile all postings. Never alter a global rate just to manufacture a pass. | Charge/tax variants covered; remaining variants and policies open. |
| T25 Notifications | One controlled transition creates one queue record and one delivered email; retry/replay does not duplicate it or release historical notices. | One queue and zero historical releases confirmed hosted; actual native transport failed due to missing SMTP configuration. Existing Emails service transport and outcome/replay guards are in the follow-up; actual delivery acceptance pending. |
| T26 Phone and themes | Use the real device/browser for navigation, tables, upload/download, signing and bank return. | Dashboard light/dark/phone fixtures covered; full device journey open. |
| T27 Historical loans | Reconcile original contracts, principal events and posted GL per loan, including Loan 14. Preserve valid history. | Exceptions inventoried; accounting review open. |
| T28 Cutover/recovery | Agree collection owner, mappings, opening balances, parallel run, recovery, UCC/insurance/inspection responsibilities and final document wording. | Owner/accounting acceptance after testing. |

## Human inputs and product scope

The owner reported signing replacement Sandbox packet SIG-0197 through the dealer portal; current DCR readback still shows Sent without a signed PDF. The legacy email-link callback can show a success page despite an unconfirmed envelope; the follow-up corrects this false success. Do not fund until provider-confirmed completion and the matching executed PDF are stored. Tristan or Bob will test as Administrator. DCR collects Cash/COD and pays the factory. The owner believes DCR receives a factory rebate and authorized us to choose the test model. Use clearing for the home funds and separate rebate income as an explicit test assumption; no rebate percentage or amount is approved. Live gross/net recognition still depends on the factory agreement and accounting approval. Insurance collection/remittance, tax applicability, final legal wording and real factory contacts still need business answers. They can be explicit test cases without being treated as production-approved policy.

The setup screen does not block new builds. Enforcing a gate requires approved mandatory items and waivers. Dealers can request payoff letters; the portal does not fabricate a dated quote. Past-due rows contact DCR because dealer payment submission is not implemented. Those are deliberate scope limits, not tested features.

Source checks pass 904 Python tests, 44 subtests and 18 Node test files. Project preflight and v16 reviews passed for deployed PR #134 and reviewed the subsequent bank/notification change without blockers. Follow-up corrections bound bank names, serialize verified connections per customer, and start a fresh server-time window on every notification enable. Old bank records and explicit loan overrides remain intact; inspect and pause/revoke superseded connections before enabling ACH. PR #135 is installed; Plaid return and automatic financial reversal passed. The manual-bank and existing-email-service follow-up still needs review, deployment and hosted acceptance. Hosted installation, real provider outcomes, human signatures and accounting approval remain separate evidence.

## Notification recovery and test operation

A pilot notice marked Sent through Email Service means the provider returned a message ID. Mailbox receipt is separate evidence. A worker crash can leave Sending; a timeout, missing message ID or uncertain response leaves Outcome Unknown. Both require provider-log and mailbox reconciliation before any operator attempts a fresh send. Do not reset these rows to Queued to retry blindly. Native Email Queue rows remain on their original transport and are never silently migrated or resent.

HBR 33 was restored to In Storage on November 8 at 14:39:33 with notifications disabled. Keep the original failed SMTP test queue for audit. New tests must start a new delivery window and make one reversible synthetic transition. Disabling notifications stops admission and Email Service dispatch, but cannot retract an email already accepted by a provider or a native SMTP queue.

The public legacy completion landing page uses its event query only as a message; it is not evidence of a stored signature. Acceptance always reads Signature Request status and its private signed attachment. Staff-verified manual bank accounts remain Paused without dealer consent; do not resume them until the actual dealer authorization is recorded.
