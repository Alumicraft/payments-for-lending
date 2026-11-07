# DCR demo preparation and remaining work

Updated November 7, 2026. The dealer workflow and core lending rules have substantial implementation and hosted evidence. The remaining work is complete workflow acceptance, several financial exceptions, production setup, and staff rehearsal. Accounting is still **not ready for production sign-off**.

The complete pilot transcript was reread. Subsequent [owner decisions](pilot-checklist-2026-10-08.md#owner-decisions-after-the-blocked-audit) settle Actual/360 from invoice date, principal including financed fees, fixed 1% curtailment from payment 13, continuation beyond month 36 without an automatic balloon, and a revised signed packet when financial terms change. These decisions do not need to be reopened.

## Rechecked November 7

- Cloud is Active with DCR `221d4ce06e44c1a59997b963a3fe7d7259257013`, PR #123. The newer main commits change documentation only. No runtime deployment is pending for them. The other apps retain their recorded pins.
- Company loan accounting is enabled with Actual/360. DocuSign and Plaid are Sandbox. Automatic ACH debits and status notices remain off; no pilot status recipient is configured.
- A fresh native email-link login reached Portal Test in a separate profile while staff remained Administrator. Home, Lending, Payments, Settings and request 37 loaded. The sign-in email and assigned factory display correctly. Portal Test has 13 requests, including four incomplete drafts, rather than an empty demo dashboard.
- Both application packets were visually inspected across all ten pages. Fresh send previews matched the reviewed PDF bytes. Application 14 has $265,000 principal and $1,855 first interest; application 15 has $225,000 principal and $2,250 first interest. Bank masks are from First Platypus Sandbox. Dealer address and signer title are blank; zero insurance prints as a blank amount.
- The owner authorized test sends to his inbox. Both invitations arrived: `SIG-0195` for application 14 and `SIG-0196` for application 15. The open dealer request gained its new signature action without a refresh.
- Application 15 opened in embedded DocuSign. **Finish Later returned to the same request 37**, retained the dealer session, showed the incomplete-signature message and preserved the Sign action. A replay of the already-signed `SIG-0194` callback also returned to its owned request 29. New completion and delayed-callback acceptance remain open; the owner has been asked to sign application 15 in the shared browser.
- All 786 Python tests and 40 subtests pass, as do 15 JavaScript test files and the portal browser fixture. These source checks remain separate from hosted/provider/accounting acceptance.

## Finish the demo workflow

| Work | Current position | What completes it |
| --- | --- | --- |
| Signing | Both reviewed Sandbox invitations are delivered. The real embedded pending return passed. | Owner completes signing; verify the completed same-request return, session, delayed callback, signed attachment and identical staff/dealer/email copies. |
| Revised invoice | Application 14 has a $260,000 invoice plus $5,000 outside-invoice fees. | Sign the original packet, revise invoice/application through normal documents, reject the old signature for changed terms, sign the replacement, then verify the new Loan/funding amount and date. Preserve both versions. |
| Dealer updates | Receipt/reversal polling passed October 20; signature-arrival polling passed November 7. | Observe application, completion, funding, repayment, payoff and closure changes in an independent dealer page without refresh. Receipt polling does not prove every transition. |
| Jake and staff roles | Administrator covered many scenarios. Purchase User can inspect POs, but Customer lookup and upstream HBR access were denied; the temporary account is disabled. | Choose the intended staff role and have Jake run Cash/COD, Customer Sold, Spec and Inventory, including document timing, waivers, history/date filters and terminal tabs. Do not broaden roles just to make tests pass. |
| Payoff print | It still derives interest from forecast totals and uses principal collected in its total. | Decide whether it is a dated payoff quote or a settlement summary, correct its amounts accordingly, and reconcile it with native payoff/closure. Keep it out of the validated payoff demonstration until then. |
| Demo fixtures | The dealer contains incomplete drafts and future-dated accounting trials. Packet address/title are blank. | Select the records to demonstrate, complete their synthetic profile/documents, prepare an incomplete-intake example and rehearse the exact staff/dealer path. Preserve accounting and signed history. |

Application 15 is next: $220,000 invoice plus $5,000 fees, November 1, 2026 funding, December 1 first payment, 12% Actual/360. Application 14 covers the separate revised-invoice case. Both are synthetic Sandbox trials; no new Loan, funding or repayment has been created in this review.

## Finish financial acceptance

| Work | Already demonstrated | Remaining acceptance |
| --- | --- | --- |
| Separate monthly receipts | Payment 12, curtailments 13–14, early payoff/reversal, and month-37 arrears collection have hosted reconciliation. | After application 15 is signed/funded, run twelve separately dated accrual/demand/receipt cycles against the prepared answer key, then check the transition to curtailment. One arrears receipt is not twelve on-time receipts. |
| Extra principal | Actual-principal quoting is fixed and deployed. A prior advance schedule row showed $6,443.92 against a $5,000 extra-principal receipt. | Decide immediate principal reduction with continued curtailments versus prepaid installments. Repair and reconcile the schedule behavior before submitting retained receipt 24/restructure 5 drafts. |
| Penalties and capitalization | Zero-balance guards, fee collection/waiver, taxes and linked fee-invoice cancellation have bounded evidence. | Exercise positive penalty, capitalization and remaining applicable reversal variants with agreed allocations and GL entries. |
| Financial policies | Insurance reaches the packet and staff upload satisfies the checklist. | Set insurance collection/remittance ownership and accounts; Cash/COD payable ownership; tax applicability/rates; remaining rebate, fee and installed-value/LTV rules. Posting tests do not settle policy. |
| Historical balances | Legacy self-offset accruals, effective periods and demands have been inventoried. | Reconcile original contracts, principal events and GL by loan, resolve Loan 14 and other exceptions, and approve a correction plan without deleting valid earned interest/history. |
| Accounting sign-off | Many synthetic native postings and reversals reconcile. | Bookkeeper/accounting owner accepts mappings, real bank/clearing reconciliation, exceptions, opening balances and operating procedures. |

The [accounting audit](accounting-readiness-audit.md) retains the detailed evidence. The [lending acceptance cases](lending-acceptance-cases.md) define expected calculations. Current packet PDFs/hashes, hosted readbacks and the application-15 receipt answer key are retained under the original checkout's `output/` directory, outside this source change.

## Complete production setup

- Confirm real plant names, dealer assignments, factory contacts and minimum packet documents. Existing data is approved for testing. Assignment submission must stay quiet until a deliberate staff send.
- Finish Plaid callback/session and the manual-bank path used by staff. Complete authorized ACHQ receipt, settlement, return, uncertain-outcome and bank-reconciliation acceptance before enabling debits.
- Configure a controlled pilot recipient before enabling status notices; verify actual delivery and duplicate prevention. Finish sender/domain, signing/webhook and provider acceptance rather than relying on enabled settings.
- Approve final dealer agreement, MIFA, flooring, PO, pre-approval and payoff wording. The test ACH authorization includes autopay and NSF terms; final policy approval remains separate.
- Decide phone support and verify real upload/download behavior if included. It remains deferred scope.
- Agree the parallel-run/cutover procedure, opening balances/history, recovery plan, a single collection owner, and manual UCC/insurance/inspection responsibilities. A clearing journal does not erase trial history.

## Dashboard redesign requirements

Tristan is redesigning part of the dashboard. Preserve these behaviors while changing its presentation:

- Staff board labels are **Requests, Pending, Ordered, Delivered**. Source documents drive transitions; storage remains a staff tag and closed history stays searchable.
- Dealer home status, loan stage and required dealer action are distinct. Do not replace all three with the staff board labels or make request review imply financing approval.
- Default staff views to all deals. Retain dealer, factory/plant, quote and serial-fragment search, including the last five digits. Historical lookup includes status and date range.
- Use actual unpaid principal for balances. Distinguish current balances, scheduled payments, history and forecast assumptions. Do not restore fixed-term Total interest/Total payable claims or treat forecast interest as a payoff quote.
- Preserve same-request navigation, private-document ownership, incomplete drafts, accepted-record locks, automatic updates, keyboard/focus behavior, retry/session-expiry handling and full payment expansion.
- Keep attention/stage totals defined. A waiver is not an uploaded file; a connected bank is not enabled automatic collection.

## Resume order

1. Complete application 15 signing, completed return and signed-file readback.
2. Fund it normally and execute the independent monthly receipt sequence with GL/Lending comparisons.
3. Complete application 14's original/revised packet and funding sequence.
4. Finish independent dealer transitions and Jake's intended-role rehearsal.
5. Resolve the payoff print and extra-payment behavior, then remaining policy, historical accounting, provider and cutover acceptance. Dashboard design can proceed alongside this work.
