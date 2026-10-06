// Dealer portal presentation rules that must stay truthful. Pure data, no DOM.
const assert = require("node:assert/strict");
const M = require("../public/js/dealer_portal.js");

const loan = (o) => Object.assign({ source: "Loan", name: "LOAN-1", application_name: "LAPP-1", payments_summary: null, payments_unavailable: false }, o);
const deal = (o) => Object.assign({ name: "HBR-1", docstatus: 0, portal_status: "In review", financing_type: "Floored", documents: { items: [] }, loan: { source: null } }, o);
const accepted = { docstatus: 1, portal_status: "Accepted" };

// Loan stage is the server's value, never the home stage, and unknown values pass through.
assert.equal(M.loanStage(deal({ ...accepted, loan_stage: "Funded", order_stage: "Closed" })).label, "Funded");
assert.equal(M.loanStage(deal({ ...accepted, loan_stage: "Not Started" })).label, "Not Started");
assert.equal(M.loanStage(deal({ ...accepted, loan_stage: "Pending" })).label, "Pending");
assert.equal(M.homeStatus(deal({ ...accepted, loan_stage: "Funded", order_stage: "Closed" })), "Closed");

// Lifecycle is exclusive and sums to the number of requests; attention is separate.
const mixed = [deal({}), deal({ ...accepted, loan_stage: "Funded" }), deal({ ...accepted, loan_stage: "Active" }), deal({ docstatus: 2 }), deal({ ...accepted, order_stage: "Closed" })];
assert.equal(M.lifecycleGroups(mixed).reduce((n, g) => n + g.count, 0), mixed.length);
const funded = deal({ ...accepted, loan_stage: "Funded", loan: loan({}) });
const waiting = { name: "S1", document_type: "Flooring Packet", status: "Sent", actionable: true, reference_name: "LAPP-1" };
assert.equal(M.lifecycle(funded).label, "Funded");
assert.equal(M.needs(funded, [waiting]), "Sign the Flooring Packet");

// Identity: floorplan, then serial, then the request number. Never the buyer.
assert.deepEqual(M.identity(deal({ floor_plan: "Plan A", home_serial_no: "SN-1", home_type: "Spec", end_buyer_name: "Private Person" })), { primary: "Plan A", secondary: "SN-1 · Spec" });
assert.equal(M.identity(deal({ floor_plan: "", home_serial_no: "SN-1" })).primary, "SN-1");
assert.equal(M.identity(deal({ floor_plan: "", home_serial_no: "" })).primary, "HBR-1");

// Checklist progress is not an upload count: waived items complete it with no file.
const waived = deal({ documents: { items: [{ document_type: "A", uploaded: false, complete: true }, { document_type: "B", uploaded: false, complete: true }] } });
assert.deepEqual(M.checklist(waived), { total: 2, uploaded: 0, needed: 0, notRequired: 2, label: "Complete" });
assert.equal(M.checklist(deal({ documents: { items: [{ document_type: "A", uploaded: true, complete: true }, { document_type: "B", uploaded: false, complete: false }] } })).label, "1 needed");

// Signatures: nothing is discarded and no record is treated as superseding another.
const sigs = [
    { name: "old", document_type: "MIFA", status: "Signed", actionable: false, reference_name: "MIFA-1" },
    { name: "new", document_type: "MIFA", status: "Sent", actionable: true, reference_name: "MIFA-2" },
    { name: "void", document_type: "Dealer Agreement", status: "Voided", actionable: false, reference_name: "CUST" },
    waiting,
    { name: "orphan", document_type: "Flooring Packet", status: "Declined", actionable: false, reference_name: "GONE" },
];
const parts = M.partitionSignatures(sigs, [funded]);
assert.equal(parts.waiting.length + parts.history.length, sigs.length);
assert.deepEqual(parts.waiting.map((e) => e.signature.name), ["new", "S1"]); // a signed MIFA does not hide a later pending one
assert.equal(parts.waiting[1].deal, funded); // matched through the loan application
assert.equal(parts.history.find((e) => e.signature.name === "orphan").deal, null);
assert.equal(M.signatureDeal(waiting, [deal({ loan: null })]), null); // a request with no loan object cannot throw

// Payments: past due is separate from upcoming, totals come only from server rows,
// and a loan that could not load is named instead of being summed as zero.
const pay = M.paymentGroups([
    deal({ name: "A", ...accepted, loan: loan({ payments_summary: { as_of: "2026-10-06", history_truncated: true, upcoming: [
        { date: "2026-04-12", total: 100, due_status: "Past due" }, { date: "2025-12-20", total: 50, due_status: "Past due" }, { date: "2026-11-01", total: 200, due_status: "Scheduled" }],
        history: [{ date: "2026-09-01", amount: 75 }] } }) }),
    deal({ name: "B", ...accepted, loan: loan({ payments_summary: { upcoming: [{ date: "2026-05-01", total: null, due_status: "Past due" }], history: [] } }) }),
    deal({ name: "C", ...accepted, loan: loan({ payments_unavailable: true }) }),
    deal({ name: "D" }),
]);
assert.equal(pay.loans, 3);
assert.deepEqual(pay.unavailable, ["C"]);
assert.deepEqual(pay.pastDue.map((r) => r.date), ["2025-12-20", "2026-04-12", "2026-05-01"]);
assert.deepEqual(pay.pastDueTotal, { amount: 150, complete: false, count: 3 }); // a missing amount is flagged, not hidden
assert.equal(pay.upcoming.length, 1);
assert.equal(pay.upcomingTotal.complete, false, "unavailable loan cannot produce a complete aggregate");
assert.equal(pay.paidTotal.complete, false);
assert.equal(pay.pastDueByDeal.find((g) => g.deal === "A").oldest, "2025-12-20");
assert.equal(pay.truncated, true);
assert.equal(M.paymentGroups([deal({})]).reported, false);

// Principal outlook: a flat series is real, past-due principal stays in the balance,
// an unfunded loan adds nothing, and an unavailable loan is flagged.
const now = new Date(2026, 9, 6);
const flat = M.principalOutlook([deal({ ...accepted, loan: loan({ payments_summary: { outstanding_principal: 1000, funded: true, as_of: "2026-10-06", upcoming: [{ date: "2026-11-01", principal: 0 }] } }) })], now);
assert.deepEqual(flat.months.map((m) => m.total), [1000, 1000, 1000, 1000, 1000, 1000]);
assert.equal(flat.balance, 1000);
const stepped = M.principalOutlook([deal({ ...accepted, loan: loan({ payments_summary: { outstanding_principal: 1000, funded: true, as_of: "2026-10-06", upcoming: [
    { date: "2026-04-01", principal: 300, due_status: "Past due" }, { date: "2026-12-15", principal: 400, due_status: "Scheduled" }] } }) })], now);
assert.deepEqual(stepped.months.map((m) => m.total), [1000, 1000, 600, 600, 600, 600]);
const unfunded = M.principalOutlook([deal({ ...accepted, loan: loan({ payments_summary: { outstanding_principal: null, funded: false, upcoming: [] } }) })], now);
assert.equal(unfunded.loans, 0);
assert.equal(unfunded.unavailable, false);
assert.equal(M.principalOutlook([deal({ ...accepted, loan: loan({ payments_unavailable: true }) })], now).unavailable, true);

// Progress: done steps are facts, later steps are pending wording, and a funded
// loan with no signature record says nothing about the packet.
const labels = (d, s) => M.progressSteps(d, s || []).map((step) => step.kind + ":" + step.label);
assert.deepEqual(labels(deal({ documents: { items: [{ document_type: "Plot Plan", uploaded: false, complete: false }] } })), ["done:Saved", "action:Upload Plot Plan", "current:Review", "upcoming:Acceptance"]);
const fundedSteps = labels(deal({ ...accepted, loan_stage: "Funded", order_stage: "Pending", loan: loan({ signed: false }) }));
assert.ok(!fundedSteps.some((l) => /Flooring Packet/.test(l)));
assert.ok(fundedSteps.includes("current:Home order") && fundedSteps.includes("upcoming:Home delivery"));
assert.ok(labels(funded, [waiting]).includes("action:Sign Flooring Packet")); // ...but a packet the server marks actionable is always shown
assert.ok(labels(deal({ ...accepted, loan_stage: "Approved", loan: loan({}) }), [waiting]).includes("action:Sign Flooring Packet"));
assert.deepEqual(labels(deal({ docstatus: 2 })), ["done:Saved", "cancelled:Cancelled"]);

console.log("Dealer portal model: loan stage, lifecycle, identity, checklist, signatures, payments, outlook and progress rules passed");

assert.equal(M.isNumber(Infinity), false);
assert.equal(M.isNumber(" "), false);
assert.equal(M.isNumber(true), false);
assert.equal(M.isNumber("100.25"), true);
const unusual = M.paymentGroups([deal({name:"__proto__", ...accepted, loan:loan({payments_summary:{upcoming:[{date:"2026-10-01",total:20,due_status:"Past due"}]}})})]);
assert.equal(unusual.pastDueByDeal[0].deal, "__proto__");
assert.equal(unusual.pastDueByDeal[0].amount,20);
assert.equal(M.canDownload({uploaded:true,can_download:false}),false,'a recorded URL without an owned private File must not produce a view link');
assert.equal(M.canDownload({uploaded:true,can_download:true}),true);
assert.equal(M.canDownload({uploaded:false,can_download:true}),false);
assert.equal(M.canDownload({uploaded:true}),true,'older API responses remain compatible during rollout');

const unavailableFileDeal = deal({documents:{items:[{document_type:'Spec Info Sheet',uploaded:true,complete:true,can_download:false}]}});
assert.equal(M.needs(unavailableFileDeal, []), 'Replace 1 unavailable file');
assert.equal(M.checklist(unavailableFileDeal).label, 'Complete', 'recorded completion is distinct from file availability');
assert.equal(M.progressSteps(unavailableFileDeal, []).filter(x=>x.replace).length, 1);
assert.equal(M.needs(Object.assign({}, unavailableFileDeal, {docstatus:1,portal_status:'Accepted'}), []), '', 'locked accepted requests must not ask for replacement');
assert.equal(M.needs(deal({documents:{items:[{document_type:'Spec Info Sheet',uploaded:true,complete:true,can_download:false},{document_type:'Factory Quote',uploaded:false,complete:false}]}}), []), 'Replace 1 unavailable file · upload 1 document');
