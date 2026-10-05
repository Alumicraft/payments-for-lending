# DCR delivery checklist — October 6 morning

Scope agreed with Tristan: usable handoff and controlled pilot. DCR workspace home pages first; move the full custom/shared GitHub stack to American-Signal-Works when destination creation rights and hosting connections are ready. Source review is based on the Meeting Changes chat and recorded transcript, refreshed against today's source and the installed-app snapshot.

## Completed in source

| Work | Evidence |
|---|---|
| Factory quote intake/readback; PO dealer context; map and document-email permissions | [Merged PR #10](https://github.com/Alumicraft/payments-for-lending/pull/10), main merge `f1a2e23`. |
| DCR home pages and Overview charts | [Merged PR #11](https://github.com/Alumicraft/payments-for-lending/pull/11), main merge `a9a636f`. Deals: New Deals by Type, Deal Pipeline by Factory; Accounting: Inflows vs Outflows, Past-Due Aging, Repayment Breakdown; Contacts: New Dealers by Month; Access: Active Users Per Day. Overview groups all seven, preserving other widgets and valid site-configured charts. |
| Controlled-pilot completion batch | [Merged PR #12](https://github.com/Alumicraft/payments-for-lending/pull/12), main merge `40cf1f7d4803bc4b3a41dd497ee7a2e959817d3b` (tested head `a33a64a10f9e19825391ea488ce15895ff58f02a`, identical Git tree): staff/action/row authorization, native v16 repayment source and allocation, durable unknown payment/signature admission, restricted ACH scope/retries/cancellation, exact PDF review, buyer/value intake, storage/map detail, uploaded factory-quote attachments, and durable pilot status notices. See [source and operating notes](controlled-pilot-2026-10-05.md). |
| ACHQ request/report contract | Public sandbox found and verified fixes for required token billing fields and CSV status reports. Native client created, queried and cancelled a fabricated $1 payment. All three accepted test payments were cancelled. See [provider receipts and limits](achq-contract-verification-2026-10-05.md). |
| Architecture and ASW inventory | [App structure review](app-structure-review-2026-10-05.md): eight repos, permissions/visibility, overlap, migration order, and handoff checks. Shared maintained base plus thin client apps is recommended over full independent forks. |

Local verification: **362 passed, zero skipped** with mocked Frappe. Python/JSON/JavaScript and changed print-format Jinja syntax checks pass. These are source checks; no hosted provider/accounting/browser acceptance is inferred.

## Hosted delivery evidence — October 5

Own isolated Codex browser and temporary synthetic API identities were used with permission. The user's browser was not controlled. Database/file backup succeeded at 1:28 PM Pacific. DCR-only deployment of PR #15 succeeded at 1:56 PM; explicit dashboard migration succeeded at 2:03 PM with after_migrate hooks in the job log. Live Frappe is 16.36.1 (`97a5dd9`), ERPNext 16.37.0 (`af63cde`), Lending 16.6.0 (`97f692e`), and Emails `f50f47e`.

Hosted checks cover two-dealer ownership, unmapped/disabled/ambiguous mapping rejection, restricted staff denial, private-file access, Cash/Floored intake, review/changes/resubmission, checklist rejection and native Cash acceptance, submitted storage editing, unique unsent notices, exact agreement PDF preview and stale-review rejection, PO PDF/quote attachment preview, five custom chart totals and Daily Active Users reconciliation. All seven charts are visible on their own pages and grouped on Overview. Native outgoing email and registered scheduler jobs exist; actual provider/email delivery is not proved by those configuration checks.

Hosted testing exposed broad legacy Dealer permissions on Customer, Supplier and Home Build Request. PR #15 removes their native access while retaining the scoped portal; direct cross-dealer resource access is now denied after migration. PR #16 fixes the portal's session CSRF token and replaces disappearing load failures with persistent errors and retry. PR #16 deployed as `fb41a7b5b0b08c7f6fc3f625169ce12a6dc9d662` at 2:23 PM; its explicit migration succeeded at 2:24 PM. Browser render, draft save/reload, and responsive Overview/Documents/Account/edit pages passed. Persistent failure/retry recovery also passed. Temporary test users were disabled, API keys revoked, and the temporary Administrator mapping removed. Synthetic accepted/draft samples remain labeled test evidence.

ACH autopay and status-notice delivery are paused. ACH scope is Controlled Pilot, with no pilot loan selected. No real dealer/factory email, signing invitation, debit, loan disbursement or financial posting was initiated. Private screenshots, API receipts, record IDs and setup readbacks stay in the local hosted-evidence folder rather than this public repository.

## Remaining work and ownership

| Work | Who / what is needed |
|---|---|
| Deployment | DCR-only deployment, backup and explicit migration completed; portal patch `fb41a7b` is installed and migrated, with browser save/reload proof. |
| ACHQ/Plaid wiring | Tristan/provider: merchant/gate credentials, correct persisted sandbox mode, Plaid processor permissions and credentials, callback secret/actual delivery contract, approved synthetic bank data. Source request/query/cancellation were verified with fabricated public sandbox data; hosted settlement and callback acceptance remain open. |
| Email and signing setup | Name a controlled test inbox. Native outgoing Email Account is configured, but delivery is untested. DocuSign sandbox credentials are present; Connect HMAC is missing and JWT consent/invitation/callback delivery need acceptance. Verify branded service sender/domain and settings. |
| Test identities and accounting master data | Synthetic dealers, scoped Website Users and approved Factory Assignments exercised the technical paths. Real pilot access and MIFA/credit setup remain deliberate. Loan Product accounts exist; ACH clearing account and Mode of Payment are missing. |
| Remaining hosted acceptance | Controlled email/invitation delivery, positive signed provider callbacks, complete Floored loan/disbursement/receipt workflow, repayment/GL, settlement/returns/unknown/retry/cancellation scenarios, and real pilot login/reset/logout. Technical intake/security/preview/chart checks are complete; DCR supplies financial expectations and business acceptance. |
| Model/Inventory home type | DCR decision required: exact third-type label and checklist rules. Spec and Customer Sold remain the supported choices. No invented checklist requirements. |
| Financial rules | DCR decision required: 360/365 day count, regular/default/late fees, partial period and dated payoff examples, rebates/insurance and rounding, installed value versus selling price as the LTV denominator. Installed value is captured but does not replace the current denominator. |
| Final documents | DCR approves Dealer Agreement, MIFA, flooring packet, pre-approval, payoff, and factory PO wording/payment instructions. Quote attachments and dealer/quote/buyer context are implemented; final legal/business wording and any further PO layout simplification remain review work. |
| ASW transfer | Source Admin is available through the already-connected `Alumicraft` account on all eight repos. ASW has no Frappe Cloud GitHub app installation; Vercel uses selected repos. Connect Cloud to ASW and verify its app source associations, destination creation permission for the source owner, and hosted email access. No transfer has been attempted. |
| Final handoff | Provide working logins, portal URL, approved workflow, acceptance evidence, synthetic-record labels, and the explicit limitations below. |

## Setup before testing

1. **Keep ACH scope Controlled Pilot.** Select one synthetic `pilot_loan`; missing selection fails closed. Keep expanded real-debit activation off. Record any existing unresolved transactions before testing. Disabling new autopay does not disable read-only receipt polling/reconciliation.
2. **ACH Settings:** Merchant ID, Gate ID, Gate Key; environment; webhook secret; callback `https://backdesk.dealercapital.net/api/method/dcr.api.achq_integration.achq_webhook`; provider-confirmed signature header/body format and optional maintained source-IP list. Match Plaid environment and processor integration. Complete the Customer billing address/contact; WEB requires the captured authorization IP. Public Sandbox is restricted to 2001/test/test, Controlled Pilot and fabricated data; legacy Sandbox is response-only development mode. Set approved SEC/check type, timing/cutoff/notification policy and at most two eligible retries.
3. **Accounting:** ACH Clearing Account and Mode of Payment, clearing-to-bank reconciliation, Loan Product accounts/terms, Company and cost center defaults. Settled ACH now posts native Loan Repayment, not a second Payment Entry. Existing legacy receipts require reconciliation before new posting.
4. **Email:** Email Service Settings, approved sender/domain and DCR branding, hosted service URL/shared secret, Resend key. Separately configure a default outgoing native Email Account. Status and ACH notices use native Email Queue directly, bypassing the shared app's immediate send override.
5. **Status notices:** DCR Pilot Settings delivery defaults off. Set `pilot_notification_recipient` and intended staff mailbox before enabling it. All status deliveries go to the pilot override. Check Recorded → Queued → native Sent, rather than treating queue creation as delivery.
6. **DocuSign:** sandbox Account ID, Integration Key, User ID, RSA key, JWT consent; Connect HMAC. Callback `https://backdesk.dealercapital.net/api/method/dcr.api.docusign.docusign_webhook`. Confirm signing anchors and source attachments in rendered PDFs.
7. **Identity/data:** two enabled Dealer Customers with one Website User per Customer; intended staff roles; submitted active Factory Assignments; onboarding documents and approved loan/product/credit data. Do not put live dealer/factory addresses on synthetic records.
8. **Hosted jobs:** verify scheduler/workers and logs for daily upcoming/initiation/retries and hourly receipt/accounting/notice work. Scheduling currently selects a payment exactly the advance-notice interval away; it does not sweep missed dates or overdue history. Configure the pilot dates deliberately.

ACHQ [sandbox documentation](https://developers.achq.com/docs/sandbox-and-testing) distinguishes persisted sandbox transactions from development responses. Production credentials plus `TestMode=On` are not proof of a persisted status/settlement cycle. Confirm the selected mode with the provider.

## Acceptance sequence

Record expected and observed values plus record IDs; preserve evidence even when a case fails.

1. **Deployment:** backup/build/migration/SHA; new fields/settings/statuses; submitted-record storage editing; charts in their own sections and all seven on Overview.
2. **Identity:** invitation/reset/login/logout; absent/disabled/multiple Customer mappings; Dealer A versus B; restricted staff. Check direct APIs and private files, not just hidden workspace navigation.
3. **Dealer intake/review:** quote, buyer contacts, installed value, factory/address; upload/replace/download; save/edit/reload; submit for review; request changes/resubmit; staff native acceptance; one durable notice per transition.
4. **Cash deal:** required documents → PO → controlled factory inbox with generated PDF and original uploaded quote → receipt/delivery → accounting. No flooring loan.
5. **Floored deal:** HBR → application → approved credit → exact packet preview → sandbox signing → loan/disbursement → PO/receipt. Verify amounts, GL, links, stages and available credit.
6. **Signature failure/replay:** preview sends nothing; edited source/recipient and expired token require new review; exact reviewed bytes sent; JSON SIM callback attaches signed PDF; duplicate completion does not duplicate processing; download failure remains retryable. Reconcile Outcome Unknown envelopes before resending.
7. **Financial examples:** approved daily accrual/first period/principal phase/fees/payoff/rebates/insurance. The prior $100k at 12% interest-only preview is a UI regression example, not approval of a contract day-count convention.
8. **ACH:** bank link/token/masked account/default/loan override; selected pilot only; schedule/notice/admission/remote ID/cleared receipt; exactly one submitted Loan Repayment with correct demand allocation and GL. Check duplicates, timeout/unknown, accounting failure/recovery, R01/R09 cap, other return codes, pause/revoke/cancellation refusal, and a post-clear return.
9. **Reporting/UI:** quote/serial search, storage marker, map buyer/location/loan stage, partial/full payoff and credit, chart/report reconciliation, light/dark pages and phone portal.
10. **Handoff:** functioning staff/dealer access, workflow, known limitations, acceptance record and named owner for provider/accounting exceptions. Queued email and same-day debit initiation are not proof of delivery/clearing.

## Operational limitations and production gates

- **Reversal Pending** requires deliberate accounting review/reversal. There is no automatic post-clear financial reversal.
- **Outcome Unknown** ACH/signature records block resubmission until provider reconciliation. DocuSign records carry the Signature Request name as transaction ID; its lookup window is seven days. Check attachment/email errors independently of envelope completion.
- Model/Inventory type, approved financial policy and final document wording remain open. Future factory portal/QR, automatic UCC work, insurance/inspection exports, bank feeds and expanded portal administration are separate follow-ups. Funded deals still need a named manual UCC/insurance/inspection owner where required.
- Full Bryt/QuickBooks cutover needs reconciled active-loan balances/accrual/history/next dates, provider-supported bank authorizations/tokens, opening trial balance and bank/AR/AP balances, history ownership, backup/recovery and a single debit owner during transition. Do not let both systems collect one installment.
- Expand to All Eligible Loans only after approved real-provider/accounting acceptance and an operator procedure for pending, returned, uncertain and failed payments.

Sources: [Meeting Changes](codex://threads/019fbefc-478d-7562-93ec-2e6a50829540), [controlled-pilot source notes](controlled-pilot-2026-10-05.md), [home-page chart acceptance](home-page-charts-2026-10-05.md), [ASW architecture/transfer review](app-structure-review-2026-10-05.md).
