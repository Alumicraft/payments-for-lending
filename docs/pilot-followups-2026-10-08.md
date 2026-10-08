# October 8 pilot follow ups

The first batch removes duplicate serial-number checks and addresses the dealer portal issues identified in the pilot recording. It is prepared for review; hosted Frappe Cloud verification remains outstanding.

## Implemented in this batch

- Staff and dealer saves allow repeated serial values, including TBD, t.b.d, tbd, and assigned serial numbers. Saved text is preserved; placeholder variants display as TBD in the portal.
- The staff board displays Requests → Pending → Ordered → Delivered. Stored stages and document-driven transitions keep their existing meanings.
- Request submission displays as Submitted, with Loan approved reserved for the financial milestone.
- The dealer portal updates automatically every ten seconds while visible. It preserves unchanged content, focus, and scroll position, waits for uploads or signing actions, and clears cached data when the session expires.
- Completed and pending Flooring Packet signing returns open the same owned home request. Dealer agreements return to Home.
- Loan details show principal, rate, and monthly or next scheduled payment. The fixed-term Total interest and Total payable display is removed. An unavailable next payment displays as unknown.

## Verification

The Python suite passed 445 tests and 29 subtests using mocked Frappe. The four dependency-free Node test files passed. A separate Chrome test exercised the production portal shell, CSS, and script with synthetic API responses, including updates, focus/scroll, uploads, signing, visibility, transient failures, malformed responses, and expired sessions.

Run the dependency-free client checks with `node --test dcr/tests/*.cjs`. The browser test additionally requires Playwright and Chrome:

```sh
node dcr/tests/browser/test_dealer_portal_refresh.cjs
```

Set `DCR_PLAYWRIGHT_MODULE` to the Playwright package directory when using an existing installation outside this repository. The browser fixture does not verify deployed Frappe queries, real DocuSign envelopes, email delivery, or accounting behavior.

## Remaining decisions and work

- Curtailment starts with payment 13 and reduces principal by 1% of the original invoice each month, as Tristan clarified. Confirm the source of the original invoice amount when loan fees differ, then test payments 12–14 and early payoff. This batch does not change schedule calculations.
- Confirm the 360-day interest convention, accrual start date, schedule horizon, and final-invoice principal mapping with dated worked examples.
- Continue the pilot checklist for insurance packet mapping, factory/plant assignments, staff filters, the editable offline date, historical deal views, and the accounting trial.
- After the pilot fixes, create a reusable skill to clean up ERPNext documents: field order, grouping, hierarchy, and visual clutter, while preserving validation, permissions, and workflow controls.
