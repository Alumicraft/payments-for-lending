// Dealer portal. The first part is a pure data model (no DOM) that is also
// loaded by Node tests; the second part renders it.

// Forecast only principal reductions; a demand's outstanding amount is not
// the remaining loan principal. This pure calculation is also verified in Node.
function dcrScheduledPrincipal(balance, schedule, endDate, asOfDate) {
    var remaining = Number(balance);
    schedule.forEach(function (row) {
        var date = String(row.date || "").slice(0, 10);
        if (date && date <= endDate && (!asOfDate || date >= asOfDate) && row.due_status !== "Past due" && row.principal !== null && row.principal !== undefined) {
            remaining -= Math.max(0, Number(row.principal) || 0);
        }
    });
    return Math.max(0, remaining);
}

var dcrPortalModel = (function () {
    "use strict";

    var LOAN_STAGES = ["Not Applicable", "Not Started", "Applied", "Approved", "Funded", "Active", "Closed"];
    var ORDER_STAGES = ["Draft", "Pending", "Ordered", "Delivered", "Closed"];
    var DEALER_AGREEMENTS = ["Dealer Agreement", "MIFA"];

    function isNumber(value) {
        return (typeof value === "number" || typeof value === "string") && String(value).trim() !== "" && Number.isFinite(Number(value));
    }

    function isCancelled(deal) { return deal.docstatus === 2 || deal.portal_status === "Cancelled"; }
    function isAccepted(deal) { return !isCancelled(deal) && (deal.portal_status === "Accepted" || deal.docstatus === 1); }
    function isOpen(deal) { return !isCancelled(deal) && !isAccepted(deal); }
    function canEdit(deal) { return isOpen(deal) && deal.docstatus === 0; }
    function hasLoan(deal) { return !!(deal.loan && deal.loan.source); }
    function summary(deal) { return hasLoan(deal) && deal.loan.payments_summary ? deal.loan.payments_summary : null; }
    function documents(deal) { return (deal.documents && deal.documents.items) || []; }
    function missingDocuments(deal) { return documents(deal).filter(function (item) { return !item.complete && !item.uploaded; }); }
    function unavailableDocuments(deal) { return documents(deal).filter(function (item) { return item.uploaded && item.can_download === false; }); }

    // Checklist progress is not a count of files: an item can be complete
    // because DCR does not require it, with nothing uploaded.
    function checklist(deal) {
        var items = documents(deal);
        var uploaded = items.filter(function (item) { return item.uploaded; }).length;
        var needed = missingDocuments(deal).length;
        return {
            total: items.length,
            uploaded: uploaded,
            needed: needed,
            notRequired: items.length - uploaded - needed,
            label: !items.length ? "—" : (needed ? needed + " needed" : "Complete")
        };
    }

    // Request lifecycle: exactly one value per request, decided in this order.
    //   Cancelled            docstatus 2
    //   In review            saved, not yet accepted
    //   Closed               loan or home stage Closed
    //   Active               loan stage Active (repaying)
    //   Delivered / Ordered  home stage
    //   Funded / Approved / Loan applied   loan stage
    //   Accepted             accepted, nothing further recorded
    // Groups for the Home chart: In review, In progress, Active, Closed.
    // Who must act next is separate: see needs().
    function lifecycle(deal) {
        if (isCancelled(deal)) return { label: "Cancelled", kind: "cancelled", group: "Closed" };
        if (!isAccepted(deal)) return { label: "In review", kind: "progress", group: "In review" };
        if (deal.loan_stage === "Closed" || deal.order_stage === "Closed") return { label: "Closed", kind: "closed", group: "Closed" };
        if (deal.loan_stage === "Active") return { label: "Active", kind: "done", group: "Active" };
        if (deal.order_stage === "Delivered") return { label: "Delivered", kind: "done", group: "In progress" };
        if (deal.order_stage === "Ordered") return { label: "Ordered", kind: "progress", group: "In progress" };
        if (deal.loan_stage === "Funded") return { label: "Funded", kind: "progress", group: "In progress" };
        if (deal.loan_stage === "Approved") return { label: "Approved", kind: "progress", group: "In progress" };
        if (deal.loan_stage === "Applied") return { label: "Loan applied", kind: "progress", group: "In progress" };
        return { label: "Accepted", kind: "done", group: "In progress" };
    }

    function lifecycleGroups(deals) {
        return ["In review", "In progress", "Active", "Closed"].map(function (label) {
            return { label: label, count: deals.filter(function (deal) { return lifecycle(deal).group === label; }).length };
        });
    }

    // The loan's own stage exactly as the server reports it, whatever the value.
    // Never the home stage. Only the mark is chosen here.
    function loanStage(deal) {
        var value = String(deal.loan_stage === null || deal.loan_stage === undefined ? "" : deal.loan_stage).trim();
        var kinds = { "Closed": "closed", "Active": "done", "Not Started": "draft", "Not Applicable": "draft" };
        if (!value) return { label: "Not started", kind: "draft" };
        return { label: value, kind: kinds[value] || "progress" };
    }

    function homeStatus(deal) {
        if (isCancelled(deal)) return "Cancelled";
        if (isOpen(deal)) return "Not started";
        return deal.order_stage || "Pending";
    }

    // What a dealer calls the home: floorplan first, then serial. No buyer name.
    function identity(deal) {
        var primary = deal.floor_plan || deal.home_serial_no || deal.name;
        var parts = [];
        if (deal.floor_plan && deal.home_serial_no) parts.push(deal.home_serial_no);
        if (deal.home_type) parts.push(deal.home_type);
        if (deal.financing_type === "Cash") parts.push("Cash");
        return { primary: String(primary), secondary: parts.join(" · ") };
    }

    function signatureDeal(signature, deals) {
        var reference = signature.reference_name;
        if (!reference) return null;
        return deals.filter(function (deal) {
            return reference === deal.name || (deal.loan && (reference === deal.loan.name || reference === deal.loan.application_name));
        })[0] || null;
    }

    function dealSignatures(deal, signatures) {
        return signatures.filter(function (item) { return signatureDeal(item, [deal]) === deal; });
    }

    function isDealerAgreement(signature) { return DEALER_AGREEMENTS.indexOf(signature.document_type) >= 0; }

    // Every record is kept. "Waiting" is only what the server marks actionable;
    // nothing here decides whether an older or newer record is the valid one.
    function partitionSignatures(signatures, deals) {
        var waiting = [];
        var history = [];
        signatures.forEach(function (item) {
            var entry = { signature: item, deal: signatureDeal(item, deals), dealerLevel: isDealerAgreement(item) };
            (item.actionable ? waiting : history).push(entry);
        });
        return { waiting: waiting, history: history };
    }

    function needs(deal, signatures) {
        var waiting = dealSignatures(deal, signatures).filter(function (item) { return item.actionable; });
        if (waiting.length) return "Sign the " + waiting[0].document_type;
        if (isOpen(deal)) {
            var unavailable = unavailableDocuments(deal).length;
            var count = missingDocuments(deal).length;
            if (unavailable) return "Replace " + unavailable + (unavailable === 1 ? " unavailable file" : " unavailable files") + (count ? " · upload " + count + (count === 1 ? " document" : " documents") : "");
            if (count) return "Upload " + count + (count === 1 ? " document" : " documents");
        }
        return "";
    }

    function sumAmounts(rows, key) {
        var amount = 0;
        var complete = true;
        rows.forEach(function (row) {
            if (isNumber(row[key])) amount += Number(row[key]);
            else complete = false;
        });
        return { amount: amount, complete: complete, count: rows.length };
    }

    function groupByDeal(rows, key) {
        var order = [];
        var groups = Object.create(null);
        rows.forEach(function (row) {
            if (!groups[row.deal]) { groups[row.deal] = []; order.push(row.deal); }
            groups[row.deal].push(row);
        });
        return order.map(function (deal) {
            var total = sumAmounts(groups[deal], key);
            return { deal: deal, rows: groups[deal], amount: total.amount, complete: total.complete, oldest: groups[deal][0].date };
        });
    }

    // Past due, upcoming and paid, from server rows only. A loan whose summary
    // could not load is named in `unavailable` and never summed as if complete.
    function paymentGroups(deals) {
        var out = { pastDue: [], upcoming: [], paid: [], unavailable: [], reported: false, loans: 0, asOf: "", truncated: false };
        deals.forEach(function (deal) {
            if (!hasLoan(deal)) return;
            out.loans += 1;
            if (deal.loan.payments_unavailable) out.unavailable.push(deal.name);
            var data = summary(deal);
            if (!data) return;
            out.reported = true;
            if (data.as_of && String(data.as_of) > out.asOf) out.asOf = String(data.as_of);
            if (data.history_truncated) out.truncated = true;
            (data.upcoming || []).forEach(function (row) {
                (row.due_status === "Past due" ? out.pastDue : out.upcoming).push(Object.assign({ deal: deal.name }, row));
            });
            (data.history || []).forEach(function (row) { out.paid.push(Object.assign({ deal: deal.name }, row)); });
        });
        var byDate = function (a, b) { return String(a.date).localeCompare(String(b.date)); };
        out.pastDue.sort(byDate);
        out.upcoming.sort(byDate);
        out.paid.sort(function (a, b) { return byDate(b, a); });
        out.pastDueTotal = sumAmounts(out.pastDue, "total");
        out.upcomingTotal = sumAmounts(out.upcoming, "total");
        out.paidTotal = sumAmounts(out.paid, "amount");
        if (out.unavailable.length) {
            out.pastDueTotal.complete = false;
            out.upcomingTotal.complete = false;
            out.paidTotal.complete = false;
        }
        out.pastDueByDeal = groupByDeal(out.pastDue, "total");
        return out;
    }

    function pad(number) { return String(number).padStart(2, "0"); }

    // Principal scheduled to remain at each of the next six month ends, summed
    // over funded loans with a known balance. A flat series is a real result.
    function principalOutlook(deals, now) {
        var months = [];
        for (var i = 0; i < 6; i++) {
            var end = new Date(now.getFullYear(), now.getMonth() + i + 1, 0);
            months.push({ date: new Date(now.getFullYear(), now.getMonth() + i, 1), end: end.getFullYear() + "-" + pad(end.getMonth() + 1) + "-" + pad(end.getDate()), total: 0 });
        }
        var loans = 0;
        var balance = 0;
        var unavailable = false;
        deals.forEach(function (deal) {
            if (!hasLoan(deal)) return;
            var data = summary(deal);
            if (deal.loan.payments_unavailable || (data && data.funded !== false && !isNumber(data.outstanding_principal))) unavailable = true;
            if (!data || !isNumber(data.outstanding_principal)) return;
            loans += 1;
            balance += Number(data.outstanding_principal);
            var schedule = (data.upcoming || []).filter(function (row) { return row.date && isNumber(row.principal); });
            months.forEach(function (month) {
                month.total += dcrScheduledPrincipal(data.outstanding_principal, schedule, month.end, data.as_of);
            });
        });
        return { months: months, loans: loans, unavailable: unavailable, balance: loans ? balance : null };
    }

    // Progress for one request. Done steps are stated as facts; the current and
    // later steps are named as things still to happen.
    function progressSteps(deal, signatures) {
        var steps = [{ label: "Saved", kind: "done", note: deal.created_on || "", noteIsDate: true }];
        var open = isOpen(deal);
        if (open) missingDocuments(deal).forEach(function (item) { steps.push({ label: "Upload " + item.document_type, kind: "action", upload: item }); });
        if (open) unavailableDocuments(deal).forEach(function (item) { steps.push({ label: "Replace " + item.document_type, kind: "action", upload: item, replace: true }); });
        if (isCancelled(deal)) {
            steps.push({ label: "Cancelled", kind: "cancelled" });
            return steps;
        }
        steps.push(open ? { label: "Review", kind: "current", note: "With DCR" } : { label: "Reviewed", kind: "done" });
        steps.push(open ? { label: "Acceptance", kind: "upcoming" } : { label: "Accepted", kind: "done" });
        if (open) return steps;

        var chain = [];
        var floored = deal.financing_type === "Floored";
        var loan = LOAN_STAGES.indexOf(deal.loan_stage);
        var order = ORDER_STAGES.indexOf(deal.order_stage);
        if (floored) {
            var packets = dealSignatures(deal, signatures).filter(function (item) { return item.document_type === "Flooring Packet"; });
            var waiting = packets.filter(function (item) { return item.actionable; })[0];
            var signed = !!(deal.loan && deal.loan.signed) || packets.some(function (item) { return item.status === "Signed"; });
            chain.push({ done: "Loan approved", pending: "Loan approval", owner: "With DCR", isDone: loan >= 3 });
            // A funded loan with no signature record says nothing about the packet either way.
            if (signed || waiting || loan < 4) chain.push({ done: "Flooring Packet signed", pending: waiting ? "Sign Flooring Packet" : "Flooring Packet", owner: "With DCR", isDone: signed, signature: waiting });
            chain.push({ done: "Loan funded", pending: "Loan funding", owner: "With DCR", isDone: loan >= 4 });
        }
        chain.push({ done: "Home ordered", pending: "Home order", owner: "With DCR", isDone: order >= 2 });
        chain.push({ done: "Home delivered", pending: "Home delivery", owner: "With the factory", isDone: order >= 3 });
        if (floored) chain.push({ done: "Loan repaid", pending: "Loan repayment", owner: "", isDone: loan >= 6 });
        chain.push({ done: "Closed", pending: "Closing", owner: "", isDone: order >= 4 || loan >= 6 });
        var found = false;
        chain.forEach(function (step) {
            if (step.isDone) { steps.push({ label: step.done, kind: "done" }); return; }
            if (step.signature) { steps.push({ label: step.pending, kind: "action", signature: step.signature }); found = true; return; }
            steps.push(found ? { label: step.pending, kind: "upcoming" } : { label: step.pending, kind: "current", note: step.owner });
            found = true;
        });
        return steps;
    }

    return {
        canDownload: function (item) { return !!item.uploaded && item.can_download !== false; },
        isNumber: isNumber, isCancelled: isCancelled, isAccepted: isAccepted, isOpen: isOpen, canEdit: canEdit,
        hasLoan: hasLoan, summary: summary, documents: documents, missingDocuments: missingDocuments, checklist: checklist,
        lifecycle: lifecycle, lifecycleGroups: lifecycleGroups, loanStage: loanStage, homeStatus: homeStatus, identity: identity,
        signatureDeal: signatureDeal, dealSignatures: dealSignatures, isDealerAgreement: isDealerAgreement, partitionSignatures: partitionSignatures,
        needs: needs, sumAmounts: sumAmounts, paymentGroups: paymentGroups, principalOutlook: principalOutlook, progressSteps: progressSteps
    };
})();

if (typeof module !== "undefined" && module.exports) module.exports = Object.assign({ dcrScheduledPrincipal: dcrScheduledPrincipal }, dcrPortalModel);

(function () {
    "use strict";
    if (typeof document === "undefined") return;

    var root = document.getElementById("dcr-dealer-portal");
    if (!root) return;

    var M = dcrPortalModel;
    var view = document.getElementById("dcr-portal-view");
    var main = document.getElementById("dcr-portal-main");
    var toastBox = document.getElementById("dcr-portal-toast");
    var toastTimer = null;
    var state = { data: null, error: null, loading: true, lastRoute: "", filter: "all", expanded: {}, focusKey: "" };

    var WEB_FORM = "/dealer-home-request";
    var MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
    var UPLOAD_ACCEPT = ".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp";
    var UPLOAD_NOTE = "PDF, Word or image, up to 10 MB";
    var PREVIEW_ROWS = 6;

    var ICONS = {
        home: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><g transform="translate(2.5 2)"><path d="M6.635,18.773V15.716A1.419,1.419,0,0,1,8.058,14.3h2.874a1.429,1.429,0,0,1,1.007.414,1.408,1.408,0,0,1,.417,1v3.058a1.213,1.213,0,0,0,.356.867,1.231,1.231,0,0,0,.871.36h1.961a3.46,3.46,0,0,0,2.443-1A3.41,3.41,0,0,0,19,16.578V7.867a2.473,2.473,0,0,0-.9-1.9L11.434.676A3.1,3.1,0,0,0,7.485.747L.967,5.965A2.474,2.474,0,0,0,0,7.867v8.7A3.444,3.444,0,0,0,3.456,20H5.372a1.231,1.231,0,0,0,1.236-1.218Z"></path></g></svg>',
        paper: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><g transform="translate(3.5 2)"><path d="M4.674,20A4.7,4.7,0,0,1,0,15.29V4.51A4.493,4.493,0,0,1,4.465,0H9.752a.458.458,0,0,1,.455.46V3.68a3.341,3.341,0,0,0,3.308,3.34c.423,0,.794,0,1.122.006.257,0,.481,0,.68,0,.141,0,.323,0,.521,0,.229,0,.486-.005.716-.005A.448.448,0,0,1,17,7.47v8.04A4.473,4.473,0,0,1,12.554,20Zm.01-6.359a.756.756,0,0,0,.743.75h5.386a.756.756,0,0,0,.743-.75.742.742,0,0,0-.743-.741H5.426A.742.742,0,0,0,4.684,13.64Zm0-4.99a.742.742,0,0,0,.743.74H8.772a.742.742,0,0,0,.743-.74.756.756,0,0,0-.743-.75H5.426A.756.756,0,0,0,4.684,8.65Zm8.964-3.091a2.018,2.018,0,0,1-2-2.017V.906a.473.473,0,0,1,.814-.334l3.986,4.187a.477.477,0,0,1-.34.806h-.691C14.793,5.567,14.149,5.564,13.648,5.559Z"></path></g></svg>',
        setting: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><g transform="translate(2.5 2)"><path d="M10.2,20H8.807a2.066,2.066,0,0,1-2.125-2.05A1.9,1.9,0,0,0,4.8,16.13a1.58,1.58,0,0,0-.9.23,2.163,2.163,0,0,1-1.084.3A2.122,2.122,0,0,1,1,15.62l-.7-1.2a2,2,0,0,1-.021-2.05,2.108,2.108,0,0,1,.817-.789,1.653,1.653,0,0,0,.644-.64,1.782,1.782,0,0,0,.19-1.365A1.837,1.837,0,0,0,1.071,8.44,2.045,2.045,0,0,1,.314,5.61L1,4.43a2.123,2.123,0,0,1,2.882-.76,1.894,1.894,0,0,0,.9.224A1.959,1.959,0,0,0,6.446,2.98a1.538,1.538,0,0,0,.236-.88A1.788,1.788,0,0,1,6.968,1.04,2.2,2.2,0,0,1,8.776,0h1.441a2.154,2.154,0,0,1,1.82,1.04A1.781,1.781,0,0,1,12.312,2.1a1.545,1.545,0,0,0,.235.88,1.964,1.964,0,0,0,1.672.914,1.926,1.926,0,0,0,.9-.224,2.111,2.111,0,0,1,2.872.76l.684,1.18a2.027,2.027,0,0,1-.756,2.831,1.829,1.829,0,0,0-.853,1.138,1.771,1.771,0,0,0,.2,1.362,1.571,1.571,0,0,0,.634.64,2.307,2.307,0,0,1,.828.789,2.031,2.031,0,0,1-.02,2.05l-.715,1.2a2.1,2.1,0,0,1-2.893.74,1.621,1.621,0,0,0-.9-.23,1.9,1.9,0,0,0-1.891,1.82A2.061,2.061,0,0,1,10.2,20ZM9.512,7.18a2.87,2.87,0,0,0-2.9,2.83,2.763,2.763,0,0,0,.849,2,2.93,2.93,0,0,0,2.053.821A2.822,2.822,0,0,0,11.55,8.006,2.877,2.877,0,0,0,9.512,7.18Z"></path></g></svg>',
        logout: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><g transform="translate(2 2)"><path d="M4.517,20A4.482,4.482,0,0,1,0,15.56V4.45A4.493,4.493,0,0,1,4.528,0H9.492A4.48,4.48,0,0,1,14,4.44V9.23H7.9a.77.77,0,1,0,0,1.54H14v4.78A4.493,4.493,0,0,1,9.472,20ZM16.54,13.451a.773.773,0,0,1,0-1.09l1.6-1.59H14V9.23h4.14l-1.6-1.59a.773.773,0,0,1,0-1.09.764.764,0,0,1,1.09-.01l2.92,2.91a.766.766,0,0,1,.229.55.741.741,0,0,1-.229.54l-2.92,2.911a.762.762,0,0,1-1.09,0Z"></path></g></svg>',
        paperupload: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><g transform="translate(3.5 2)"><path d="M4.674,20A4.7,4.7,0,0,1,0,15.29V4.51A4.493,4.493,0,0,1,4.465,0H9.752a.464.464,0,0,1,.455.46V3.68a3.341,3.341,0,0,0,3.308,3.34c.416,0,.785,0,1.11.005.256,0,.482,0,.682,0,.141,0,.323,0,.521,0,.229,0,.486-.005.716-.005A.453.453,0,0,1,17,7.47v8.04A4.478,4.478,0,0,1,12.544,20ZM7.4,9.293V14.12a.738.738,0,1,0,1.475,0V9.29l1.574,1.6a.731.731,0,0,0,1.04,0,.739.739,0,0,0,.01-1.05L8.654,6.96A.78.78,0,0,0,8.416,6.8a.644.644,0,0,0-.277-.06.7.7,0,0,0-.287.06.78.78,0,0,0-.238.159L4.783,9.84a.748.748,0,0,0,0,1.05.731.731,0,0,0,1.04,0l1.572-1.6,0,0Zm6.246-3.733a2.018,2.018,0,0,1-2-2.017V.906a.472.472,0,0,1,.813-.334C13.53,1.7,15.4,3.661,16.445,4.759a.477.477,0,0,1-.34.806h-.691C14.787,5.567,14.144,5.564,13.642,5.559Z"></path></g></svg>',
        edit: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><g transform="translate(3 3)"><path d="M11.28,18a1.023,1.023,0,0,1,0-2.047h5.71a1.023,1.023,0,0,1,0,2.047ZM.848,17.576l-.8-3.451a2.132,2.132,0,0,1,.4-1.8L6.684,4.268a.313.313,0,0,1,.424-.054L9.73,6.3a.846.846,0,0,0,.647.183.945.945,0,0,0,.817-1.043,1.053,1.053,0,0,0-.329-.635L8.319,2.763a.378.378,0,0,1-.064-.526L9.241.957A2.584,2.584,0,0,1,13.03.7l1.475,1.172a3.062,3.062,0,0,1,1.146,1.752,2.4,2.4,0,0,1-.488,2.042L6.377,17.028a2.105,2.105,0,0,1-1.634.817l-3.5.042A.4.4,0,0,1,.848,17.576Z"></path></g></svg>',
        send: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><g transform="translate(2 2)"><path d="M19.435.582A1.933,1.933,0,0,0,17.5.079L1.408,4.76A1.919,1.919,0,0,0,.024,6.281a2.253,2.253,0,0,0,1,2.1L6.06,11.477a1.3,1.3,0,0,0,1.61-.193l5.763-5.8a.734.734,0,0,1,1.06,0,.763.763,0,0,1,0,1.067l-5.773,5.8a1.324,1.324,0,0,0-.193,1.619L11.6,19.054A1.91,1.91,0,0,0,13.263,20a2.078,2.078,0,0,0,.25-.01A1.95,1.95,0,0,0,15.144,18.6L19.916,2.525a1.964,1.964,0,0,0-.48-1.943"></path></g></svg>',
        danger: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><g transform="translate(2 3)"><path d="M17.316,18H2.679a3.129,3.129,0,0,1-.91-.2A2.809,2.809,0,0,1,.218,16.275,2.747,2.747,0,0,1,.21,14.146L7.529,1.433a2.746,2.746,0,0,1,1.1-1.08A2.819,2.819,0,0,1,9.993,0a2.853,2.853,0,0,1,2.484,1.442l7.268,12.615a2.936,2.936,0,0,1,.25,1,2.753,2.753,0,0,1-.73,2.021A2.841,2.841,0,0,1,17.316,18ZM10,12.272a.873.873,0,1,0,0,1.745.877.877,0,0,0,.869-.883A.867.867,0,0,0,10,12.272ZM10,6.09a.872.872,0,0,0-.88.862v2.8a.888.888,0,0,0,.88.873.872.872,0,0,0,.869-.873v-2.8A.867.867,0,0,0,10,6.09Z"></path></g></svg>',
        money: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2.8v18.4M16.6 8.2c-.6-1.6-2.3-2.6-4.5-2.6-2.7 0-4.7 1.4-4.7 3.4 0 4.6 9.5 2.2 9.5 6.9 0 2-2 3.5-4.8 3.5-2.4 0-4.2-1.1-4.9-2.8"></path></svg>'
    };
    var FILE_ICONS = {
        pdf: '<svg width="24" height="24" viewBox="0 0 40 40" fill="none" aria-hidden="true"><path fill="#D92D20" d="M4 4a4 4 0 0 1 4-4h16l12 12v24a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z"></path><path fill="#fff" d="m24 0 12 12h-8a4 4 0 0 1-4-4z" opacity=".3"></path><path fill="#fff" d="M11.75 32v-6.546h2.582q.744 0 1.268.285.524.281.8.783.277.498.277 1.15 0 .653-.28 1.151a1.94 1.94 0 0 1-.816.777q-.53.278-1.285.278H12.65v-1.11h1.423q.399 0 .658-.137a.9.9 0 0 0 .39-.386q.13-.25.13-.572 0-.326-.13-.57a.88.88 0 0 0-.39-.38q-.262-.137-.665-.137h-.933V32zm8.147 0h-2.32v-6.546h2.339q.987 0 1.7.394.712.39 1.096 1.122.387.731.387 1.75 0 1.024-.387 1.759-.384.735-1.102 1.128-.717.393-1.713.393m-.937-1.186h.879q.614 0 1.032-.217.422-.22.633-.68.214-.464.214-1.196 0-.726-.214-1.186a1.4 1.4 0 0 0-.63-.677q-.418-.218-1.032-.218h-.882zM24.124 32v-6.546h4.334v1.142h-2.95v1.56h2.662v1.14h-2.662V32z"></path></svg>',
        img: '<svg width="24" height="24" viewBox="0 0 40 40" fill="none" aria-hidden="true"><path fill="#7F56D9" d="M4 4a4 4 0 0 1 4-4h16l12 12v24a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z"></path><path fill="#fff" d="m24 0 12 12h-8a4 4 0 0 1-4-4z" opacity=".3"></path><path fill="#fff" d="M13.15 25.455V32h-1.383v-6.546zm1.14 0h1.706l1.802 4.397h.077l1.803-4.398h1.706V32h-1.342v-4.26h-.054l-1.694 4.228h-.914l-1.694-4.244h-.055V32H14.29zm12.575 2.115a1.4 1.4 0 0 0-.189-.412 1.28 1.28 0 0 0-.694-.502 1.7 1.7 0 0 0-.488-.067q-.502 0-.883.25a1.63 1.63 0 0 0-.588.725q-.21.472-.21 1.157 0 .684.207 1.163.209.48.588.732a1.6 1.6 0 0 0 .898.25q.47 0 .802-.167a1.2 1.2 0 0 0 .512-.476q.18-.306.179-.726l.281.042h-1.687v-1.042h2.739v.825q0 .863-.365 1.483a2.5 2.5 0 0 1-1.003.952q-.639.333-1.464.332-.921 0-1.617-.405a2.8 2.8 0 0 1-1.087-1.16q-.387-.755-.387-1.79 0-.796.23-1.42.234-.625.652-1.06.42-.434.975-.662.557-.227 1.205-.227.556 0 1.036.163.48.16.85.454.375.295.61.7.238.402.304.888z"></path></svg>',
        docx: '<svg width="24" height="24" viewBox="0 0 40 40" fill="none" aria-hidden="true"><path fill="#155EEF" d="M4 4a4 4 0 0 1 4-4h16l12 12v24a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z"></path><path fill="#fff" d="m24 0 12 12h-8a4 4 0 0 1-4-4z" opacity=".3"></path><path fill="#fff" d="M9.565 32h-2.32v-6.546h2.34q.986 0 1.7.394.712.39 1.096 1.122.386.731.386 1.75 0 1.024-.386 1.759-.383.735-1.103 1.128-.716.393-1.713.393m-.936-1.186h.878q.615 0 1.033-.217.422-.22.633-.68.213-.464.214-1.196 0-.726-.214-1.186a1.4 1.4 0 0 0-.63-.677q-.42-.218-1.032-.218h-.882zm11.178-2.087q0 1.07-.405 1.822-.403.75-1.1 1.147a3.1 3.1 0 0 1-1.56.393 3.1 3.1 0 0 1-1.566-.396 2.8 2.8 0 0 1-1.096-1.147q-.402-.75-.402-1.819 0-1.07.402-1.822.403-.75 1.096-1.144a3.1 3.1 0 0 1 1.566-.396q.867 0 1.56.396.697.393 1.1 1.145.405.75.405 1.821m-1.403 0q0-.693-.207-1.17a1.6 1.6 0 0 0-.579-.722 1.56 1.56 0 0 0-.875-.246q-.502 0-.876.246t-.582.723q-.204.476-.204 1.17 0 .692.204 1.169.208.477.582.722.373.246.875.246t.876-.246.579-.722q.207-.476.207-1.17m8.204-.98h-1.4a1.4 1.4 0 0 0-.157-.483 1.2 1.2 0 0 0-.303-.365 1.3 1.3 0 0 0-.429-.23 1.6 1.6 0 0 0-.52-.08q-.509 0-.886.253-.377.25-.585.728-.207.476-.207 1.157 0 .7.207 1.176.21.477.588.72.378.242.873.242.278 0 .514-.073.24-.074.425-.214.186-.144.307-.349.125-.204.173-.466l1.4.006q-.054.45-.272.87a2.6 2.6 0 0 1-.578.744q-.362.326-.863.518a3.2 3.2 0 0 1-1.128.189 3.1 3.1 0 0 1-1.566-.397 2.8 2.8 0 0 1-1.087-1.147q-.396-.75-.396-1.819 0-1.07.402-1.822.403-.75 1.093-1.144.69-.396 1.553-.396.57 0 1.055.16.49.16.866.466a2.4 2.4 0 0 1 .614.745q.24.44.307 1.01m2.15-2.293 1.32 2.231h.05l1.326-2.23h1.563l-1.997 3.272L33.062 32h-1.591l-1.343-2.234h-.05L28.734 32H27.15l2.048-3.273-2.01-3.273z"></path></svg>'
    };

    var MARKS = {
        draft: '<circle cx="7" cy="7" r="5.6" stroke="#8c8c8c" stroke-width="1.4" stroke-dasharray="2.3 2.3"></circle>',
        progress: '<circle cx="7" cy="7" r="5.6" stroke="#0070cc" stroke-width="1.4"></circle><path d="M7 3.6a3.4 3.4 0 0 1 0 6.8z" fill="#0070cc"></path>',
        current: '<circle cx="7" cy="7" r="5.5" stroke="#0070cc" stroke-width="1.4"></circle><circle cx="7" cy="7" r="2.6" fill="#0070cc"></circle>',
        upcoming: '<circle cx="7" cy="7" r="5.5" stroke="#8fc0e8" stroke-width="1.4"></circle>',
        action: '<circle cx="7" cy="7" r="5.5" stroke="#d98200" stroke-width="1.4"></circle><circle cx="7" cy="7" r="2.6" fill="#d98200"></circle>',
        done: '<circle cx="7" cy="7" r="6.3" fill="#30a66d"></circle><path d="M4.3 7.2l1.9 1.9 3.6-3.9" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"></path>',
        closed: '<circle cx="7" cy="7" r="6.3" fill="#8c8c8c"></circle><path d="M4.3 7.2l1.9 1.9 3.6-3.9" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"></path>',
        cancelled: '<circle cx="7" cy="7" r="6.3" fill="#8c8c8c"></circle><path d="M4.8 4.8l4.4 4.4M9.2 4.8L4.8 9.2" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round"></path>',
        neutral: '<circle cx="7" cy="7" r="5.6" stroke="#8c8c8c" stroke-width="1.4"></circle><path d="M4.4 7h5.2" stroke="#8c8c8c" stroke-width="1.4" stroke-linecap="round"></path>'
    };
    var CHEVRON = '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="#8c8c8c" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 2.5L8 6l-3.5 3.5"></path></svg>';
    var PLUS = '<svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M6 1.5v9M1.5 6h9"></path></svg>';

    // ------------------------------------------------------------ helpers
    function esc(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // null and undefined mean "the server has no figure"; zero is a real amount.
    function money(value, currency) {
        if (!M.isNumber(value)) return "—";
        try {
            return new Intl.NumberFormat("en-US", { style: "currency", currency: currency || "USD" }).format(Number(value));
        } catch (error) {
            return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value));
        }
    }

    function compact_money(value) {
        return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 }).format(Number(value));
    }

    function parse_date(value) {
        if (!value) return null;
        var parts = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value));
        var date = parts ? new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3])) : new Date(value);
        return Number.isNaN(date.getTime()) ? null : date;
    }

    // The year is shown whenever it is not the current one, so old rows are unambiguous.
    function fmt_date(value) {
        var date = parse_date(value);
        if (!date) return "";
        var options = { month: "short", day: "numeric" };
        if (date.getFullYear() !== new Date().getFullYear()) options.year = "numeric";
        return new Intl.DateTimeFormat("en-US", options).format(date);
    }

    function plural(count, one, many) { return count + " " + (count === 1 ? one : (many || one + "s")); }

    function mark(kind) {
        return '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">' + MARKS[kind] + "</svg>";
    }

    function status(kind, label) {
        return '<span class="dcr-status">' + mark(kind) + esc(label) + "</span>";
    }

    function small_icon(svg, size) {
        return svg.replace('width="16" height="16"', 'width="' + size + '" height="' + size + '"');
    }

    function section(title, body, aside, id) {
        return '<section class="dcr-section"' + (id ? ' id="' + id + '"' : "") + '><div class="dcr-section-head"><h2>' + esc(title) + "</h2>" + (aside ? '<span class="dcr-small">' + aside + "</span>" : "") + "</div>" + body + "</section>";
    }

    function cells(columns, pairs) {
        var list = pairs.slice();
        while (list.length % columns) list.push(["", ""]);
        return '<dl class="dcr-cells dcr-cells-' + columns + '">' + list.map(function (pair) {
            return "<div><dt>" + esc(pair[0]) + "</dt><dd>" + (pair[2] ? pair[1] : esc(pair[1])) + "</dd></div>";
        }).join("") + "</dl>";
    }

    // Real tables, so every cell is announced with its column heading.
    // columns: [{ label, cls, hidden }]   rows: [{ cells: [html], href, header }]
    function table(caption, columns, rows) {
        var head = columns.map(function (column) {
            return '<th scope="col" class="' + (column.cls || "") + '">' + (column.hidden ? '<span class="dcr-sr">' + esc(column.label) + "</span>" : esc(column.label)) + "</th>";
        }).join("");
        var body = rows.map(function (row) {
            var attrs = (row.href ? ' class="dcr-row-link" data-href="' + esc(row.href) + '"' : "") + (row.cls ? ' class="' + row.cls + '"' : "");
            return "<tr" + attrs + ">" + row.cells.map(function (html, index) {
                var cls = columns[index].cls || "";
                return index === row.header ? '<th scope="row" class="' + cls + '">' + html + "</th>" : '<td class="' + cls + '">' + html + "</td>";
            }).join("") + "</tr>";
        }).join("");
        return '<div class="dcr-table"><table><caption class="dcr-sr">' + esc(caption) + "</caption><thead><tr>" + head + "</tr></thead><tbody>" + body + "</tbody></table></div>";
    }

    function toggle_button(key, total, noun) {
        var open = !!state.expanded[key];
        return '<button type="button" class="dcr-btn-text dcr-more" data-action="toggle" data-key="' + esc(key) + '" data-focus-key="toggle|' + esc(key) + '" aria-expanded="' + (open ? "true" : "false") + '">' + (open ? "Show fewer" : "Show all " + plural(total, noun)) + "</button>";
    }

    function preview(rows, key) {
        return state.expanded[key] ? rows : rows.slice(0, PREVIEW_ROWS);
    }

    function safe_url(value) {
        var text = String(value || "").trim();
        return /^(https?:\/\/|\/(?!\/))/i.test(text) ? text : "";
    }

    // From the API context when it loaded; otherwise from the page, so the
    // no-access and load-error states can still offer a way to reach DCR.
    function support_url() { return safe_url(state.data && state.data.support_url) || safe_url(root.getAttribute("data-support-url")); }

    function support_link(label, cls, accessible_label) {
        var url = support_url();
        return url ? '<a class="' + (cls || "dcr-link") + '" href="' + esc(url) + '"' + (accessible_label ? ' aria-label="' + esc(accessible_label) + '"' : '') + '>' + esc(label || "Contact DCR") + "</a>" : "";
    }

    function toast(message, is_error) {
        if (toastTimer) window.clearTimeout(toastTimer);
        toastBox.innerHTML = (is_error ? '<span class="dcr-toast-icon">' + ICONS.danger + "</span>" : mark("done")) + "<span>" + esc(message || "Something went wrong. Please try again.") + "</span>";
        toastBox.classList.toggle("is-error", !!is_error);
        toastBox.hidden = false;
        toastTimer = window.setTimeout(function () { toastBox.hidden = true; }, is_error ? 8000 : 5000);
    }

    // ------------------------------------------------------------ server
    function csrf_headers() {
        var token = root.getAttribute("data-csrf-token") || window.csrf_token || "";
        return token ? { "X-Frappe-CSRF-Token": token } : {};
    }

    function error_message(payload) {
        if (!payload) return "The request could not be completed.";
        if (payload._server_messages) {
            try {
                var messages = JSON.parse(payload._server_messages);
                if (messages.length) return String(JSON.parse(messages[0]).message).replace(/<[^>]*>/g, "");
            } catch (error) {
                // Fall through to the generic response.
            }
        }
        if (payload.message && typeof payload.message === "string") return payload.message;
        return "The request could not be completed.";
    }

    async function api(method, payload) {
        var response = await fetch("/api/method/dcr.api.dealer_portal." + method, {
            method: "POST",
            headers: Object.assign({ "Content-Type": "application/json" }, csrf_headers()),
            credentials: "same-origin",
            body: JSON.stringify(payload || {}),
        });
        var data = await response.json().catch(function () { return {}; });
        if (!response.ok || data.exc) throw new Error(error_message(data));
        return data.message;
    }

    async function upload_file(input) {
        var form = new FormData();
        form.append("file", input.files[0]);
        form.append("target_type", input.getAttribute("data-upload-target"));
        form.append("target_name", input.getAttribute("data-target-name") || "");
        form.append("document_type", input.getAttribute("data-document-type"));
        var response = await fetch("/api/method/dcr.api.dealer_portal.upload_document", {
            method: "POST",
            headers: csrf_headers(),
            credentials: "same-origin",
            body: form,
        });
        var data = await response.json().catch(function () { return {}; });
        if (!response.ok || data.exc) throw new Error(error_message(data));
        return data.message;
    }

    // ------------------------------------------------------------ shared pieces
    function deals() { return (state.data && state.data.deals) || []; }
    function signatures() { return (state.data && state.data.signatures) || []; }
    function deal_by_name(name) { return deals().filter(function (deal) { return deal.name === name; })[0] || null; }
    function request_href(name) { return "#/request/" + encodeURIComponent(name); }

    // The home's name as a link; the request number stays a separate, whole value.
    function home_link(deal) {
        var who = M.identity(deal);
        return '<a class="dcr-home-link" href="' + request_href(deal.name) + '" aria-label="' + esc(who.primary + ", request " + deal.name) + '">' + esc(who.primary) + "</a>" +
            (who.secondary ? ' <span class="dcr-muted">' + esc(who.secondary) + "</span>" : "");
    }

    function request_number(name) { return '<span class="dcr-id">' + esc(name) + "</span>"; }

    function doc_key(target, name, document_type) { return "doc|" + target + "|" + (name || "") + "|" + document_type; }

    function upload_control(cls, target, name, document_type, label, title) {
        return '<label class="' + cls + ' dcr-upload" tabindex="0" role="button" aria-label="' + esc((label || "Upload") + " " + title) + '" data-focus-key="' + esc(doc_key(target, name, document_type)) + '">' + esc(label || "Upload") +
            '<input type="file" accept="' + UPLOAD_ACCEPT + '" data-upload-target="' + esc(target) + '" data-target-name="' + esc(name || "") + '" data-document-type="' + esc(document_type) + '"></label>';
    }

    function document_links(target, name, document_type, title) {
        var params = new URLSearchParams({ target_type: target, target_name: name || "", document_type: document_type });
        var href = "/api/method/dcr.api.dealer_portal.download_document?" + params.toString();
        return '<a class="dcr-btn-text" href="' + esc(href) + '" target="_blank" rel="noopener" aria-label="' + esc("View " + title) + '" data-focus-key="' + esc(doc_key(target, name, document_type)) + '">View</a>' +
            '<a class="dcr-btn-text" href="' + esc(href) + '" download aria-label="' + esc("Download " + title) + '">Download</a>';
    }

    function file_icon(item) {
        if (!item.uploaded && item.complete) return '<span class="dcr-slot dcr-slot-plain">' + mark("neutral") + "</span>";
        if (!item.uploaded) return '<span class="dcr-slot">' + small_icon(ICONS.paperupload, 12) + "</span>";
        var match = /\.([a-z0-9]+)$/i.exec(item.file_name || "");
        var ext = match ? match[1].toLowerCase() : "";
        if (ext === "pdf") return FILE_ICONS.pdf;
        if (ext === "doc" || ext === "docx") return FILE_ICONS.docx;
        if (ext === "png" || ext === "jpg" || ext === "jpeg" || ext === "webp") return FILE_ICONS.img;
        return '<span class="dcr-slot dcr-slot-filled">' + small_icon(ICONS.paper, 12) + "</span>";
    }

    // One documents table for request checklists and dealer documents.
    // "Uploaded" means a file is on the record; it does not mean reviewed or accepted.
    function documents_table(caption, items, target, name, can_upload) {
        var dated = items.some(function (item) { return item.uploaded_on; });
        var columns = [{ label: "File type", cls: "dcr-c-icon", hidden: true }, { label: "Document" }, { label: "File" }];
        if (dated) columns.push({ label: "Added", cls: "dcr-nowrap dcr-muted" });
        columns.push({ label: "Actions", cls: "dcr-c-act", hidden: true });
        var rows = items.map(function (item) {
            var type = item.fieldname || item.document_type;
            var title = item.label || item.document_type;
            var unavailable = item.uploaded && !M.canDownload(item);
            var file = item.uploaded ? '<span class="dcr-muted">' + esc(unavailable ? "File unavailable" : item.file_name || "Uploaded") + "</span>"
                : (item.complete ? '<span class="dcr-muted">Not required</span>' : (can_upload ? '<span class="dcr-needed">Needed</span>' : '<span class="dcr-muted">Not provided</span>'));
            var actions = (M.canDownload(item) ? document_links(target, name, type, title) : "") +
                (unavailable ? (support_link("Contact DCR", "dcr-btn-text", "Contact DCR about " + title) || '<span class="dcr-muted">Contact DCR for help.</span>') : "") +
                (can_upload && (unavailable || (!item.uploaded && !item.complete)) ? upload_control("dcr-btn-row", target, name, type, unavailable ? "Replace file" : "Upload", title) : "");
            var row = [file_icon(item), '<span class="dcr-strong">' + esc(title) + "</span>", file];
            if (dated) row.push(esc(fmt_date(item.uploaded_on)));
            row.push('<span class="dcr-actions">' + actions + "</span>");
            return { cells: row, header: 1 };
        });
        return table(caption, columns, rows);
    }

    function signature_status(item) {
        if (item.status === "Signed") return status("done", "Signed");
        if (item.actionable) return status("action", "Waiting for your signature");
        if (item.status === "Sent") return status("progress", "Waiting for DCR");
        if (item.status === "Declined") return status("cancelled", "Declined");
        if (item.status === "Voided") return status("cancelled", "Voided");
        if (item.status === "Outcome Unknown") return status("progress", "Checking with DocuSign");
        return status("draft", "Not sent yet");
    }

    // Who a signature record is for: the dealer account, or a named home and request.
    function signature_scope(entry) {
        if (entry.deal) return home_link(entry.deal) + " " + request_number(entry.deal.name);
        if (entry.dealerLevel) return '<span class="dcr-muted">Dealer account</span>';
        return '<span class="dcr-muted">Not linked to a request</span>';
    }

    function sign_button(item, label) {
        return '<button type="button" class="dcr-btn-row" data-action="sign" data-signature="' + esc(item.name) + '" aria-label="' + esc("Sign " + label) + '" data-focus-key="sign|' + esc(item.name) + '">Sign</button>';
    }

    function empty_state(icon, title, text, action) {
        return '<div class="dcr-empty"><span class="dcr-empty-tile">' + small_icon(icon, 20) + "</span><h3>" + esc(title) + "</h3><p>" + esc(text) + "</p>" + (action || "") + "</div>";
    }

    function new_request_button() {
        return '<a class="dcr-btn-primary" href="' + WEB_FORM + '/new">' + PLUS + "New request</a>";
    }

    function page_head(title, action) {
        return '<div class="dcr-page-head"><h1 tabindex="-1">' + esc(title) + "</h1>" + (action || "") + "</div>";
    }

    // ------------------------------------------------------------ Home
    function greeting() {
        var hour = new Date().getHours();
        return hour < 12 ? "Good morning" : (hour < 18 ? "Good afternoon" : "Good evening");
    }

    // Only what the server marks actionable, or a dealer document that is missing.
    // Signed, declined, voided and unsent records are history, not to-dos.
    function attention_rows() {
        var rows = [];
        M.partitionSignatures(signatures(), deals()).waiting.forEach(function (entry) {
            if (entry.deal) return; // shown on its own request row below
            var item = entry.signature;
            rows.push([status("action", "To do"), '<span class="dcr-strong">' + esc("Sign " + item.document_type) + "</span>", '<span class="dcr-muted">' + esc(item.sent_date ? "Sent " + fmt_date(item.sent_date) : "Waiting for your signature") + "</span>",
                '<a class="dcr-btn-row" href="#/settings" aria-label="' + esc("Review " + item.document_type + " in Settings") + '">Review</a>']);
        });
        var needed = ((state.data && state.data.onboarding_documents) || []).filter(function (item) { return !item.uploaded || item.can_download === false; });
        if (needed.length) {
            rows.push([status("action", "To do"), '<span class="dcr-strong">Upload dealer documents</span>', '<span class="dcr-muted">' + esc(needed.map(function (item) { return item.label; }).join(", ")) + "</span>",
                '<a class="dcr-btn-row" href="#/settings" aria-label="Upload dealer documents in Settings">Upload</a>']);
        }
        return rows;
    }

    function attention_section() {
        var rows = attention_rows();
        if (!rows.length) return "";
        var title = deals().some(M.isAccepted) ? "Needs your attention" : "Set up your dealer profile";
        return section(title, table(title, [{ label: "Status", cls: "dcr-nowrap" }, { label: "Step" }, { label: "Details" }, { label: "Actions", cls: "dcr-c-act", hidden: true }],
            rows.map(function (row) { return { cells: [row[0], row[1], row[2], '<span class="dcr-actions">' + row[3] + "</span>"], header: 1 }; })));
    }

    function principal_card() {
        var outlook = M.principalOutlook(deals(), new Date());
        var loans = deals().filter(M.hasLoan);
        var metric = outlook.unavailable || !outlook.loans ? "—" : money(outlook.balance);
        var note = outlook.unavailable ? "Balance details could not load" : (!loans.length ? "No loans yet" : (outlook.loans ? "Across " + plural(outlook.loans, "funded loan") : "No funded loans yet"));
        var chart = "";
        var max = Math.max.apply(null, outlook.months.map(function (month) { return month.total; }));
        if (!outlook.unavailable && outlook.loans && max > 0) {
            var short_month = new Intl.DateTimeFormat("en-US", { month: "short" });
            var long_month = new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" });
            chart = '<div class="dcr-card-foot"><p class="dcr-small" id="dcr-outlook-note">Principal scheduled to remain at each month end.</p>' +
                '<div class="dcr-bars" aria-hidden="true">' + outlook.months.map(function (month, index) {
                    return '<span class="dcr-bar' + (index === 0 ? " is-now" : "") + '"><em>' + esc(compact_money(month.total)) + '</em><i style="height:' + Math.max(2, Math.round(month.total / max * 100)) + '%"></i><b>' + esc(short_month.format(month.date)) + "</b></span>";
                }).join("") + "</div>" +
                '<ul class="dcr-sr" aria-describedby="dcr-outlook-note">' + outlook.months.map(function (month) { return "<li>" + esc(long_month.format(month.date) + ": " + money(month.total)) + "</li>"; }).join("") + "</ul></div>";
        }
        return '<div class="dcr-card"><span class="dcr-small">Outstanding principal</span><span class="dcr-metric">' + esc(metric) + '</span><span class="dcr-small">' + esc(note) + "</span>" + chart +
            (loans.length ? '<a class="dcr-card-link" href="#/lending">View lending</a>' : "") + "</div>";
    }

    function requests_card() {
        var list = deals();
        var colors = { "In review": "#0070cc", "In progress": "#8fc0e8", "Active": "#30a66d", "Closed": "#c7c7c7" };
        var meaning = { "In review": "Saved and with DCR for review", "In progress": "Accepted: approved, funded, ordered or delivered", "Active": "Delivered and repaying the loan", "Closed": "Closed or cancelled" };
        var groups = M.lifecycleGroups(list);
        var need = list.filter(function (deal) { return M.needs(deal, signatures()); }).length;
        return '<div class="dcr-card"><span class="dcr-small">Home build requests</span><span class="dcr-metric">' + list.length + '</span><span class="dcr-small">' + (need ? esc(need + (need === 1 ? " needs" : " need") + " something from you") : "Nothing needed from you") + "</span>" +
            '<div class="dcr-card-foot"><p class="dcr-small">By stage. A request appears once.</p><div class="dcr-stack" aria-hidden="true">' +
            groups.filter(function (group) { return group.count; }).map(function (group) { return '<span style="flex:' + group.count + " 1 0;background:" + colors[group.label] + '"></span>'; }).join("") +
            '</div><ul class="dcr-legend">' + groups.map(function (group) {
                return '<li title="' + esc(meaning[group.label]) + '"><i style="background:' + colors[group.label] + '"></i><em>' + esc(group.label) + '<span class="dcr-sr">: ' + esc(meaning[group.label]) + '</span></em><span class="dcr-num">' + group.count + "</span></li>";
            }).join("") + "</ul></div></div>";
    }

    function payments_card() {
        var pay = M.paymentGroups(deals());
        var lines = "";
        var metric = "—";
        var note;
        if (!pay.loans) note = "No loans yet";
        else if (!pay.reported) note = pay.unavailable.length ? "Payment details could not load" : "No payments before funding";
        else {
            var next = pay.upcoming[0];
            metric = !pay.pastDueTotal.complete ? "—" : pay.pastDue.length ? money(pay.pastDueTotal.amount) : (next ? fmt_date(next.date) : "—");
            note = !pay.pastDueTotal.complete ? "Payment total unavailable; some amounts are missing" : pay.pastDue.length ? "Past due across " + plural(pay.pastDue.length, "payment") : (next ? "Next payment · " + money(next.total) : "Nothing scheduled");
            if (pay.pastDue.length) lines += '<div class="dcr-due">' + mark("action") + '<span class="dcr-grow">Past due</span><span class="dcr-num">' + esc(money(pay.pastDueTotal.amount) + (pay.pastDueTotal.complete ? "" : " known")) + "</span></div>";
            lines += '<div class="dcr-due">' + mark("progress") + '<span class="dcr-grow">' + (next ? (pay.unavailable.length ? "Next recorded · " : "Next · ") + esc(fmt_date(next.date)) : pay.unavailable.length ? "Upcoming details unavailable" : "Nothing scheduled") + '</span><span class="dcr-num">' + esc(next ? money(next.total) : "") + "</span></div>";
            if (pay.unavailable.length) lines += '<div class="dcr-due dcr-muted">' + mark("neutral") + '<span class="dcr-grow">' + esc(plural(pay.unavailable.length, "loan") + " could not load") + "</span></div>";
        }
        return '<div class="dcr-card"><span class="dcr-small">' + (pay.pastDue.length ? "Past due" : "Payments") + '</span><span class="dcr-metric">' + esc(metric) + '</span><span class="dcr-small">' + esc(note) + "</span>" +
            (lines ? '<div class="dcr-card-foot">' + lines + "</div>" : "") + (pay.loans ? '<a class="dcr-card-link" href="#/payments">View payments</a>' : "") + "</div>";
    }

    function requests_table(list) {
        var columns = [{ label: "Status", cls: "dcr-nowrap" }, { label: "Home" }, { label: "Request", cls: "dcr-nowrap" }, { label: "Checklist", cls: "dcr-nowrap dcr-muted" }, { label: "Needs from you", cls: "dcr-nowrap" }, { label: "Open", cls: "dcr-c-chev", hidden: true }];
        return table("Home build requests", columns, list.map(function (deal) {
            var current = M.lifecycle(deal);
            var need = M.needs(deal, signatures());
            return { href: request_href(deal.name), header: 1, cells: [status(current.kind, current.label), home_link(deal), request_number(deal.name), esc(M.checklist(deal).label),
                need ? '<span class="dcr-strong">' + esc(need) + "</span>" : '<span class="dcr-muted">Nothing right now</span>', CHEVRON] };
        }));
    }

    function page_home() {
        var list = deals();
        var needing = list.filter(function (deal) { return M.needs(deal, signatures()); });
        var order = list.slice().sort(function (a, b) { return (M.needs(b, signatures()) ? 1 : 0) - (M.needs(a, signatures()) ? 1 : 0); });
        var shown = state.filter === "needs" ? needing : order;
        var filter = function (key, label, count) {
            return '<button type="button" class="dcr-seg' + (state.filter === key ? " is-on" : "") + '" data-action="filter" data-filter="' + key + '" data-focus-key="filter|' + key + '" aria-pressed="' + (state.filter === key ? "true" : "false") + '">' + label + ' <span class="dcr-num">' + count + "</span></button>";
        };
        var requests;
        if (!list.length) requests = section("Home build requests", empty_state(ICONS.home, "No home build requests yet", "Your requests, loans and payments will show up here.", new_request_button()));
        else {
            var body = shown.length ? requests_table(shown) : '<p class="dcr-note">Nothing needs you right now. Choose All to see every request.</p>';
            requests = '<section class="dcr-section" id="requests"><div class="dcr-section-head"><h2>Home build requests</h2><div class="dcr-segs" role="group" aria-label="Show requests">' + filter("needs", "Needs you", needing.length) + filter("all", "All", list.length) + "</div></div>" + body + "</section>";
        }
        return '<div class="dcr-page">' + page_head(greeting(), list.length ? new_request_button() : "") + attention_section() +
            (list.length ? '<section class="dcr-cards" aria-label="At a glance">' + principal_card() + requests_card() + payments_card() + "</section>" : "") + requests + "</div>";
    }

    // ------------------------------------------------------------ request
    function progress_list(deal) {
        return '<ol class="dcr-steps">' + M.progressSteps(deal, signatures()).map(function (step) {
            var note = step.noteIsDate ? fmt_date(step.note) : step.note;
            var aside = note ? '<span class="dcr-small">' + esc(note) + "</span>" : "";
            if (step.upload) aside = upload_control("dcr-btn-mini", "hbr", deal.name, step.upload.document_type, step.replace ? "Replace file" : "Upload", step.upload.document_type);
            if (step.signature) aside = '<button type="button" class="dcr-btn-mini" data-action="sign" data-signature="' + esc(step.signature.name) + '" aria-label="' + esc("Sign " + step.signature.document_type) + '">Sign</button>';
            var said = { done: "Done", current: "In progress", action: "Needs you", upcoming: "Later", cancelled: "Cancelled" }[step.kind] || "";
            return '<li class="is-' + step.kind + '"><span class="dcr-step-mark">' + mark(step.kind) + '</span><span class="dcr-step-body"><span><span class="dcr-sr">' + said + ": </span>" + esc(step.label) + "</span>" + aside + "</span></li>";
        }).join("") + "</ol>";
    }

    function tracker(deal) {
        var rank = Math.max(["Draft", "Pending", "Ordered", "Delivered", "Closed"].indexOf(deal.order_stage), 1);
        return '<ol class="dcr-tracker">' + ["Pending", "Ordered", "Delivered", "Closed"].map(function (label, index) {
            var position = index + 1;
            var cls = rank === 4 || position < rank ? "is-done" : (position === rank ? "is-now" : "");
            var said = cls === "is-done" ? "Done" : (cls === "is-now" ? "Current" : "Later");
            return '<li class="' + cls + '"><i></i><span><span class="dcr-sr">' + said + ": </span>" + label + "</span></li>";
        }).join("") + "</ol>";
    }

    function payment_components(row) {
        var parts = [];
        if (M.isNumber(row.principal) && Number(row.principal)) parts.push("Principal " + money(row.principal));
        if (M.isNumber(row.interest) && Number(row.interest)) parts.push("Interest " + money(row.interest));
        if (M.isNumber(row.charges) && Number(row.charges)) parts.push("Charges " + money(row.charges));
        return parts.join(" · ");
    }

    function loan_payments_section(deal) {
        var data = M.summary(deal);
        if (!data) return section("Payments", '<p class="dcr-note">' + (deal.loan.payments_unavailable ? "Payment details could not load. Refresh to try again." : "No payments yet. The schedule starts when the loan is funded.") + "</p>");
        var rows = [];
        var key = "loan|" + deal.name;
        (data.upcoming || []).forEach(function (row) {
            var late = row.due_status === "Past due";
            rows.push({ cells: [status(late ? "action" : "progress", late ? "Past due" : "Scheduled"), esc(fmt_date(row.date)), '<span class="dcr-muted">' + esc(payment_components(row)) + "</span>", esc(money(row.total, data.currency))] });
        });
        (data.history || []).forEach(function (row) {
            rows.push({ cells: [status("done", "Paid"), esc(fmt_date(row.date)), '<span class="dcr-muted">' + esc(row.type || "Payment") + "</span>", esc(money(row.amount, data.currency))] });
        });
        if (!rows.length) return section("Payments", '<p class="dcr-note">No payments yet. The schedule starts when the loan is funded.</p>');
        var aside = [data.as_of ? "As of " + fmt_date(data.as_of) : "", data.history_truncated ? "most recent payments shown" : ""].filter(Boolean).join(" · ");
        var body = table("Payments for " + deal.name, [{ label: "Status", cls: "dcr-nowrap" }, { label: "Date", cls: "dcr-nowrap" }, { label: "Details" }, { label: "Amount", cls: "dcr-right dcr-nowrap" }], preview(rows, key));
        return section("Payments", body + (rows.length > PREVIEW_ROWS ? toggle_button(key, rows.length, "payment") : ""), esc(aside));
    }

    function field(deal, name) {
        var value = deal[name];
        if ((value === null || value === undefined || value === "") && deal.editable) value = deal.editable[name];
        return value === null || value === undefined ? "" : value;
    }

    function page_request(name) {
        var deal = deal_by_name(name);
        if (!deal) {
            return '<div class="dcr-topbar"><nav class="dcr-crumbs" aria-label="Breadcrumb"><a href="#/home">Home</a>' + CHEVRON + '<h1 tabindex="-1">' + esc(name || "Request") + '</h1></nav></div><div class="dcr-page">' +
                empty_state(ICONS.home, "This request is not available", "It may belong to another dealer account, or it is no longer in your list.", '<a class="dcr-btn" href="#/home">Back to Home</a>') + "</div>";
        }
        var current = M.lifecycle(deal);
        var open = M.isOpen(deal);
        var accepted = M.isAccepted(deal);
        var loan = deal.loan || {};
        var data = M.summary(deal);
        var who = M.identity(deal);

        var actions = "";
        if (M.canEdit(deal)) actions += '<a class="dcr-btn" href="' + WEB_FORM + "/" + encodeURIComponent(deal.name) + '/edit">' + small_icon(ICONS.edit, 14) + "Edit</a>";
        if (loan.payoff && loan.payoff.can_request) actions += '<button type="button" class="dcr-btn" data-action="payoff" data-hbr="' + esc(deal.name) + '">' + small_icon(ICONS.send, 14) + "Request payoff letter</button>";

        var address = [field(deal, "delivery_address"), field(deal, "address_line_2"), field(deal, "city"), [field(deal, "state"), field(deal, "zip")].filter(Boolean).join(" ")].filter(Boolean).join(", ");
        var details = [["Factory", deal.factory && deal.factory.label || ""], ["Floorplan", deal.floor_plan || ""], ["Serial number", deal.home_serial_no || ""], ["Factory quote", deal.quote_no || ""], ["Quoted amount", money(deal.quoted_amount)]];
        if (address) details.push(["Delivery address", address]);
        if (deal.property_type === "Park") {
            var community = [field(deal, "community_name"), field(deal, "space_number") ? "Space " + field(deal, "space_number") : ""].filter(Boolean).join(" · ");
            if (community) details.push(["Community", community]);
        }
        if (deal.home_type === "Customer Sold") {
            if (deal.end_buyer_name) details.push(["End buyer", deal.end_buyer_name]);
            if (M.isNumber(field(deal, "selling_price"))) details.push(["Selling price", money(field(deal, "selling_price"))]);
            if (M.isNumber(deal.installed_value)) details.push(["Installed value", money(deal.installed_value)]);
        }

        var body = section("Home details", cells(3, details));
        if (accepted && M.hasLoan(deal)) {
            var known = data && M.isNumber(data.outstanding_principal);
            var stage = M.loanStage(deal);
            body += section("Loan details", cells(4, [[known ? "Outstanding principal" : "Principal", money(known ? data.outstanding_principal : loan.principal)],
                ["Interest rate", M.isNumber(loan.interest_rate) ? Number(loan.interest_rate) + "%" : "—"], ["Total interest", money(loan.total_interest)], ["Total payable", money(loan.total_payable)]]), status(stage.kind, stage.label));
        }
        if (accepted) body += section("Home status", tracker(deal), esc(M.homeStatus(deal)));
        var items = M.documents(deal);
        body += section("Documents", items.length ? documents_table("Documents for " + deal.name, items, "hbr", deal.name, open) : '<p class="dcr-note">No documents are required for this request.</p>', open && (M.missingDocuments(deal).length || items.some(function (item) { return item.uploaded && item.can_download === false; })) ? esc(UPLOAD_NOTE) : "");
        var signed = M.dealSignatures(deal, signatures());
        if (signed.length) {
            body += section("Signatures", table("Signatures for " + deal.name, [{ label: "File type", cls: "dcr-c-icon", hidden: true }, { label: "Document" }, { label: "Status" }, { label: "Date", cls: "dcr-nowrap dcr-muted" }, { label: "Actions", cls: "dcr-c-act", hidden: true }],
                signed.map(function (item) {
                    return { header: 1, cells: [FILE_ICONS.pdf, '<span class="dcr-strong">' + esc(item.document_type) + "</span>", signature_status(item), esc(fmt_date(item.signed_date || item.sent_date)), '<span class="dcr-actions">' + (item.actionable ? sign_button(item, item.document_type) : "") + "</span>"] };
                })));
        }
        if (accepted && M.hasLoan(deal)) body += loan_payments_section(deal);

        var loan_stage = M.loanStage(deal);
        var panel = '<aside class="dcr-float" aria-label="Progress and details"><section><h2>Progress</h2>' + progress_list(deal) + '</section><section><h2>Details</h2><dl class="dcr-kv">' +
            "<dt>Status</dt><dd>" + status(current.kind, current.label) + "</dd>" +
            "<dt>Request</dt><dd>" + request_number(deal.name) + "</dd>" +
            "<dt>Home status</dt><dd>" + esc(M.homeStatus(deal)) + "</dd>" +
            "<dt>Loan stage</dt><dd>" + esc(loan_stage.label) + "</dd>" +
            (M.hasLoan(deal) && loan.name ? "<dt>Loan</dt><dd>" + request_number(loan.name) + "</dd>" : "") +
            "<dt>Home type</dt><dd>" + esc(deal.home_type || "—") + "</dd><dt>Deal type</dt><dd>" + esc(deal.financing_type || "—") + "</dd><dt>Property</dt><dd>" + esc(deal.property_type || "—") + "</dd></dl></section></aside>";

        return '<div class="dcr-topbar"><nav class="dcr-crumbs" aria-label="Breadcrumb"><a href="#/home">Home</a>' + CHEVRON + '<h1 tabindex="-1">' + esc(who.primary) + "</h1>" + (who.primary !== deal.name ? request_number(deal.name) : "") + '</nav><div class="dcr-topbar-actions">' + actions + '</div></div><div class="dcr-record"><div class="dcr-record-main">' + body + "</div>" + panel + "</div>";
    }

    // ------------------------------------------------------------ Lending
    function page_lending() {
        var loans = deals().filter(M.hasLoan);
        var body;
        if (!loans.length) {
            body = empty_state(ICONS.paper, "No loans yet", "A loan appears here once DCR opens it for an accepted floored request.");
        } else {
            var columns = [{ label: "Loan stage", cls: "dcr-nowrap" }, { label: "Home" }, { label: "Request", cls: "dcr-nowrap" }, { label: "Home status", cls: "dcr-nowrap dcr-muted dcr-wide-only" }, { label: "Outstanding", cls: "dcr-right dcr-nowrap" }, { label: "Next" }, { label: "Open", cls: "dcr-c-chev", hidden: true }];
            body = table("Loans", columns, loans.map(function (deal) {
                var stage = M.loanStage(deal);
                var data = M.summary(deal);
                var rows = (data && data.upcoming) || [];
                var late = rows.filter(function (row) { return row.due_status === "Past due"; });
                var next = rows.filter(function (row) { return row.due_status !== "Past due"; })[0];
                var need = M.needs(deal, signatures());
                var text;
                if (need) text = '<span class="dcr-strong">' + esc(need) + "</span>";
                else if (late.length) text = '<span class="dcr-status dcr-wrap dcr-strong">' + mark("action") + esc("Past due " + money(M.sumAmounts(late, "total").amount) + (M.sumAmounts(late, "total").complete ? "" : " known; total unavailable") + " · " + plural(late.length, "payment")) + "</span>";
                else if (next) text = '<span class="dcr-muted">' + esc("Payment " + fmt_date(next.date) + " · " + money(next.total)) + "</span>";
                else if (deal.loan.payments_unavailable) text = '<span class="dcr-muted">Payment details could not load</span>';
                else if (!data || data.funded === false) text = '<span class="dcr-muted">Not funded yet</span>';
                else text = '<span class="dcr-muted">Nothing scheduled</span>';
                return { href: request_href(deal.name), header: 1, cells: [status(stage.kind, stage.label), home_link(deal), request_number(deal.name), esc(M.homeStatus(deal)), esc(money(data ? data.outstanding_principal : null)), text, CHEVRON] };
            }));
        }
        return '<div class="dcr-page">' + page_head("Lending") + body + "</div>";
    }

    // ------------------------------------------------------------ Payments
    function deal_cell(name) {
        var deal = deal_by_name(name);
        return deal ? home_link(deal) : request_number(name);
    }

    function page_payments() {
        var ach = (state.data && state.data.ach) || {};
        var accounts = ach.accounts || [];
        var bank;
        if (accounts.length) {
            // A bank record on file is not evidence of a live provider link or of automatic debits.
            bank = table("Bank accounts on file", [{ label: "Bank", cls: "dcr-c-icon", hidden: true }, { label: "Account" }, { label: "Use" }, { label: "Status", cls: "dcr-nowrap" }], accounts.map(function (account) {
                var name = account.bank_name || "Bank account";
                var initials = name.split(/\s+/).map(function (word) { return word.charAt(0); }).join("").slice(0, 2).toUpperCase();
                return { header: 1, cells: ['<span class="dcr-bank-mark" aria-hidden="true">' + esc(initials) + "</span>", '<span class="dcr-strong">' + esc(name) + (account.last4 ? ' <span class="dcr-num">····' + esc(account.last4) + "</span>" : "") + "</span>",
                    '<span class="dcr-muted">' + (account.is_default ? "Default" : "") + "</span>", account.status === "Paused" ? status("draft", "Paused") : status("neutral", "On file")] };
            })) + '<p class="dcr-help">DCR manages payment setup. Contact DCR to confirm automatic payments.' + (support_url() ? " " + support_link("Contact DCR") : "") + "</p>";
        } else {
            bank = '<p class="dcr-note">No bank account is on file. Bank setup is not available in the portal yet; DCR will set up payments with you.' + (support_url() ? " " + support_link("Contact DCR") : "") + "</p>";
        }
        var body = section("Bank account", bank);

        var pay = M.paymentGroups(deals());
        if (!pay.loans) {
            body += section("Payments", '<p class="dcr-note">No payments yet. They appear here once a loan is funded.</p>');
        } else if (!pay.reported) {
            body += section("Payments", '<p class="dcr-note">' + (pay.unavailable.length ? "Payment details could not load. Refresh to try again." : "No payments yet. The schedule starts when a loan is funded.") + "</p>");
        } else {
            var total = function (sum) { return money(sum.amount) + (sum.complete ? "" : " known; total unavailable"); };
            var next = pay.upcoming[0];
            body += '<section class="dcr-section" aria-label="Payment summary">' + cells(3, [
                ["Past due", pay.pastDue.length ? total(pay.pastDueTotal) + " · " + plural(pay.pastDue.length, "payment") : pay.pastDueTotal.complete ? "Nothing past due" : "Total unavailable"],
                [pay.unavailable.length ? "Next recorded payment" : "Next payment", next ? fmt_date(next.date) + " · " + money(next.total) : pay.unavailable.length ? "Details unavailable" : "Nothing scheduled"],
                ["Paid", pay.paid.length ? plural(pay.paid.length, "payment") + (pay.truncated ? ", most recent shown" : "") : pay.unavailable.length ? "History unavailable" : "None yet"]]) +
                '<p class="dcr-help">' + esc(pay.asOf ? "As of " + fmt_date(pay.asOf) + ". " : "") + "Figures come from DCR's loan records." +
                (pay.unavailable.length ? " " + esc(plural(pay.unavailable.length, "loan")) + " could not load and " + (pay.unavailable.length === 1 ? "is" : "are") + " not included: " + esc(pay.unavailable.join(", ")) + "." : "") + "</p></section>";

            if (pay.pastDue.length) {
                var groups = [];
                pay.pastDueByDeal.forEach(function (group) {
                    var key = "late|" + group.deal;
                    var open = !!state.expanded[key];
                    groups.push({ cls: "dcr-group", header: 1, cells: [mark("action"), deal_cell(group.deal), request_number(group.deal),
                        '<span class="dcr-muted">' + esc(plural(group.rows.length, "payment") + " · oldest " + fmt_date(group.oldest)) + "</span>",
                        '<span class="dcr-strong">' + esc(money(group.amount) + (group.complete ? "" : " known; total unavailable")) + "</span>",
                        '<button type="button" class="dcr-btn-text" data-action="toggle" data-key="' + esc(key) + '" data-focus-key="toggle|' + esc(key) + '" aria-expanded="' + (open ? "true" : "false") + '" aria-label="' + esc((open ? "Hide" : "Show") + " past-due payments for " + group.deal) + '">' + (open ? "Hide" : "Show") + "</button>"] });
                    if (open) group.rows.forEach(function (row) {
                        groups.push({ cls: "dcr-sub", cells: ["", '<span class="dcr-muted">Due ' + esc(fmt_date(row.date)) + "</span>", "", '<span class="dcr-muted">' + esc(payment_components(row)) + "</span>", esc(money(row.total)), ""] });
                    });
                });
                body += section("Past due", table("Past-due payments by request", [{ label: "Past due", cls: "dcr-c-icon", hidden: true }, { label: "Home" }, { label: "Request", cls: "dcr-nowrap" }, { label: "Details" }, { label: "Amount", cls: "dcr-right dcr-nowrap" }, { label: "Rows", cls: "dcr-c-act", hidden: true }], groups),
                    esc(plural(pay.pastDue.length, "payment") + " · " + total(pay.pastDueTotal)));
            }

            var simple = function (caption, rows, key, kind, date_label, detail, amount) {
                var columns = [{ label: kind, cls: "dcr-c-icon", hidden: true }, { label: date_label, cls: "dcr-nowrap" }, { label: "Home" }, { label: "Request", cls: "dcr-nowrap" }, { label: "Details" }, { label: "Amount", cls: "dcr-right dcr-nowrap" }];
                return table(caption, columns, preview(rows, key).map(function (row) {
                    return { cells: [mark(kind === "Paid" ? "done" : "progress"), esc(fmt_date(row.date)), deal_cell(row.deal), request_number(row.deal), '<span class="dcr-muted">' + esc(detail(row)) + "</span>", esc(money(amount(row)))] };
                })) + (rows.length > PREVIEW_ROWS ? toggle_button(key, rows.length, "payment") : "");
            };
            body += section("Upcoming", pay.upcoming.length ? simple("Upcoming payments", pay.upcoming, "upcoming", "Scheduled", "Due", payment_components, function (row) { return row.total; }) : '<p class="dcr-note">' + (pay.unavailable.length ? "Some payment details could not load. Upcoming totals are unavailable." : "Nothing is scheduled right now.") + '</p>',
                pay.upcoming.length ? esc(plural(pay.upcoming.length, "payment")) : "");
            body += section("Paid", pay.paid.length ? simple("Paid payments", pay.paid, "paid", "Paid", "Paid", function (row) { return row.type || "Payment"; }, function (row) { return row.amount; }) : '<p class="dcr-note">' + (pay.unavailable.length ? "Some payment details could not load. Payment history is unavailable." : "No payments have been made yet.") + '</p>',
                pay.paid.length ? esc(plural(pay.paid.length, "payment") + (pay.truncated ? ", most recent shown" : "")) : "");
        }
        return '<div class="dcr-page">' + page_head("Payments") + body + "</div>";
    }

    // ------------------------------------------------------------ Settings
    function page_settings() {
        var data = state.data;
        var customer = data.customer || {};
        var factories = (data.factories || []).map(function (item) { return item.label || item.name; }).join(", ");
        var onboarding = data.onboarding_documents || [];
        var dealer = [["Dealer", customer.label || ""], ["Sign-in email", customer.email || ""], ["Assigned factories", factories || "None assigned yet"]];
        var body = section("Dealer", cells(3, dealer) + (support_url() ? '<p class="dcr-help">Something wrong here? ' + support_link("Contact DCR") + "</p>" : ""));

        var parts = M.partitionSignatures(signatures(), deals());
        if (parts.waiting.length) {
            body += section("Waiting for your signature", table("Documents waiting for your signature", [{ label: "File type", cls: "dcr-c-icon", hidden: true }, { label: "Document" }, { label: "For" }, { label: "Sent", cls: "dcr-nowrap dcr-muted" }, { label: "Actions", cls: "dcr-c-act", hidden: true }],
                parts.waiting.map(function (entry) {
                    var item = entry.signature;
                    var label = item.document_type + (entry.deal ? " for " + M.identity(entry.deal).primary : "");
                    return { header: 1, cells: [FILE_ICONS.pdf, '<span class="dcr-strong">' + esc(item.document_type) + "</span>", signature_scope(entry), esc(fmt_date(item.sent_date)), '<span class="dcr-actions">' + sign_button(item, label) + "</span>"] };
                })));
        }
        // History keeps every record; nothing is collapsed to "latest".
        var history = preview(parts.history, "signatures");
        body += section("Agreements and signatures", parts.history.length ? table("Agreement and signature history", [{ label: "File type", cls: "dcr-c-icon", hidden: true }, { label: "Document" }, { label: "For" }, { label: "Status", cls: "dcr-nowrap" }, { label: "Date", cls: "dcr-nowrap dcr-muted" }, { label: "Help", cls: "dcr-c-act", hidden: true }],
            history.map(function (entry) {
                var item = entry.signature;
                var help = item.status === "Declined" || item.status === "Voided" ? support_link("Contact DCR", "dcr-btn-text") : "";
                return { header: 1, cells: [FILE_ICONS.pdf, '<span class="dcr-strong">' + esc(item.document_type) + "</span>", signature_scope(entry), signature_status(item), esc(fmt_date(item.signed_date || item.sent_date)), '<span class="dcr-actions">' + help + "</span>"] };
            })) + (parts.history.length > PREVIEW_ROWS ? toggle_button("signatures", parts.history.length, "record") : "")
            : '<p class="dcr-note">' + (parts.waiting.length ? "No earlier records." : "No agreements have been sent yet.") + "</p>", parts.history.length ? esc(plural(parts.history.length, "record")) : "");

        body += section("Dealer documents", documents_table("Dealer documents", onboarding, "customer", customer.name, true), onboarding.some(function (item) { return !item.uploaded || item.can_download === false; }) ? esc(UPLOAD_NOTE) : "");
        return '<div class="dcr-page">' + page_head("Settings") + body + "</div>";
    }

    // ------------------------------------------------------------ loading and errors
    function page_loading() {
        var card = '<div class="dcr-card"><i style="width:96px"></i><i style="width:140px;height:16px"></i><i style="margin-top:auto;height:72px;border-radius:8px"></i></div>';
        return '<div class="dcr-page dcr-skeleton" role="status" aria-label="Loading your dashboard"><i style="width:220px;height:20px"></i><div class="dcr-cards">' + card + card + card + '</div><div class="dcr-note"><span class="dcr-spinner" aria-hidden="true"></span> Loading…</div></div>';
    }

    function page_error(message) {
        var no_access = /not linked|not active|more than one dealer|could not be found/i.test(message || "");
        if (no_access) {
            return '<div class="dcr-page">' + page_head("Dealer portal") + empty_state(ICONS.home, "No dealer access yet", "To set up your dealer access, contact DCR.",
                '<span class="dcr-empty-actions">' + support_link("Contact DCR", "dcr-btn-primary") + '<a class="dcr-btn" href="/logout">Sign out</a></span>') + "</div>";
        }
        return '<div class="dcr-page">' + page_head(greeting()) + '<div class="dcr-alert" role="alert"><span><span class="dcr-strong">We could not load your dashboard.</span> ' + esc(message || "") + '</span><button type="button" class="dcr-btn" data-action="retry">Try again</button></div></div>';
    }

    // ------------------------------------------------------------ routing and render
    function current_route() {
        var parts = window.location.hash.replace(/^#\/?/, "").split("/");
        return { name: parts[0] || "home", arg: parts.length > 1 ? decodeURIComponent(parts.slice(1).join("/")) : "" };
    }

    // reason "route": the dealer navigated, so focus moves to the new page heading.
    // reason "refresh": data or a control changed; focus returns to where it was.
    function render(reason) {
        var route = current_route();
        var active = route.name === "request" ? "home" : route.name;
        var keep = reason === "refresh" ? (state.focusKey || (document.activeElement && view.contains(document.activeElement) && document.activeElement.getAttribute("data-focus-key")) || "") : "";
        state.focusKey = "";
        root.querySelectorAll("[data-nav]").forEach(function (link) {
            var on = link.getAttribute("data-nav") === active;
            link.classList.toggle("is-active", on);
            if (on) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
        });
        var customer = (state.data && state.data.customer) || {};
        root.querySelectorAll("[data-customer-label]").forEach(function (node) { node.textContent = customer.label || "Dealer portal"; });

        var html;
        if (state.loading && !state.data) html = page_loading();
        else if (state.error && !state.data) html = page_error(state.error);
        else if (route.name === "request") html = page_request(route.arg);
        else if (route.name === "lending") html = page_lending();
        else if (route.name === "payments") html = page_payments();
        else if (route.name === "settings") html = page_settings();
        else html = page_home();
        view.innerHTML = html;

        var key = route.name + "/" + route.arg;
        if (key !== state.lastRoute) {
            state.lastRoute = key;
            main.scrollTop = 0;
        }
        var deal = route.name === "request" ? deal_by_name(route.arg) : null;
        document.title = (deal ? M.identity(deal).primary : (route.name === "request" && route.arg ? route.arg : active.charAt(0).toUpperCase() + active.slice(1))) + " · Dealer Portal";

        if (reason === "route") {
            var heading = view.querySelector("h1");
            if (heading) heading.focus({ preventScroll: true });
        } else if (keep) {
            var target = Array.prototype.filter.call(view.querySelectorAll("[data-focus-key]"), function (node) { return node.getAttribute("data-focus-key") === keep; })[0];
            if (target) target.focus({ preventScroll: true });
        }
    }

    async function reload() {
        state.loading = true;
        state.error = null;
        if (!state.data) render();
        try {
            state.data = await api("get_portal_context");
        } catch (error) {
            state.error = error.message;
            if (state.data) toast(error.message, true);
        }
        state.loading = false;
        render("refresh");
    }

    // ------------------------------------------------------------ events
    root.querySelectorAll("[data-icon]").forEach(function (node) {
        node.innerHTML = ICONS[node.getAttribute("data-icon")] || "";
    });

    root.addEventListener("click", async function (event) {
        var action = event.target.closest("[data-action]");
        if (!action) {
            // Pointer convenience only: the home name in each row is the real link.
            var row = event.target.closest("tr[data-href]");
            if (row && !event.target.closest("a, button, label, input")) window.location.hash = row.getAttribute("data-href");
            return;
        }
        var name = action.getAttribute("data-action");
        if (name === "retry") { state.data = null; await reload(); return; }
        // Safari does not focus a button on click, so the control to return to is recorded here.
        if (name === "filter") {
            state.filter = action.getAttribute("data-filter");
            state.focusKey = action.getAttribute("data-focus-key") || "";
            render("refresh");
            return;
        }
        if (name === "toggle") {
            var key = action.getAttribute("data-key");
            state.expanded[key] = !state.expanded[key];
            state.focusKey = action.getAttribute("data-focus-key") || "";
            render("refresh");
            return;
        }
        if (name === "sign") {
            action.disabled = true;
            try {
                var signing = await api("start_signature", { signature_request: action.getAttribute("data-signature") });
                if (signing && signing.url) window.location.href = signing.url;
                else { action.disabled = false; toast("That document is not ready to sign yet.", true); }
            } catch (error) { action.disabled = false; toast(error.message, true); }
            return;
        }
        if (name === "payoff") {
            action.disabled = true;
            try {
                await api("request_payoff_letter", { name: action.getAttribute("data-hbr") });
                toast("Request recorded for DCR.");
            } catch (error) { toast(error.message, true); }
            action.disabled = false;
        }
    });

    root.addEventListener("change", async function (event) {
        var input = event.target.closest("input[type=file][data-upload-target]");
        if (!input || !input.files || !input.files.length) return;
        var file = input.files[0];
        var label = input.closest(".dcr-upload");
        var allowed = UPLOAD_ACCEPT.split(",").some(function (ext) { return file.name.toLowerCase().endsWith(ext); });
        if (!allowed) { input.value = ""; toast("Upload a PDF, Word document, or image file.", true); return; }
        if (file.size > MAX_UPLOAD_BYTES) { input.value = ""; toast("Files must be 10 MB or smaller.", true); return; }
        var key = label ? label.getAttribute("data-focus-key") : "";
        if (label) { label.classList.add("is-busy"); label.childNodes[0].nodeValue = "Uploading…"; }
        try {
            await upload_file(input);
            toast("Document uploaded.");
            state.focusKey = key;
            await reload();
        } catch (error) {
            toast(error.message, true);
            if (label) { label.classList.remove("is-busy"); label.childNodes[0].nodeValue = "Try again"; }
        } finally {
            input.value = "";
        }
    });

    root.addEventListener("keydown", function (event) {
        if ((event.key === "Enter" || event.key === " ") && event.target.matches(".dcr-upload")) {
            event.preventDefault();
            var input = event.target.querySelector("input[type=file]");
            if (input) input.click();
        }
    });

    window.addEventListener("hashchange", function () { render("route"); });

    async function start() {
        var query = new URLSearchParams(window.location.search);
        var requested = query.get("request");
        var signed = query.get("signature") === "complete";
        var pendingSignature = query.get("signature") === "pending";
        if (requested) window.location.hash = "#/request/" + encodeURIComponent(requested);
        if ((requested || signed || pendingSignature) && window.history.replaceState) {
            window.history.replaceState(null, "", window.location.pathname + window.location.hash);
        }
        await reload();
        if (signed && state.data) toast("Signature received. Thank you.");
        if (pendingSignature && state.data) toast("Your signature is not complete yet. Your request is unchanged.");
    }
    start();
})();
