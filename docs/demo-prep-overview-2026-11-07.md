# DCR demo preparation and remaining work

Updated November 7, 2026. The dealer workflow and core lending rules have substantial implementation and hosted evidence. The remaining work is complete workflow acceptance, several financial exceptions, production setup, and staff rehearsal. Accounting is still **not ready for production sign-off**.

The complete pilot transcript was reread. Subsequent [owner decisions](pilot-checklist-2026-10-08.md#owner-decisions-after-the-blocked-audit) settle Actual/360 from invoice date, principal including financed fees, fixed 1% curtailment from payment 13, continuation beyond month 36 without an automatic balloon, and a revised signed packet when financial terms change. These decisions do not need to be reopened.

## Rechecked November 7

- Cloud is Active with DCR `221d4ce06e44c1a59997b963a3fe7d7259257013`, PR #123. The newer main commits change documentation only. No runtime deployment is pending for them. The other apps retain their recorded pins.
- Company loan accounting is enabled with Actual/360. DocuSign and Plaid are Sandbox. Automatic ACH debits and status notices remain off; no pilot status recipient is configured.
- A fresh native email-link login reached Portal Test in a separate profile while staff remained Administrator. Home, Lending, Payments, Settings and request 37 loaded. The sign-in email and assigned factory display correctly. Portal Test has 13 requests, including four incomplete drafts, rather than an empty demo dashboard.
- Both application packets were visually inspected across all ten pages. Fresh send previews matched the reviewed PDF bytes. Application 14 has $265,000 principal and $1,855 first interest; application 15 has $225,000 principal and $2,250 first interest. Bank masks are from First Platypus Sandbox. Dealer address and signer title are blank; zero insurance prints as a blank amount.
- Both Sandbox packets are now signed through the owner's email in Dia: `SIG-0195` for application 14 and `SIG-0196` for application 15. Application 15's staff, dealer and emailed executed PDFs have identical SHA-256 hashes. Signature arrival and signed status appeared on the untouched dealer page.
- Application 15 opened in embedded DocuSign. **Finish Later returned to the same request 37**, retained the dealer session, showed the incomplete-signature message and preserved the Sign action. A replay of the already-signed `SIG-0194` callback also returned to its owned request 29. Email signing completed successfully. A newly completed embedded same-request return and delayed-callback acceptance remain separate checks.
- The current local fixes pass 798 Python tests and 42 subtests, 16 JavaScript test files and the portal browser fixture. PDF layout checks cover signature spacing and dated payoff amounts. These fixes are awaiting release and hosted acceptance. These source checks remain separate from hosted/provider/accounting acceptance.

## Finish the demo workflow

| Work | Current position | What completes it |
| --- | --- | --- |
| Signing | Both original Sandbox packets are signed. Application 15 signed copies match across staff/dealer/email. Embedded pending return passed. | Complete the revised packet in the embedded flow; verify same-request return, session, callback and new signed copies. |
| Revised invoice | Original signed packet preserved. PO 18 updated normally; invoice 10-1 submitted at $275,000; application 14-1 submitted at $280,000 with fees. Loan 27 is Sanctioned. Funding 14 rejects the old signature with zero GL entries. | Release the amendment-file fix, sign the replacement, then fund and reconcile the new amount/date. Original records remain available. |
| Dealer updates | Delivery/reversal, signature arrival/signed status, funding and monthly repayment balances passed in an independent session. After receipt 14 the untouched page shows $220,500 principal and $4,528.50 next payment. | Complete payoff/closure and remaining application/callback transitions. |
| Jake and staff roles | Administrator covered many scenarios. Purchase User can inspect POs, but Customer lookup and upstream HBR access were denied; the temporary account is disabled. | Choose the intended staff role and have Jake run Cash/COD, Customer Sold, Spec and Inventory, including document timing, waivers, history/date filters and terminal tabs. Do not broaden roles just to make tests pass. |
| Payoff print | Local fix uses the native dated Loan Closure quote, preserves the original financed basis after restructuring, and asks staff for the quote date. Forecast interest and settlement arithmetic are removed. | Release and inspect/send an actual hosted dated PDF, then reconcile against closure. |
| Demo fixtures | The dealer contains incomplete drafts and future-dated accounting trials. Packet address/title are blank. | Select the records to demonstrate, complete their synthetic profile/documents, prepare an incomplete-intake example and rehearse the exact staff/dealer path. Preserve accounting and signed history. |

Application 15 produced Loan 26 and funding 13 at $225,000, with $5,000 financed fees. Twelve independent monthly receipts collected $27,375 interest and zero principal. Payments 13 and 14 each collected $2,250 principal; payment 14 interest was $2,301.75 and remaining principal is $220,500. All 917 relevant ledger rows and 457 complete vouchers reconcile. These are synthetic future value dates with November 7 native GL posting dates, not provider settlement or calendar rollover acceptance. ACH debits remain off.

## Finish financial acceptance

| Work | Already demonstrated | Remaining acceptance |
| --- | --- | --- |
| Separate monthly receipts | Complete: twelve independent interest-only receipts plus payments 13–14 on new Loan 26. Full funding/fee/interest/principal ledger reconciliation passed. | Retain future-date and provider-settlement limitations; calendar rollover remains separate. |
| Extra principal | Owner approved immediate principal reduction with continued regular curtailments. Fresh Pre Payment 39 is Draft for $5,000 principal, reducing the preview balance to $215,500. It exposed $1,029 earned interest omitted from the next schedule row. | Release the carry fix and the guidance to use Pre Payment rather than Advance Payment. Save/recheck receipt 39, post and reconcile it and the next installment, then test reversal. Old Loan 25 advance drafts remain unsubmitted. |
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

## Repeatable checks and resume order

The private proof is `output/pilot-2026-10-08/demo-prep-2026-11-07/monthly-receipts-posted-proof.json` in the original checkout. Run [verify_monthly_receipts.py](../tools/diagnostics/verify_monthly_receipts.py) against it to verify all fourteen receipts and the complete ledger. Wrong-interest and missing-posting probes are rejected. [native_monthly_trial.js](../tools/diagnostics/native_monthly_trial.js) retains the UI-only scoped Save/Submit helpers; it requires current tab state and the November 7 trial context, and never writes through the Frappe API.

1. Release and verify the dated payoff, signature spacing, amended-file and extra-principal carry fixes.
2. Complete receipt 39, the next installment and reversal with actual ledger/schedule checks.
3. Complete application 14-1's replacement signature and funding sequence.
4. Finish payoff/closure dealer transitions and Jake's intended-role rehearsal.
5. Finish remaining policy, historical accounting, provider and cutover acceptance. Dashboard design can proceed alongside this work.
