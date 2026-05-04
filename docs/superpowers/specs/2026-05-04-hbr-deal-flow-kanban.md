# HBR Deal Flow Kanban (Pipeline View)

## Goal
Create a clean pipeline view for HBRs that aligns to operational milestones and avoids duplicate states.

## Primary Board (Ops Truth)
Use three core columns tied directly to document state:

1. **Pending**
   - Definition: No active Purchase Order exists.
   - Includes: Draft HBRs and submitted HBRs that still have no active PO.
   - Rule: Any HBR with no PO in `docstatus=1` remains here.

2. **Ordered**
   - Definition: At least one active Purchase Order exists (`docstatus=1`).
   - Exit condition: A Purchase Receipt is submitted (`docstatus=1`).

3. **Delivered**
   - Definition: A Purchase Receipt exists and is submitted (`docstatus=1`).
   - This is the terminal state for this board.

## Suggested Swimlanes (Optional, same 3 columns)
If you want richer deal flow without adding more columns, use swimlanes or badges:

- **Aging**: 0-7d, 8-14d, 15+d in current column
- **Risk**: Blocked, Missing info, Vendor delay
- **Priority**: High, Medium, Low
- **Owner**: RM / Ops assignee

This preserves a simple board while still surfacing urgency and exceptions.

## Deal Flow Variant (Business-Friendly Labels)
If stakeholders want a sales-style “deal flow” naming convention, map labels like this:

- **Sourcing** -> **Pending**
- **Execution** -> **Ordered**
- **Fulfillment** -> **Delivered**

Keep the backend logic pinned to PO/PR docstatus, and only change display labels.

## Recommended WIP & Alerts
- **Pending WIP cap**: alert if > N items per owner.
- **Ordered SLA alert**: flag cards in Ordered > X days.
- **Delivered cleanup**: auto-archive cards after Y days.

## Card Fields to Display
Keep cards compact but actionable:
- HBR ID / borrower name
- Amount
- Owner
- Days in stage
- PO # (when Ordered)
- PR # and delivered date (when Delivered)
- Risk badge (if any)

## Why this works
- Matches your source-of-truth objects (PO and PR).
- Minimizes state ambiguity.
- Scales with swimlanes/badges instead of column sprawl.
- Keeps Draft out of the way while still visible in Pending.
