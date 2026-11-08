# Dealer portal redesign

Source: Paper file DCR, Dealer portal page, boards at y13700 and y14900. The November 7 design brief controls intentional differences in the exports, including Inter throughout and font weights no higher than 500.

## Included

- Home setup To do/Done, ready and no-loans states; Builds and its four views; build Overview, Details, Documents and Payments; Loans Active/Repaid; Payments Overview, Schedule and Bank.
- A 228px sidebar, shared table lanes, underline tabs, system dark theme and phone bottom navigation. Settings retains uploads and signature history. Phone users can sign out through Settings.
- Request IDs identify builds. Wide tables omit only the organizational ACC prefix from link text so distinct HBR numbers fit. Link targets, titles, page headings and breadcrumbs retain the saved ID.
- Historical charts use submitted funding and repayment posting dates. Projected principal uses unpaid schedule reductions and a dashed line. A history that does not reconcile with the native balance displays as unavailable.
- Account totals read all owned submitted loans and receipts. Noncash waivers, capitalizations and Principal Adjustment records do not inflate paid-to-date or appear as paid installments. Paid-to-date includes submitted collection receipts, including write-off recovery and cash settlement records; it does not claim provider settlement. A missing or blank MIFA limit remains unavailable. Actual outstanding uses native balances. Used credit and Available share the staff approval calculation, including reserved amounts for partially disbursed loans. These figures can differ from actual funded principal.
- Paid schedule copies are matched by funding and due date as well as row ID. This prevents prepayment from presenting a paid installment again without suppressing a different funding's installment on the same date.
- An amended application's signed flag requires its own matching dealer Signature Request. An inherited file pointer cannot claim it is signed.

## Deliberate limits

The setup screen does not block new builds. Tristan must approve the required steps and waivers before that rule exists. File dates mean uploaded, and signature dates mean signed; neither implies an invented approval date.

The payoff sidebar offers the existing durable request action. It does not invent a total or a Good through date. Past-due rows offer Contact DCR because there is no dealer payment-submission flow. Bank connection uses the existing owned Plaid setup action. Automatic debits remain unchanged. An enabled global setting alone does not claim an individual dealer has automatic payments enabled.

Curtailments still begin at payment 13 and use the configured percentage of original financed principal. This release does not change that basis to factory invoice excluding financed fees. Dealers see combined scheduled amounts, without principal/interest splits or curtailment notes.

Upcoming payments on Home means the next scheduled installment per loan. This avoids presenting the sum of years of forecast payments as currently due. Each side table has at most three rows; when necessary its third row links to the full schedule. The overflow wording says next due when the hidden rows span dates.

## Validation

The payment regression failed before the fix with $5,100.17 instead of $600 due, because a copied paid installment was included. It now passes while retaining the independent funding's payment.

Run the Python suite and Node test files. The two browser fixtures use the real portal shell, script, CSS and bundled font with synthetic API responses. The refresh fixture checks polling, focus/scroll retention, signing/upload serialization, transient failures and expired sessions. The redesign fixture checks all screen families, amounts, the side-table cap, edit locks, dark mode, phone layouts and horizontal overflow.

Browser fixture invocation uses `DCR_PLAYWRIGHT_MODULE` for an existing Playwright installation. `DCR_PORTAL_SCREENSHOT_DIR` saves the redesign screenshots. These are local browser proofs, not hosted data, provider delivery or settlement acceptance.

InterVariable.woff2 and its license come from rsms/inter commit e3a3d4c57d5ecc01453a575621882a384c1995a3. No external font service is contacted by the portal.

Run the project preflight and v16-linter agents on this diff before a main push. Deployment and signed-in hosted acceptance must be recorded separately from these local checks.

## Release checks

The preflight and v16-linter agents reviewed candidate 81aa05b. Their findings led to a shared staff/portal credit-usage helper, exclusion of Principal Adjustment from cash receipts, blank-limit handling, a guarded ACH status read, reuse of already-verified loan balances, and font coverage in MANIFEST.in. Both portal and native request-form cache tokens advance together. The API client sends reads as POST, so the review's inferred GET-log rollback issue does not apply to this path.

Final validation passes 828 Python tests and 42 subtests, all 17 Node test files, and both browser fixtures. The fixtures produce desktop, dark and phone screenshots under the local output directory. Polling still returns full owned histories every ten seconds. This release reduces duplicate loan reads but does not claim a measured hosted performance result.
