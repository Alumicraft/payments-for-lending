# ACHQ provider contract verification — October 5, 2026

Direct HTTP tests used ACHQ's published public sandbox merchant 2001, its published test token, fabricated billing information and $1 amounts. Provider email was disabled. No site settings, real merchant credentials, dealer records or browser session were used. All three accepted synthetic payments were cancelled.

## Defects found and fixed

- The previous payment payload was refused with response code **151 / FieldValueIsNotValid**. It omitted required `TokenSource` and billing/contact fields, plus explicit customer-email and Express Verify flags. Manual ACHQ tokens now send `TokenSource=ACHQ`; Plaid tokens send `Plaid`.
- Payment initiation validates the dealer's billing address, phone and email before committing remote admission. Missing local data leaves the transaction Scheduled. WEB additionally requires the recorded authorization IP. Review the primary Customer Address/contact against the bank authorization; the app does not fabricate missing data.
- Both merchant and provider software reference fields carry the internal ACH Transaction name. The accepted primary `TransAct_ReferenceID` is preserved for reconciliation and `ECheck.Void`.
- StatusTrackingQuery returned **CSV**, including when `ResponseType=JSON` was requested. Direct merchant responses had ten columns; published platform responses use eleven. Both layouts are parsed; platform results are filtered by merchant. Quoted return explanations are preserved. Malformed reports fail explicitly. Rows without a remote reference are skipped with a warning and count, rather than hiding valid events.
- New **Public Sandbox** settings mode uses only the published `2001/test/test` credentials, omits TestMode and requires Controlled Pilot scope. Existing **Sandbox** remains the backwards-compatible development-response mode with `TestMode=On`. Its default is unchanged. No live configuration was switched on.

## Receipts

| Test | Merchant reference | Remote reference | Result |
|---|---|---|---|
| Corrected manual payload | `DCR-SYNTHETIC-dd5059be72604f93` | `36177867` | Approved; later located by its unique merchant reference; Void approved. |
| Both internal reference fields | `DCR-SYNTHETIC-6670427f4a894f19` | `36177960` | Approved; tracking ID matched acknowledgement; Void approved. |
| Corrected native ACHQClient | `DCR-SYNTHETIC-81efb4a3e2bf470d` | `36178048` | Created with the source client, read through its CSV parser, Void approved, Cancelled event read back. |

The third test started at **2026-10-05 18:27:38 UTC**. Its tracking report showed Created at 13:27:50 and Cancelled at 13:28:45 in the provider's report time. Four unrelated report rows had no remote ID and were reported/excluded. No other sandbox users' records were saved. Initial immediate queries did not contain the new rows, and one immediate cancellation was refused with 103; later reconciliation/cancellation succeeded. A missing immediate event is not a reason to submit a second payment.

## What this establishes

The source client's payment request, primary reference, direct-merchant CSV query, cancellation request and cancellation readback work against the public sandbox. The complete local suite has **360 passed, zero skipped**, using mocked Frappe on Python 3.12; nine existing map datetime deprecation warnings remain.

This does not establish a hosted Frappe deployment, database concurrency, persisted Loan Repayment/GL allocation, Plaid linking, real merchant acceptance, signed webhook delivery, clearance, returns, retries or email delivery. Those remain in the [delivery checklist](delivery-checklist-2026-10-06.md).

## Setup implications

1. For persisted public tests choose Public Sandbox and published credentials, Controlled Pilot, one synthetic loan and entirely fabricated billing/account information. The public account exposes submitted data to other test users.
2. For private/provider sandbox testing obtain the correct merchant mode and credentials from ACHQ. Do not infer persistence from a development success response.
3. Complete and review Customer billing address/contact; record authorization IP for WEB. Confirm SEC/check type and the account holder's identity with the operator.
4. Reconcile existing unknown payments by reference, allow for provider indexing delay, and confirm cancellation before replacing an attempt. Never re-submit solely because an immediate status query is empty.
5. Verify real callback authentication, settlement/return scenarios and exactly one native Lending receipt in the hosted pilot before expanded activation.

Sources: [ACHQ sandbox/development distinction](https://developers.achq.com/docs/sandbox-and-testing), [required token-payment fields](https://developers.achq.com/docs/use-a-token), [CSV event report](https://developers.achq.com/docs/payment-event-tracking), [cancellation contract](https://developers.achq.com/docs/cancel-a-payment).
