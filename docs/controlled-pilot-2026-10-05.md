# DCR controlled-pilot source and operating notes — October 5

Delivery target: October 6 morning, usable handoff and controlled pilot. This document describes the source changes and the hosted checks still required. Passing mocked tests does not establish provider, database, accounting, or browser acceptance.

## Source changes

- Staff APIs now require a System User and the relevant document/action permission. Chart aggregates use permission-filtered document IDs. Available-credit calculations refuse to present a partial set of dealer loans as the full balance. Map protections came in PR #10.
- ACH admission is committed as **Outcome Unknown** before calling ACHQ. An ambiguous acknowledgement cannot become an automatic second debit. The primary remote ID is `TransAct_ReferenceID`; cancellation uses `ECheck.Void` and `Transact_ReferenceID`.
- New automatic debits default to **Controlled Pilot**, limited to `ACH Settings.pilot_loan`. No selected pilot loan means no new automatic debits. The separately selectable **All Eligible Loans** scope requires production acceptance.
- Scheduler admission locks the Loan before checking existing attempts. Any prior attempt for the same due date blocks a new scheduled debit; only an eligible returned payment can use the retry path. Only R01/R09 are eligible, capped at two reattempts.
- Repayment selection reads the installed v16 **Loan Repayment Schedule**, its **Repayment Schedule** rows, and submitted **Loan Demand** outstanding balances. A generated row with missing demands stops processing for reconciliation. Dealer-current checks also use unpaid submitted demands.
- Cleared ACH posts one submitted **Loan Repayment** through Lending, using the configured ACH Clearing Account. It does not also create a Payment Entry. Failure becomes **Accounting Pending**; the hourly job retries accounting, without submitting another debit. Existing legacy Payment Entries block new posting until reconciled.
- A return after accounting becomes **Reversal Pending**. Reversal is deliberately manual; the source does not automatically undo GL entries or retry that payment. Revoking a bank account commits the revocation before remote cancellation and reports unresolved debits.
- Dealer Agreement, MIFA, and Flooring Packet sending require review of the recipient and the exact PDFs. The five-minute review is bound to the staff user, source revisions, recipient, and print formats. Send uses those cached bytes, not a freshly rendered replacement. Durable **Outcome Unknown** signature admission blocks duplicate envelopes after a timeout.
- DocuSign callbacks accept JSON SIM's nested `data.envelopeId` and event/status fields. Duplicate completed callbacks with an attached signed PDF do not repeat downstream processing. PDF download failure returns a retryable webhook error rather than marking the source signed. Signing links use the reviewed recipient snapshot.
- Portal intake captures end-buyer name/email/phone and installed value without exposing an arbitrary Customer link. Installed value is recorded separately; existing selling-price/LTV formulas are unchanged pending a business decision. Updated print formats fall back to the raw buyer details.
- Staff can mark **In Storage**. Portal cards, the map, and labeled Kanban card properties expose it. Map details include serial, quote, buyer, and loan stage. Stable HBR record IDs are unchanged.
- Factory PO email includes the generated PO PDF and original uploaded Factory Quotes attached to the linked, readable HBR. Preview lists the attachments; the helper checks file ownership and read permission before sending.
- **DCR Status Notice** stores review, order, loan, and storage transitions. Portal submission explicitly records its staff alert; native staff submission changes portal state to Accepted. **DCR Pilot Settings** defaults delivery off and requires a pilot recipient before enabling it. Every delivered status notice goes to that override, with its intended recipient retained for review.
- Status notices and ACH event notices use the native Frappe Email Queue directly, bypassing the shared Emails app's immediate Vercel override. Upcoming/success/failure ACH notice flags are independent. A queued record is not called Sent until the native queue reports Sent.
- DCR now declares the already-installed `emails` app as a required dependency. No app/DocType ownership migration or repository rename is included. Source Admin for the eight-repo transfer was verified through the already-connected Alumicraft account; destination Frappe Cloud installation and source-account destination creation rights remain to be set up/verified.

## Verification

Full local suite after the provider-contract follow-up: **362 passed, zero skipped**, using mocked Frappe, also verified on Python 3.12. Nine existing `datetime.utcnow` deprecation warnings remain. Python/JSON/JavaScript/Jinja syntax and whitespace checks accompany the batch. The installed Lending and Frappe source revisions were inspected to establish schedule, repayment, queue, dialog, and Kanban contracts.

The ignored `.claude/agents/preflight.md` and `v16-linter.md` files are available in the primary checkout and were read for the final review. Their checks were performed directly against the isolated checkout; no separate agent run is claimed.

Public sandbox verification found additional required payload fields and the CSV report format. The native client then created, queried and cancelled a fabricated $1 payment; all three accepted tests were cancelled. See [provider-contract receipts](achq-contract-verification-2026-10-05.md). This does not establish hosted settlement/GL or callback acceptance.

## Deploy and first readback

1. Take a current database and file backup through Frappe Cloud. Record the current deployment and installed-app SHAs.
2. On private bench group **DCR / bench-37701**, deploy the tested `dcr` main revision. Keep the recorded framework/Lending/Emails versions unless a separate upgrade has been reviewed. Do not select an unrelated framework update just to deploy DCR.
3. Watch the dashboard build and automatic migration. The existing `after_migrate` setup hook repairs configuration, workspaces, and some existing record state; review its errors even if the build succeeds.
4. Read back the installed DCR SHA. PR #15 deployed as `b47a3b6` and its explicit migration succeeded October 5 at 2:03 PM Pacific. PR #16 deployed as `fb41a7b5b0b08c7f6fc3f625169ce12a6dc9d662` at 2:23 PM; migration succeeded at 2:24 PM. Browser rendering, draft save/reload and responsive pages passed; detailed receipts stay local. A group build alone did not run all migration hooks in this rollout; the explicit dashboard migration log and permission-row readback established that they ran.
5. Confirm new `DCR Pilot Settings` and `DCR Status Notice` DocTypes, ACH/signature status options, pilot scope/loan fields, and HBR buyer/storage/value fields. Confirm storage can be changed on a submitted HBR.
6. Check Deals, Accounting, Contacts, Access, and Overview. Overview should group the seven charts by section. Check the map and Kanban without changing operational stages manually.
7. Check `ACH Settings`: scope **Controlled Pilot**, selected synthetic pilot loan, correct environment, real-debit activation disabled until setup and acceptance below. Check `DCR Pilot Settings`: notifications disabled until its controlled mailbox is configured.

## Controlled setup

- **ACHQ/Plaid:** approved Merchant ID, Gate ID, Gate Key; matched environments and authorized synthetic accounts; Plaid Client ID/Secret and enabled ACHQ processor integration. Confirm the actual persisted-sandbox mode: production credentials with `TestMode=On` are development response testing, not settlement/status-query evidence. For public persisted tests use the explicit Public Sandbox mode with 2001/test/test, Controlled Pilot and fabricated data. Complete and review the Customer billing address/contact; WEB requires its captured authorization IP. Verify the provider's real callback signature/header/body contract against the site's HMAC verifier; that contract has not been proven live.
- **Accounting:** Loan Product and Company GL mappings; required ACH Clearing Account, Mode of Payment, and clearing-to-bank reconciliation. Confirm the native submitted repayment allocates principal/interest/demands as approved.
- **DocuSign:** sandbox account, Account ID, Integration Key, User ID, RSA key, JWT consent, Connect HMAC. Callback `/api/method/dcr.api.docusign.docusign_webhook`. Use approved test recipients and inspect signature/date anchors in the exact rendered PDFs.
- **Branded email:** shared Emails app and Email Service Settings, sender/domain, service URL, service secret, Resend key, and DCR branding. PO and signature messages use this pipeline.
- **Transactional notices:** configure a default outgoing native **Email Account** as well. Status/ACH notices deliberately use Email Queue, not the immediate branded override. Set `DCR Pilot Settings.pilot_notification_recipient` and the intended staff mailbox before enabling status delivery. Synthetic dealer contacts must also point to controlled mailboxes for other pilot emails.
- **Users/master data:** authorized staff roles; two Website Users each linked to one enabled Dealer Customer; submitted active Factory Assignments; onboarding documents, MIFA/credit limit, Loan Product, factory contacts, and Map Settings token. Keep synthetic records clearly labeled.
- **Scheduler/workers:** verify daily upcoming/initiating/retry jobs, hourly ACH polling/accounting reconciliation, and notice queue/delivery-status jobs in the hosted scheduler logs. Upcoming scheduling currently selects a payment exactly the configured advance-notice interval away; it does not automatically sweep missed notice dates or overdue history. Existing ACH attempts must be reconciled explicitly.

## Hosted checks completed

Two synthetic Dealer Website Users exercised intake, draft edit, review and resubmission, ownership checks, private documents and restricted APIs. Native staff accepted the complete Cash checklist and changed submitted storage state. Agreement and PO previews were rendered without sending; stale signature review was refused. All seven workspace charts render, custom chart metrics and Daily Active Users were independently reconciled. Legacy Dealer native permissions and portal session CSRF failures were found and fixed in PRs #15/#16. Outbound delivery, full Floored funding, hosted settlement/GL and positive signed callbacks remain open. All temporary test users are disabled, API keys revoked and the temporary Administrator portal mapping removed. Labeled synthetic samples remain as evidence; detailed cleanup is recorded locally.

## Required hosted evidence

Record IDs, expected/observed amounts, and screenshots or API readbacks for each scenario. No real dealer/factory email, signature invitation, or debit has been performed by this source work.

| Flow | Required result |
|---|---|
| Dealer A/B and restricted staff | Own-deal access works; direct map/chart/bank/email/signature APIs and private files deny unauthorized records/actions. |
| Portal review | Quote/buyer/value save and reload; assigned factory; upload/download; review submission; changes requested and resubmission; native staff acceptance updates Accepted. Notices record once. |
| Cash deal | Complete checklist, PO, controlled factory email, generated PDF plus original quote, receipt and accounting. No flooring loan. |
| Floored deal | Application, approved credit, reviewed packet, sandbox signing, loan/disbursement, PO/receipt, repayment demands, GL, stages and available credit. |
| Signing | Preview creates no envelope/email; changed/expired review is refused; exact reviewed bytes sent once; nested Connect event attaches PDF; repeated event does not duplicate processing; edited Customer contact does not change envelope identity. |
| Pilot scope | Missing pilot loan or another loan blocks new admission, even with autopay enabled. Existing remote payments still poll/reconcile while new autopay is disabled. |
| ACH cleared/replayed | Exactly one native submitted Loan Repayment; correct allocation/balances/clearing account; repeated callbacks/polls do not double-post. Upcoming and success notices are independently queued. |
| ACH failures | Persisted unknown submission is reconciled before any new attempt; accounting failure shows Accounting Pending and recovers without a debit; R01/R09 cap; other return codes do not retry; remote cancellation refusal remains unresolved after revocation. |
| Post-clear return | Reversal Pending is visible; operator reviews/cancels/reverses posted accounting under approved procedure before any reattempt. No automatic reversal is claimed. |
| UI/reporting | All seven charts, row-restricted totals, serial/quote search, storage readback, map loan stage, light/dark views and phone portal. Compare chart totals to source reports. |

Unknown ACH receipts require provider reconciliation by merchant/remote reference. Unknown DocuSign creation uses the Signature Request name as `transactionId`; reconcile the provider envelope before resending. DocuSign's transaction-ID lookup window is seven days. Reference or email failures must be checked in logs and retried deliberately; a provider's completed response alone does not prove every downstream attachment/email succeeded.

## Decisions still needed from DCR

360/365 day count, regular/default/late fees and dated payoff examples; selling price versus installed value as the LTV denominator; the third Model/Inventory home type's label and required documents; final agreement/packet/PO wording. None were guessed in this batch. Final business acceptance and expanded real-debit activation remain separate from tomorrow's pilot.

## Provider/source references

- [ACHQ transaction IDs](https://developers.achq.com/docs/transaction-identification), [void/cancel](https://developers.achq.com/docs/cancel-a-payment), [status events](https://developers.achq.com/docs/event-monitoring), [sandbox modes](https://developers.achq.com/docs/sandbox-and-testing).
- [DocuSign JSON SIM model](https://developers.docusign.com/platform/webhooks/connect/json-sim-event-model/), [official payload example](https://www.docusign.com/blog/developers/connect-20), [transaction-ID recovery](https://www.docusign.com/blog/developers/common-api-tasks-use-transactionid-to-find-the-envelope-you-created).
- [Current installed Lending source](https://github.com/frappe/lending/tree/97f692e908e92b3ce6737ab08c3ff9cb3cdcca44), [current installed Frappe source](https://github.com/frappe/frappe/tree/97a5dd93ca5883bcc9c4ef9834120c5cba397b67).
