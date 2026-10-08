# October 8 pilot follow ups

This batch addresses dealer portal and staff workflow issues from the pilot recording. The [full checklist](pilot-checklist-2026-10-08.md) tracks each item by name and status. It is prepared for review; hosted Frappe Cloud verification remains outstanding.

## Implemented in this batch

- Staff and dealer saves allow repeated serial values, including TBD, t.b.d, tbd, and assigned serial numbers. Saved text is preserved; placeholder variants display as TBD in the portal.
- The staff board displays Requests → Pending → Ordered → Delivered. Stored stages and document-driven transitions keep their existing meanings.
- Request submission displays as Submitted, with Loan approved reserved for the financial milestone.
- The dealer portal updates automatically every ten seconds while visible. It preserves unchanged content, focus, and scroll position, waits for uploads or signing actions, and clears cached data when the session expires.
- Completed and pending Flooring Packet signing returns open the same owned home request. Dealer agreements return to Home.
- Loan details show principal, rate, and monthly or next scheduled payment. The fixed-term Total interest and Total payable display is removed. An unavailable next payment displays as unknown.

- Home Build Requests have one staff-editable Offline Date, including changes after submission and existing document history. The dealer detail displays it as read-only information.
- Native staff filters include dealer, factory, quote, and partial serial number. Purchase Orders have read-only Dealer context and a standard Dealer filter.
- A registered, repeatable migration fills missing Purchase Order dealer context from the linked HBR. It preserves populated values, leaves unlinked orders alone, and does not change timestamps or accounting entries. The app-owned field is custom_dcr_dealer to preserve unrelated site fields.
- The monthly insurance field is provisioned on Loan Application if missing. The existing ACH packet mapping is verified with a populated amount; staff values and the hosted PDF still need a check.
- Factory Assignment submission sends nothing automatically. Staff can deliberately send the existing four-document packet; the endpoint requires write and email permission, locks the stored assignment, and rejects drafts, cancellations, and packets already marked sent.

## Verification

The Python suite passed 459 tests and 29 subtests using mocked Frappe. The five dependency-free Node test files passed. A separate Chrome test exercised the production portal shell, CSS, and script with synthetic API responses, including updates, focus/scroll, uploads, signing, visibility, transient failures, malformed responses, expired sessions, offline date display, and Customer Sold summaries.

Run the dependency-free client checks with `node --test dcr/tests/*.cjs`. The browser test additionally requires Playwright and Chrome:

```sh
node dcr/tests/browser/test_dealer_portal_refresh.cjs
```

Set `DCR_PLAYWRIGHT_MODULE` to the Playwright package directory when using an existing installation outside this repository. The browser fixture does not verify deployed Frappe queries, real DocuSign envelopes, email delivery, or accounting behavior.

## Remaining decisions and work

- Curtailment starts with payment 13 and reduces principal by 1% of the original invoice each month, as Tristan clarified. Confirm the source of the original invoice amount when loan fees differ, then test payments 12–14 and early payoff. This batch does not change schedule calculations.
- Confirm the 360-day interest convention, accrual start date, schedule horizon, and final-invoice principal mapping with dated worked examples.
- Use the full checklist for hosted checks, factory/plant assignments, insurance entry, historical date filtering, and the accounting trial.
- The personal `$erpnext-document-cleanup` skill is created and its package validates. Its instructions were edited using [humanizer](https://github.com/blader/humanizer/blob/main/SKILL.md). Applying it to a chosen live document remains separate from creating the skill.
