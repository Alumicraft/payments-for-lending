# October 5 pilot fix batch

This branch prepares source changes for the October 6 controlled pilot. It has not been deployed, does not configure providers, and does not send email or initiate payments.

## Changes

- Dealer intake now accepts and saves the existing HBR `quote_no` field, returns it in detail and editable draft data, and displays it in the portal. The portal JavaScript asset URL is versioned for the update.
- Factory PO email context and subject use the dealer Customer on the linked HBR. A PO without an HBR no longer labels the factory as the dealer.
- DCR email preview checks document read access. PO sending checks read and email access. Linked HBR context also requires HBR read access.
- All four workspace map endpoints require a System User with HBR read permission. Heatmap records and factory counts are limited to permission-filtered HBRs; factory locations use permission-filtered Suppliers. An empty permitted record set does not fall back to unrestricted SQL.

The map uses Frappe's permission-aware `get_list` before its aggregation SQL. See the [Database API](https://docs.frappe.io/framework/user/en/api/database). Document checks use [Document API permissions](https://docs.frappe.io/framework/user/en/api/document).

## Local verification

- Full Python suite: 241 passed, zero skipped. Frappe is mocked, so this is not hosted integration proof. The local Python 3.9 SSL-library warning is unrelated to the changed code.
- Portal JavaScript syntax and Git whitespace checks pass.
- Regression cases exercised against the original API source demonstrate the previous unauthorized access, incorrect dealer label, and missing quote readback. After enabling exception behavior in the draft-write test, its fixture was corrected to represent a draft's `docstatus` through `get`, as Frappe documents do.
- The Frappe `version-16` source was checked for `get_list`, permission checks, and the `limit_page_length` argument. The exact deployed framework revision still needs hosted verification.

## Hosted acceptance after deployment

1. Link a controlled test dealer user to its Customer; verify that user's own-deal scoping and denial for another dealer's records.
2. Create a draft with a factory quote number, reload, edit it, reload again, and submit for review. Verify the staff HBR and PO email preview retain that number.
3. With staff access, preview an HBR-linked PO. Dealer must show the Customer dealer; factory remains the supplier/recipient; end buyer remains a separate value. Previewing must produce no outbound message.
4. Check all map endpoints as a dealer and as a staff user lacking HBR read access: both must be denied. As authorized staff, verify map rendering and factory counts. Test a staff user with a restrictive Customer User Permission: other dealers' homes and counts must be absent.
5. Verify a user lacking document read permission cannot preview it, and a user lacking PO email permission cannot send it. Verify an unreadable linked HBR cannot be exposed through a readable PO.
6. Verify a normal staff map account can read the required Suppliers. A user lacking Supplier read permission now receives a permission failure instead of unrestricted factory data.

ACHQ setup, accounting-result reconciliation, DocuSign review flow, automatic status messages, home type decisions, workspace chart completion, and source-repository Admin access for the ASW transfer remain separate work. This batch does not establish full pilot readiness.
