# October 8 pilot follow ups

This batch addresses dealer portal and staff workflow issues from the pilot recording. The [full checklist](pilot-checklist-2026-10-08.md) tracks each item by name and status. Source changes are merged and deployed through PR #42, installed as `31bb1c0`; site migration succeeded. Off Line Date, insurance placement, Factory Address heading, empty derived-detail hiding and the Homes grid heading are verified live. Hosted evidence and unresolved items are tracked individually in the checklist.

## Implemented in this batch

- Staff and dealer saves allow repeated serial values, including TBD, t.b.d, tbd, and assigned serial numbers. Saved text is preserved; placeholder variants display as TBD in the portal.
- The staff board displays Requests → Pending → Ordered → Delivered. Stored stages and document-driven transitions keep their existing meanings.
- Request submission displays as Submitted, with Loan approved reserved for the financial milestone.
- The dealer portal updates automatically every ten seconds while visible. It preserves unchanged content, focus, and scroll position, waits for uploads or signing actions, and clears cached data when the session expires.
- Completed and pending Flooring Packet signing returns open the same owned home request. Dealer agreements return to Home.
- Loan details show principal, rate, and monthly or next scheduled payment. The fixed-term Total interest and Total payable display is removed. An unavailable next payment displays as unknown.

- Home Build Requests have one staff-editable Off Line Date, including changes after submission and existing document history. The dealer detail displays it as read-only information.
- Native staff filters include dealer, factory, quote, and partial serial number. Purchase Orders have read-only Dealer context and a standard Dealer filter.
- A registered, repeatable migration fills missing Purchase Order dealer context from the linked HBR. It preserves populated values, leaves unlinked orders alone, and does not change timestamps or accounting entries. The app-owned field is custom_dcr_dealer to preserve unrelated site fields.
- The monthly insurance field is provisioned on Loan Application if missing. The existing ACH packet mapping is verified with a populated amount; staff values and the hosted PDF still need a check.
- Factory Assignment submission sends nothing automatically. Staff can deliberately send the existing four-document packet; the endpoint requires write and email permission, locks the stored assignment, and rejects drafts, cancellations, and packets already marked sent.
- Purchase Order setup moves Home Build Request, Dealer, and Payment Type into the first section. Dealer fetches from the linked request in the form and remains derived by server validation. A first Purchase Order form pass labels factory context and the order date clearly on linked home orders. Empty barcode inputs and raw-material controls disappear on ordinary home orders. Subcontracting, populated materials, required fields, and extra site fields remain inspectable; removing the home reference restores native labels and visibility. It changes presentation without writing document values. Tabs use task names, numeric totals retain their stored print wording without repeating it in the form, and matching company-currency totals are hidden only on immutable submitted/cancelled home orders. Drafts and differing currencies retain both amounts. First-section placement, dealer/factory/payment defaults, duplicate tax suppression and subcontracting visibility were verified live. Expanded-row cleanup is deployed and verified on a submitted order; the cancelled-order payment hydration guard is regression-covered. Further spacing/tab polish and hosted cancelled/restricted-role checks remain open.

## Verification

The latest Python suite passed 465 tests and 33 subtests using mocked Frappe. The eight dependency-free Node test files passed, including Purchase Order scope, draft/submitted/cancelled states, required and custom fields, materials, restoration, and opening without data writes. A separate Chrome test exercised the production portal shell, CSS, and script with synthetic API responses, including updates, focus/scroll, uploads, signing, visibility, transient failures, malformed responses, expired sessions, offline date display, and Customer Sold summaries.

Run the dependency-free client checks with `node --test dcr/tests/*.cjs`. The browser test additionally requires Playwright and Chrome:

```sh
node dcr/tests/browser/test_dealer_portal_refresh.cjs
```

Set `DCR_PLAYWRIGHT_MODULE` to the Playwright package directory when using an existing installation outside this repository. The browser fixture does not verify deployed Frappe queries, real DocuSign envelopes, email delivery, or accounting behavior.

### Initial anonymous browser evidence, October 8

- The production `/desk` route opens DCR Sign In with `/desk` retained as the return destination.
- The production `/portal` route opens DCR Sign In with `/portal` retained as the return destination.
- These initial captures were made while signed out. They verify anonymous entry routing; they do not verify authenticated forms, permissions, signing, or loan transitions.
- Review against the [Frappe v16 grid source](https://github.com/frappe/frappe/blob/version-16/frappe/public/js/frappe/form/grid.js) caught a child-table event registration error in the first PO pass. Add/remove handlers now register on Purchase Order Item Supplied, and the regression test invokes that child registration plus parent table replacement. Material controls return when materials appear and hide again when the last row is removed.

## Remaining decisions and work

- Curtailment starts with payment 13 and reduces principal by 1% of the original invoice each month, as Tristan clarified. Confirm the source of the original invoice amount when loan fees differ, then test payments 12–14 and early payoff. This batch does not change schedule calculations.
- Confirm the 360-day interest convention, accrual start date, schedule horizon, and final-invoice principal mapping with dated worked examples.
- Use the full checklist for hosted checks, factory/plant assignments, insurance entry, historical date filtering, and the accounting trial.
- The personal `$erpnext-docs` skill is created and its package validates. Its instructions were edited using [humanizer](https://github.com/blader/humanizer/blob/main/SKILL.md). Purchase Order application is in progress. On October 8 the live `/desk` route reached the DCR sign-in page; sign-in was subsequently restored on backdesk.dealercapital.net, and the submitted PO baseline was inspected. Cloud Apps confirms installed DCR `dafb01c`. The initial PO pass and its two repairs are deployed and inspected; further variants remain open. The source inventory used the [official ERPNext v16 Purchase Order metadata](https://github.com/frappe/erpnext/blob/version-16/erpnext/buying/doctype/purchase_order/purchase_order.json); Customize Form may differ on the site.

### Current authenticated evidence

Administrator Desk checks cover linked PO creation, submitted PO presentation, historical dealer/date/manufacturer filters and board dealer/factory/quote/serial-fragment searches. The current Administrator portal session reports No dealer access yet, so dealer-owned behavior remains unverified. The accounting audit confirms accrual and demand scheduler executions, an enabled 2026 fiscal year, and a posted accrued-interest mapping defect. The deployed source guard prevents the legacy income-account fallback; live account repair and reconciliation are still required.
