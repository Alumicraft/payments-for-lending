# Dealer HBR Web Form and dashboard

The dealer experience uses a standard Frappe Web Form for Home Build Request and the custom DCR dashboard for current requests, documents, signatures and account actions.

- Dashboard: `/portal`.
- New HBR: `/dealer-home-request/new`.
- Edit a dealer-owned draft: `/dealer-home-request/<request-name>/edit`.
- Saving returns to `/portal?request=<request-name>`, opening that request's details. Upload checklist documents there, then choose Submit to DCR for review.

The form uses current Home Build Request metadata for input controls, labels, select options and conditional sections. It exposes the existing dealer input allowlist rather than staff controls or generic Customer/Supplier links. Assigned Factory uses the active Factory Assignment list. The same HBR controller continues to populate the checklist and validate native staff acceptance; Inventory retains the Spec/Floored/private-property checklist.

Dealers remain Website Users. No Dealer native DocPerms are enabled. DCR narrowly adapts the native Web Form save/data endpoints and renderer for this named form; other Web Forms delegate to their original behavior. Both page and API readbacks omit internal fields and checklist waiver controls. Customer scope is derived from the logged-in user's Portal User mapping, including staff-created requests and multiple portal users for one Customer. Request keys do not bypass the dealer identity checks. Draft saves lock the HBR and reject stale native form revisions or current review/submission locks.

Source verification: 378 tests passed with mocked Frappe, zero skipped; changed JavaScript and Git whitespace checks passed. Hosted deployment and native form acceptance must be recorded separately, including new/edit/save/readback, conditional fields, assigned factories, cross-dealer page/data denial, review locks and mobile layout. Provider emails, signing, ACH and accounting are outside this change.
