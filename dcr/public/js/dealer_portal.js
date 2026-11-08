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
    //   Submitted            staff reviewed the request; no loan approval implied
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
        if (deal.loan_stage === "Approved") return { label: "Loan approved", kind: "progress", group: "In progress" };
        if (deal.loan_stage === "Applied") return { label: "Loan applied", kind: "progress", group: "In progress" };
        return { label: "Submitted", kind: "done", group: "In progress" };
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

    function serialNumber(deal) {
        var serial = String(deal.home_serial_no || "").trim();
        return serial.replace(/\./g, "").toUpperCase() === "TBD" ? "" : serial;
    }

    function paymentDisplay(deal) {
        var data = summary(deal);
        if (data && data.funded !== false) {
            var upcoming = (data.upcoming || []).filter(function (row) { return row.due_status !== "Past due"; });
            upcoming.sort(function (a, b) { return String(a.date).localeCompare(String(b.date)); });
            return { label: "Next payment", amount: upcoming.length && isNumber(upcoming[0].total) ? upcoming[0].total : null };
        }
        if (deal.loan && deal.loan.payments_unavailable) return { label: "Next payment", amount: null };
        return { label: "Monthly payment", amount: deal.loan && deal.loan.monthly_payment };
    }

    function identity(deal) {
        var serial = serialNumber(deal) || "TBD";
        var buyer = deal.home_type === "Customer Sold" && deal.end_buyer_name ? deal.end_buyer_name : "–";
        return { primary: String(deal.name), secondary: buyer + " · Serial " + serial };
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
            (data.history || []).forEach(function (row) { if (row.is_payment !== false) out.paid.push(Object.assign({ deal: deal.name }, row)); });
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
        steps.push(open ? { label: "DCR submission", kind: "upcoming" } : { label: "Submitted", kind: "done" });
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
        lifecycle: lifecycle, lifecycleGroups: lifecycleGroups, loanStage: loanStage, homeStatus: homeStatus, identity: identity, serialNumber: serialNumber, paymentDisplay: paymentDisplay,
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
    var state = { data: null, error: null, loading: true, lastRoute: "", filter: "all", expanded: {}, focusKey: "", signFailed: {} };
    var refreshTimer = null;
    var loadGeneration = 0;
    var pendingLoads = 0;
    var pendingActions = 0;

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
        loans: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M3 22h18M6 18v-7M10 18v-7M14 18v-7M18 18v-7M12 2l9 5H3z"/></svg>',
        money: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2.8v18.4M16.6 8.2c-.6-1.6-2.3-2.6-4.5-2.6-2.7 0-4.7 1.4-4.7 3.4 0 4.6 9.5 2.2 9.5 6.9 0 2-2 3.5-4.8 3.5-2.4 0-4.2-1.1-4.9-2.8"></path></svg>'
    };
    var FILE_ICONS = {
        pdf: '<svg width="24" height="24" viewBox="0 0 40 40" fill="none" aria-hidden="true"><path fill="#D92D20" d="M4 4a4 4 0 0 1 4-4h16l12 12v24a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z"></path><path fill="#fff" d="m24 0 12 12h-8a4 4 0 0 1-4-4z" opacity=".3"></path><path fill="#fff" d="M11.75 32v-6.546h2.582q.744 0 1.268.285.524.281.8.783.277.498.277 1.15 0 .653-.28 1.151a1.94 1.94 0 0 1-.816.777q-.53.278-1.285.278H12.65v-1.11h1.423q.399 0 .658-.137a.9.9 0 0 0 .39-.386q.13-.25.13-.572 0-.326-.13-.57a.88.88 0 0 0-.39-.38q-.262-.137-.665-.137h-.933V32zm8.147 0h-2.32v-6.546h2.339q.987 0 1.7.394.712.39 1.096 1.122.387.731.387 1.75 0 1.024-.387 1.759-.384.735-1.102 1.128-.717.393-1.713.393m-.937-1.186h.879q.614 0 1.032-.217.422-.22.633-.68.214-.464.214-1.196 0-.726-.214-1.186a1.4 1.4 0 0 0-.63-.677q-.418-.218-1.032-.218h-.882zM24.124 32v-6.546h4.334v1.142h-2.95v1.56h2.662v1.14h-2.662V32z"></path></svg>',
        img: '<svg width="24" height="24" viewBox="0 0 40 40" fill="none" aria-hidden="true"><path fill="#7F56D9" d="M4 4a4 4 0 0 1 4-4h16l12 12v24a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z"></path><path fill="#fff" d="m24 0 12 12h-8a4 4 0 0 1-4-4z" opacity=".3"></path><path fill="#fff" d="M13.15 25.455V32h-1.383v-6.546zm1.14 0h1.706l1.802 4.397h.077l1.803-4.398h1.706V32h-1.342v-4.26h-.054l-1.694 4.228h-.914l-1.694-4.244h-.055V32H14.29zm12.575 2.115a1.4 1.4 0 0 0-.189-.412 1.28 1.28 0 0 0-.694-.502 1.7 1.7 0 0 0-.488-.067q-.502 0-.883.25a1.63 1.63 0 0 0-.588.725q-.21.472-.21 1.157 0 .684.207 1.163.209.48.588.732a1.6 1.6 0 0 0 .898.25q.47 0 .802-.167a1.2 1.2 0 0 0 .512-.476q.18-.306.179-.726l.281.042h-1.687v-1.042h2.739v.825q0 .863-.365 1.483a2.5 2.5 0 0 1-1.003.952q-.639.333-1.464.332-.921 0-1.617-.405a2.8 2.8 0 0 1-1.087-1.16q-.387-.755-.387-1.79 0-.796.23-1.42.234-.625.652-1.06.42-.434.975-.662.557-.227 1.205-.227.556 0 1.036.163.48.16.85.454.375.295.61.7.238.402.304.888z"></path></svg>',
        docx: '<svg width="24" height="24" viewBox="0 0 40 40" fill="none" aria-hidden="true"><path fill="#155EEF" d="M4 4a4 4 0 0 1 4-4h16l12 12v24a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z"></path><path fill="#fff" d="m24 0 12 12h-8a4 4 0 0 1-4-4z" opacity=".3"></path><path fill="#fff" d="M9.565 32h-2.32v-6.546h2.34q.986 0 1.7.394.712.39 1.096 1.122.386.731.386 1.75 0 1.024-.386 1.759-.383.735-1.103 1.128-.716.393-1.713.393m-.936-1.186h.878q.615 0 1.033-.217.422-.22.633-.68.213-.464.214-1.196 0-.726-.214-1.186a1.4 1.4 0 0 0-.63-.677q-.42-.218-1.032-.218h-.882zm11.178-2.087q0 1.07-.405 1.822-.403.75-1.1 1.147a3.1 3.1 0 0 1-1.56.393 3.1 3.1 0 0 1-1.566-.396 2.8 2.8 0 0 1-1.096-1.147q-.402-.75-.402-1.819 0-1.07.402-1.822.403-.75 1.096-1.144a3.1 3.1 0 0 1 1.566-.396q.867 0 1.56.396.697.393 1.1 1.145.405.75.405 1.821m-1.403 0q0-.693-.207-1.17a1.6 1.6 0 0 0-.579-.722 1.56 1.56 0 0 0-.875-.246q-.502 0-.876.246t-.582.723q-.204.476-.204 1.17 0 .692.204 1.169.208.477.582.722.373.246.875.246t.876-.246.579-.722q.207-.476.207-1.17m8.204-.98h-1.4a1.4 1.4 0 0 0-.157-.483 1.2 1.2 0 0 0-.303-.365 1.3 1.3 0 0 0-.429-.23 1.6 1.6 0 0 0-.52-.08q-.509 0-.886.253-.377.25-.585.728-.207.476-.207 1.157 0 .7.207 1.176.21.477.588.72.378.242.873.242.278 0 .514-.073.24-.074.425-.214.186-.144.307-.349.125-.204.173-.466l1.4.006q-.054.45-.272.87a2.6 2.6 0 0 1-.578.744q-.362.326-.863.518a3.2 3.2 0 0 1-1.128.189 3.1 3.1 0 0 1-1.566-.397 2.8 2.8 0 0 1-1.087-1.147q-.396-.75-.396-1.819 0-1.07.402-1.822.403-.75 1.093-1.144.69-.396 1.553-.396.57 0 1.055.16.49.16.866.466a2.4 2.4 0 0 1 .614.745q.24.44.307 1.01m2.15-2.293 1.32 2.231h.05l1.326-2.23h1.563l-1.997 3.272L33.062 32h-1.591l-1.343-2.234h-.05L28.734 32H27.15l2.048-3.273-2.01-3.273z"></path></svg>'
    };

    var MARKS = {
        draft: '<circle cx="7" cy="7" r="5.6" stroke="var(--dcr-muted)" stroke-width="1.4" stroke-dasharray="2.3 2.3"></circle>',
        progress: '<circle cx="7" cy="7" r="5.6" stroke="var(--dcr-blue)" stroke-width="1.4"></circle><path d="M7 3.6a3.4 3.4 0 0 1 0 6.8z" fill="var(--dcr-blue)"></path>',
        current: '<circle cx="7" cy="7" r="5.5" stroke="var(--dcr-blue)" stroke-width="1.4"></circle><circle cx="7" cy="7" r="2.6" fill="var(--dcr-blue)"></circle>',
        upcoming: '<circle cx="7" cy="7" r="5.5" stroke="var(--dcr-muted)" stroke-width="1.4"></circle>',
        action: '<circle cx="7" cy="7" r="5.5" stroke="var(--dcr-orange)" stroke-width="1.4"></circle><circle cx="7" cy="7" r="2.6" fill="var(--dcr-orange)"></circle>',
        done: '<circle cx="7" cy="7" r="6.3" fill="var(--dcr-green)"></circle><path d="M4.3 7.2l1.9 1.9 3.6-3.9" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"></path>',
        closed: '<circle cx="7" cy="7" r="6.3" fill="var(--dcr-muted)"></circle><path d="M4.3 7.2l1.9 1.9 3.6-3.9" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"></path>',
        cancelled: '<circle cx="7" cy="7" r="6.3" fill="var(--dcr-muted)"></circle><path d="M4.8 4.8l4.4 4.4M9.2 4.8L4.8 9.2" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round"></path>',
        neutral: '<circle cx="7" cy="7" r="5.6" stroke="var(--dcr-muted)" stroke-width="1.4"></circle><path d="M4.4 7h5.2" stroke="var(--dcr-muted)" stroke-width="1.4" stroke-linecap="round"></path>'
    };
    var CHEVRON = '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="var(--dcr-muted)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 2.5L8 6l-3.5 3.5"></path></svg>';
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
        return '<div class="dcr-table' + (columns.some(function (c) { return c.cls === "dcr-col-request"; }) ? " dcr-wide-table" : "") + '"><table><caption class="dcr-sr">' + esc(caption) + "</caption><thead><tr>" + head + "</tr></thead><tbody>" + body + "</tbody></table></div>";
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
        var action = method !== "get_portal_context";
        if (action) pendingActions += 1;
        try {
            var response = await fetch("/api/method/dcr.api.dealer_portal." + method, {
                method: "POST",
                headers: Object.assign({ "Content-Type": "application/json" }, csrf_headers()),
                credentials: "same-origin",
                body: JSON.stringify(payload || {}),
            });
            var data = await response.json().catch(function () { return {}; });
            if (!response.ok || data.exc) {
                var error = new Error(error_message(data));
                error.status = response.status;
                if (data.exc_type === "AuthenticationError") error.status = 401;
                if (data.exc_type === "PermissionError") error.status = 403;
                throw error;
            }
            return data.message;
        } finally { if (action) pendingActions -= 1; }
    }

    async function upload_file(input) {
        pendingActions += 1;
        try {
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
        } finally { pendingActions -= 1; }
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
    function documents_table(caption, items, target, name, can_upload, no_support) {
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
                (unavailable && !no_support ? (support_link("Contact DCR", "dcr-btn-text", "Contact DCR about " + title) || '<span class="dcr-muted">Contact DCR for help.</span>') : "") +
                (can_upload && (unavailable || (!item.uploaded && !item.complete)) ? upload_control("dcr-btn-row", target, name, type, unavailable ? "Replace file" : "Upload", title) : "");
            var row = [file_icon(item), '<span class="dcr-strong">' + esc(title) + "</span>", file];
            if (dated) row.push(esc(fmt_date(item.uploaded_on)));
            row.push('<span class="dcr-actions">' + actions + "</span>");
            return { cells: row, header: 1 };
        });
        return table(caption, columns, rows);
    }

    function signed_document_links(item) {
        return item.status === "Signed" && item.can_download === true
            ? document_links("signature", item.name, item.document_type, "signed " + item.document_type)
            : "";
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
        var failed = state.signFailed[item.name];
        // A packet DCR must re-issue cannot be signed by trying again, so no button is offered for it.
        if (failed && !failed.canRetry) return '<span class="dcr-muted">Cannot be opened</span>';
        return '<button type="button" class="dcr-btn-row" data-action="sign" data-signature="' + esc(item.name) + '" aria-label="' + esc((failed ? "Try signing again: " : "Sign ") + label) + '" data-focus-key="sign|' + esc(item.name) + '">' + (failed ? "Try again" : "Sign") + "</button>";
    }

    // Says only what is known: signing did not open, and nothing was signed. No support link.
    function sign_alert(items) {
        var failed = items.filter(function (item) { return state.signFailed[item.name]; });
        if (!failed.length) return "";
        return failed.map(function (item) {
            var deal = M.signatureDeal(item, deals());
            var what = item.document_type + (deal ? " for " + M.identity(deal).primary : "");
            var reason = state.signFailed[item.name].message;
            // The server's own explanation when it has one; otherwise only what is known.
            return '<div class="dcr-alert" role="alert" tabindex="-1" data-sign-error="' + esc(item.name) + '"><span><span class="dcr-strong">' + esc(what) + ".</span> " + esc(reason) + "</span></div>";
        }).join("");
    }

    function empty_state(icon, title, text, action) {
        return '<div class="dcr-empty"><span class="dcr-empty-tile">' + small_icon(icon, 20) + "</span><h3>" + esc(title) + "</h3><p>" + esc(text) + "</p>" + (action || "") + "</div>";
    }

    function new_request_button() {
        return '<a class="dcr-btn-primary" href="' + WEB_FORM + '/new">' + PLUS + "New build</a>";
    }

    function page_head(title, action) {
        return '<div class="dcr-page-head"><h1 tabindex="-1">' + esc(title) + "</h1>" + (action || "") + "</div>";
    }

    // ------------------------------------------------------------ Home
    function greeting() {
        var hour = new Date().getHours();
        return hour < 12 ? "Good morning" : (hour < 18 ? "Good afternoon" : "Good evening");
    }

    function dot(needed) { return needed ? '<i class="dcr-attention-dot" aria-label="Needs you"></i>' : ''; }

    function tabs(label, items, selected) {
        return '<nav class="dcr-tabs" aria-label="' + esc(label) + '">' + items.map(function (item) {
            return '<a class="dcr-tab" href="' + esc(item.href) + '"' + (item.key === selected ? ' aria-current="page"' : '') + '>' + esc(item.label) + dot(item.needs) + '</a>';
        }).join('') + '</nav>';
    }

    function buyer(deal) { return deal.home_type === 'Customer Sold' && deal.end_buyer_name ? deal.end_buyer_name : ''; }
    function optional(value) { return value ? esc(value) : '<span class="dcr-muted">–</span>'; }
    function serial(deal) { return M.serialNumber(deal) ? esc(M.serialNumber(deal)) : '<span class="dcr-muted">TBD</span>'; }
    function build_link(deal) { return '<a class="dcr-home-link" title="' + esc(deal.name) + '" href="' + request_href(deal.name) + '">' + esc(String(deal.name).replace(/^ACC-(?=HBR-)/, '')) + '</a><span class="dcr-phone-summary">' + optional(buyer(deal)) + ' · ' + serial(deal) + '</span>' + (next_step(deal).who === 'You' ? '<span class="dcr-phone-summary dcr-needs-you">You: ' + esc(next_step(deal).text) + '</span>' : ''); }

    function next_step(deal) {
        var need = M.needs(deal, signatures());
        if (need) return { who: 'You', text: need, kind: 'action' };
        var payments = M.summary(deal);
        if (payments && (payments.upcoming || []).some(function (r) { return r.due_status === 'Past due'; })) return { who: 'You', text: 'Contact DCR about payment', kind: 'action' };
        if (M.lifecycle(deal).group === 'Closed') return { who: '', text: '', kind: 'done' };
        var current = M.progressSteps(deal, signatures()).find(function (s) { return s.kind === 'current'; });
        return { who: current && current.note === 'With the factory' ? 'Factory' : 'DCR', text: current ? current.label : 'Review build', kind: 'progress' };
    }

    function build_columns() {
        return [{ label: 'Request', cls: 'dcr-col-request' }, { label: 'Buyer', cls: 'dcr-col-buyer' },
            { label: 'Serial', cls: 'dcr-col-serial' }, { label: 'Status', cls: 'dcr-col-status' },
            { label: 'Waiting on', cls: 'dcr-col-waiting' }, { label: 'Next step', cls: 'dcr-col-flex' },
            { label: 'Quoted', cls: 'dcr-col-amount dcr-right' }];
    }

    function builds_table(list) {
        if (!list.length) return '<p class="dcr-note">No builds in this view.</p>';
        return table('Builds', build_columns(), list.map(function (deal) {
            var stage = M.lifecycle(deal), next = next_step(deal);
            return { href: request_href(deal.name), header: 0, cells: [build_link(deal), optional(buyer(deal)), serial(deal),
                status(next.who === 'You' ? 'action' : stage.kind, stage.label),
                '<span class="' + (next.who === 'You' ? 'dcr-needs-you' : 'dcr-muted') + '">' + esc(next.who || '–') + '</span>',
                '<span class="' + (next.who === 'You' ? 'dcr-needs-you' : 'dcr-muted') + '">' + esc(next.text || '–') + '</span>', esc(money(deal.quoted_amount))] };
        }));
    }

    function setup_steps() {
        var data = state.data || {}, customer = data.customer || {}, rows = [];
        ['Dealer Agreement', 'MIFA'].forEach(function (type) {
            var records = signatures().filter(function (s) { return s.document_type === type; });
            var pending = records.find(function (s) { return s.actionable; });
            var signed = records.find(function (s) { return s.status === 'Signed'; });
            rows.push({ label: type, done: !pending && !!signed, date: signed && signed.signed_date,
                detail: pending ? 'Review and sign your ' + type : signed ? 'Signed' : 'DCR will prepare your ' + type,
                kind: pending ? 'action' : signed ? 'done' : 'progress',
                action: pending ? sign_button(pending, type) : signed ? signed_document_links(signed) : '' });
        });
        (data.onboarding_documents || []).forEach(function (item) {
            var done = M.canDownload(item);
            rows.push({ label: item.label, done: done, date: item.uploaded_on, kind: done ? 'done' : 'action',
                detail: done ? item.file_name || 'File uploaded' : 'PDF, Word or image, up to 10 MB',
                action: done ? document_links('customer', customer.name, item.fieldname, item.label) : upload_control('dcr-btn-row', 'customer', customer.name, item.fieldname, 'Upload', item.label) });
        });
        var ach = data.ach || {}, account = (ach.accounts || [])[0];
        rows.push({ label: 'Bank account', done: !!account, kind: account ? 'done' : ach.available ? 'action' : 'progress',
            detail: account ? (account.bank_name || 'Bank account') + ' ····' + (account.last4 || '') : 'Connect an account for payments',
            action: !account && ach.available ? '<button class="dcr-btn-row" data-action="connect-bank">Connect</button>' : '' });
        var factories = data.factories || [];
        rows.push({ label: 'Factory assignment', done: !!factories.length, kind: factories.length ? 'done' : 'progress',
            detail: factories.length ? factories.map(function (f) { return f.label || f.name; }).join(', ') : 'DCR will assign your factory', action: '' });
        return rows;
    }

    function setup_table(selected) {
        var steps = setup_steps(), done = selected === 'done';
        return tabs('Account setup', [{ key: 'todo', label: 'To do', href: '#/home/todo', needs: steps.some(function (r) { return !r.done && r.kind === 'action'; }) },
            { key: 'done', label: 'Done', href: '#/home/done' }], done ? 'done' : 'todo') +
            table('Account setup', [{ label: 'Step', cls: 'dcr-col-step' }, { label: 'Details' }, { label: done ? 'Date' : 'Status', cls: 'dcr-col-status' }, { label: 'Action', hidden: true, cls: 'dcr-c-act' }],
                steps.filter(function (r) { return r.done === done; }).map(function (r) { return { header: 0, cells: [esc(r.label), '<span class="dcr-muted">' + esc(r.detail) + '</span>',
                    done ? esc(fmt_date(r.date) || '–') : status(r.kind, r.kind === 'action' ? 'Needs you' : 'With DCR'), '<span class="dcr-actions">' + r.action + '</span>'] }; }));
    }

    function line_chart(label, amount, series, projection) {
        var points = (series || []).filter(function (p) { return p.date && M.isNumber(p.amount); });
        var future = projection || [];
        var metric = '<div class="dcr-chart-label">' + esc(label) + '</div><div class="dcr-chart-value">' + esc(money(amount)) + '</div>';
        if (!points.length || !M.isNumber(amount) || Math.abs(Number(points[points.length - 1].amount) - Number(amount)) > .02) {
            return '<section class="dcr-chart" aria-label="' + esc(label) + '">' + metric + '<p class="dcr-chart-empty">' + (M.isNumber(amount) && Number(amount) === 0 ? 'No payments yet.' : 'Historical chart is not available.') + '</p></section>';
        }
        var all = points.concat(future), values = all.map(function (p) { return Number(p.amount); });
        var max = Math.max.apply(null, values.concat([1])), min = Math.min.apply(null, values.concat([0]));
        var begin = parse_date(all[0].date).getTime(), end = parse_date(all[all.length - 1].date).getTime();
        function position(p) { return [((parse_date(p.date).getTime() - begin) / Math.max(end - begin, 1) * 600).toFixed(2), (126 - (Number(p.amount) - min) / Math.max(max - min, 1) * 110).toFixed(2)]; }
        var actual = points.map(position), d = actual.map(function (p, i) { return (i ? 'L' : 'M') + p.join(' '); }).join(' ');
        var projected = future.length ? [points[points.length - 1]].concat(future).map(position) : [];
        var id = 'dcr-chart-' + label.replace(/[^a-z]/gi, '').toLowerCase();
        var svg = '<svg class="dcr-line-chart" viewBox="0 0 600 142" preserveAspectRatio="none" role="img" aria-label="' + esc(label + ' over time. ' + (future.length ? 'Dashed line shows scheduled projection.' : 'Posted transactions.')) + '"><defs><linearGradient id="' + id + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="currentColor" stop-opacity=".08"/><stop offset="100%" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs>' +
            '<path d="' + d + ' L' + actual[actual.length - 1][0] + ' 142 L' + actual[0][0] + ' 142Z" fill="url(#' + id + ')"/>' +
            '<path d="' + d + '" fill="none" stroke="currentColor" stroke-width="1.5" vector-effect="non-scaling-stroke"/>' +
            (projected.length ? '<polyline points="' + projected.map(function (p) { return p.join(','); }).join(' ') + '" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>' : '') +
            '<circle cx="' + actual[actual.length - 1][0] + '" cy="' + actual[actual.length - 1][1] + '" r="2.5" fill="currentColor"/></svg>';
        var sampled = all.filter(function (_, i) { return all.length <= 6 || i === 0 || i === all.length - 1 || i % Math.ceil(all.length / 5) === 0; });
        return '<section class="dcr-chart" aria-label="' + esc(label) + '">' + metric + svg + '<div class="dcr-chart-axis">' + sampled.map(function (p) { return '<span>' + esc(fmt_date(p.date)) + '</span>'; }).join('') + '</div>' +
            '<details class="dcr-chart-data"><summary>View chart values</summary>' + table(label + ' values', [{ label: 'Date' }, { label: 'Amount', cls: 'dcr-right' }], all.map(function (p) { return { cells: [esc(fmt_date(p.date)), esc(money(p.amount))] }; })) + '</details></section>';
    }

    function side_payments(title, rows) {
        var total = M.sumAmounts(rows, 'total');
        var shown = rows.length > 3 ? rows.slice(0, 2) : rows;
        var body = table(title, [{ label: 'Request', cls: 'dcr-side-request' }, { label: 'Buyer' }, { label: 'Due', cls: 'dcr-side-due' }, { label: 'Amount', cls: 'dcr-right dcr-side-amount' }], shown.map(function (r) {
            var deal = deal_by_name(r.deal);
            return { header: 0, cells: [deal ? build_link(deal) : esc(r.deal), deal ? optional(buyer(deal)) : optional(''), esc(fmt_date(r.date)), esc(money(r.total))] };
        }));
        if (rows.length > 3) body += '<a class="dcr-overflow-row" href="#/payments/schedule">' + esc((rows.length - 2) + ' more · next due ' + fmt_date(rows[2].date)) + '<span>View all →</span></a>';
        if (!rows.length) body = '<p class="dcr-muted">Nothing due.</p>';
        return '<section class="dcr-payment-side"><h2>' + esc(title) + '</h2><div class="dcr-chart-value dcr-side-total">' + esc(total.complete ? money(total.amount) : 'Unavailable') + '</div>' + body + '</section>';
    }

    function page_home(arg) {
        var unfinished = setup_steps().some(function (r) { return !r.done; });
        if (unfinished || arg === 'done' || arg === 'todo') return '<div class="dcr-page">' + page_head('Set up your account', new_request_button()) +
            '<p class="dcr-subtitle">Complete these steps to get your account ready.</p>' + setup_table(arg) + '</div>';
        var finance = state.data.finance || {}, pay = M.paymentGroups(deals());
        var hasFunded = finance.funded_loans > 0 || deals().some(function (d) { return M.summary(d) && M.summary(d).funded; });
        var overview = hasFunded ? '<div class="dcr-overview-grid">' + line_chart('Outstanding', finance.outstanding, finance.principal_series) + side_payments('Upcoming payments', pay.upcoming.filter(function (r, i, rows) { return rows.findIndex(function (item) { return item.deal === r.deal; }) === i; })) + '</div>' : '';
        return '<div class="dcr-page">' + page_head(greeting(), new_request_button()) + overview + section('Builds', builds_table(deals().filter(function (d) { return M.lifecycle(d).group !== 'Closed'; }))) + '</div>';
    }

    function page_builds(arg) {
        var selected = ['you', 'dcr', 'closed'].indexOf(arg) >= 0 ? arg : 'all';
        var list = deals().filter(function (d) {
            var closed = M.lifecycle(d).group === 'Closed', next = next_step(d);
            return selected === 'closed' ? closed : selected === 'all' ? true : !closed && (selected === 'you' ? next.who === 'You' : next.who === 'DCR');
        });
        return '<div class="dcr-page">' + page_head('Builds', new_request_button()) + tabs('Build views', [
            { key: 'all', label: 'All', href: '#/builds' }, { key: 'you', label: 'Waiting on you', href: '#/builds/you', needs: deals().some(function (d) { return next_step(d).who === 'You'; }) },
            { key: 'dcr', label: 'Waiting on DCR', href: '#/builds/dcr' }, { key: 'closed', label: 'Closed and cancelled', href: '#/builds/closed' }], selected) + builds_table(list) + '</div>';
    }

    function progress_list(deal) {
        return '<ol class="dcr-steps">' + M.progressSteps(deal, signatures()).map(function (step) {
            var note = step.noteIsDate ? fmt_date(step.note) : step.note;
            return '<li class="is-' + step.kind + '"><span class="dcr-step-mark">' + mark(step.kind) + '</span><span class="dcr-step-body"><span>' + esc(step.label) + '</span>' + (note ? '<span class="dcr-small">' + esc(note) + '</span>' : '') + '</span></li>';
        }).join('') + '</ol>';
    }

    function field(deal, name) {
        var value = deal[name];
        if ((value === null || value === undefined || value === '') && deal.editable) value = deal.editable[name];
        return value === null || value === undefined ? '' : value;
    }

    function build_details(deal) {
        var address = ['delivery_address', 'address_line_2', 'city', 'state', 'zip'].map(function (n) { return field(deal, n); }).filter(Boolean).join(', ');
        var details = [['Factory', deal.factory && deal.factory.label || '–'], ['Floorplan', deal.floor_plan || '–'], ['Serial number', M.serialNumber(deal) || 'TBD'],
            ['Factory quote', deal.quote_no || '–'], ['Quoted amount', money(deal.quoted_amount)], ['Home type', deal.home_type || '–'],
            ['Deal type', deal.financing_type || '–'], ['Property', deal.property_type || '–']];
        if (address) details.push(['Delivery address', address]);
        if (deal.offline_date) details.push(['Off Line Date', fmt_date(deal.offline_date)]);
        if (deal.property_type === 'Park') details.push(['Community', [field(deal, 'community_name'), field(deal, 'space_number')].filter(Boolean).join(' · ')]);
        if (deal.home_type === 'Customer Sold') {
            details.push(['Buyer', buyer(deal) || '–']);
            if (M.isNumber(field(deal, 'selling_price'))) details.push(['Selling price', money(field(deal, 'selling_price'))]);
            if (M.isNumber(deal.installed_value)) details.push(['Installed value', money(deal.installed_value)]);
        }
        return section('Build details', cells(2, details), M.canEdit(deal) ? '<a class="dcr-btn" href="' + WEB_FORM + '/' + encodeURIComponent(deal.name) + '/edit">Edit</a>' : 'Read only');
    }

    function build_documents(deal) {
        var items = M.documents(deal), signed = M.dealSignatures(deal, signatures());
        var body = section('Documents', items.length ? documents_table('Documents for ' + deal.name, items, 'hbr', deal.name, M.canEdit(deal)) : '<p class="dcr-muted">No documents are required for this build.</p>');
        if (signed.length) body += section('Signatures', sign_alert(signed) + table('Signatures for ' + deal.name, [{ label: 'Document' }, { label: 'Status', cls: 'dcr-col-status' }, { label: 'Date', cls: 'dcr-col-date' }, { label: 'Action', hidden: true, cls: 'dcr-c-act' }], signed.map(function (s) {
            return { header: 0, cells: [esc(s.document_type), signature_status(s), esc(fmt_date(s.signed_date || s.sent_date)), '<span class="dcr-actions">' + (s.actionable ? sign_button(s, s.document_type) : signed_document_links(s)) + '</span>'] };
        })));
        return body;
    }

    function build_payments(deal) {
        var data = M.summary(deal);
        if (!data) return '<p class="dcr-note">' + (deal.loan && deal.loan.payments_unavailable ? 'Payment details could not load.' : 'The schedule starts when the loan is funded.') + '</p>';
        var rows = (data.upcoming || []).map(function (r) { return { date: r.date, amount: r.total, label: r.due_status, kind: r.due_status === 'Past due' ? 'action' : 'progress' }; })
            .concat((data.history || []).map(function (r) { return { date: r.date, amount: r.amount, label: r.is_payment === false ? 'Recorded' : 'Paid', kind: 'done' }; }));
        rows.sort(function (a, b) { return String(a.date).localeCompare(String(b.date)); });
        return rows.length ? table('Build payments', [{ label: 'Due', cls: 'dcr-col-date' }, { label: 'Status' }, { label: 'Amount', cls: 'dcr-col-amount dcr-right' }], rows.map(function (r) { return { cells: [esc(fmt_date(r.date)), status(r.kind, r.label || 'Scheduled'), esc(money(r.amount))] }; })) : '<p class="dcr-note">No payments yet.</p>';
    }

    function build_overview(deal) {
        var data = M.summary(deal), body = '';
        if (data && data.funded) {
            var outlook = M.principalOutlook([deal], parse_date(data.as_of) || new Date());
            body += line_chart('Outstanding', data.outstanding_principal, data.principal_series, outlook.months.map(function (m) { return { date: m.end, amount: m.total }; }));
        }
        var rows = M.progressSteps(deal, signatures()).filter(function (s) { return s.kind === 'action' || s.kind === 'current'; }).map(function (s) {
            var action = s.signature ? sign_button(s.signature, s.signature.document_type) : s.upload ? upload_control('dcr-btn-row', 'hbr', deal.name, s.upload.document_type, s.replace ? 'Replace' : 'Upload', s.upload.document_type) : '';
            return { cells: [esc(s.kind === 'action' ? 'You' : s.note === 'With the factory' ? 'Factory' : 'DCR'), esc(s.label), '<span class="dcr-muted">–</span>', action] };
        });
        if (M.canEdit(deal)) rows.push({ cells: ['You', 'Review build details', '–', '<a class="dcr-btn-row" href="' + WEB_FORM + '/' + encodeURIComponent(deal.name) + '/edit">Edit</a>'] });
        return body + section('Next steps', rows.length ? table('Next steps', [{ label: 'Who', cls: 'dcr-col-waiting' }, { label: 'Step' }, { label: 'Due', cls: 'dcr-col-date' }, { label: 'Action', hidden: true, cls: 'dcr-c-act' }], rows) : '<p class="dcr-muted">Nothing needed from you right now.</p>') + sign_alert(M.dealSignatures(deal, signatures()));
    }

    function page_request(name, tab) {
        var deal = deal_by_name(name);
        if (!deal) return '<div class="dcr-page">' + page_head(name || 'Build') + empty_state(ICONS.home, 'This build is not available', 'It may belong to another dealer account.', '<a class="dcr-btn" href="#/builds">Back to Builds</a>') + '</div>';
        var selected = ['details', 'documents', 'payments'].indexOf(tab) >= 0 ? tab : 'overview';
        var base = request_href(name), pay = M.summary(deal), needsDocs = M.needs(deal, signatures());
        var nav = tabs('Build tabs', [{ key: 'overview', label: 'Overview', href: base }, { key: 'details', label: 'Details', href: base + '/details' },
            { key: 'documents', label: 'Documents', href: base + '/documents', needs: !!needsDocs }, { key: 'payments', label: 'Payments', href: base + '/payments', needs: pay && pay.upcoming.some(function (r) { return r.due_status === 'Past due'; }) }], selected);
        var content = selected === 'details' ? build_details(deal) : selected === 'documents' ? build_documents(deal) : selected === 'payments' ? build_payments(deal) : build_overview(deal);
        var payoff = deal.loan && deal.loan.payoff && deal.loan.payoff.can_request;
        var aside = '<aside class="dcr-build-aside"><section><h2>Progress</h2>' + progress_list(deal) + '</section><section><h2>Payoff quote</h2><p class="dcr-muted">' + (payoff ? 'Request a reviewed payoff letter from DCR.' : 'Available for an open, funded loan.') + '</p>' +
            (payoff ? '<button class="dcr-btn" data-action="payoff" data-hbr="' + esc(name) + '">Request payoff letter</button>' : '') + '</section></aside>';
        return '<div class="dcr-page dcr-build-page"><header><nav class="dcr-crumbs" aria-label="Breadcrumb"><a href="#/builds">Builds</a>' + CHEVRON + '<span>' + esc(name) + '</span></nav>' + page_head(name) +
            '<p class="dcr-subtitle">' + optional(buyer(deal)) + ' · Serial ' + serial(deal) + '</p></header><div class="dcr-build-layout"><div class="dcr-record-main">' + nav + '<div class="dcr-build-content">' + content + '</div></div>' + aside + '</div></div>';
    }

    function page_lending(arg) {
        var selected = arg === 'repaid' ? 'repaid' : 'active', finance = state.data.finance || {};
        var list = deals().filter(function (d) { return M.hasLoan(d) && !M.isCancelled(d) && (selected === 'repaid' ? d.loan_stage === 'Closed' : d.loan_stage !== 'Closed'); });
        var credit = section('Available credit', cells(3, [['Limit', M.isNumber(finance.credit_limit) ? money(finance.credit_limit) : 'Not available'], ['Outstanding', money(finance.outstanding)], ['Available', M.isNumber(finance.available_credit) ? money(finance.available_credit) : 'Not available']]));
        return '<div class="dcr-page">' + page_head('Loans') + '<div class="dcr-overview-grid">' + line_chart('Outstanding', finance.outstanding, finance.principal_series) + credit + '</div>' +
            tabs('Loan views', [{ key: 'active', label: 'Active', href: '#/loans' }, { key: 'repaid', label: 'Repaid', href: '#/loans/repaid' }], selected) +
            (list.length ? table('Loans', [{ label: 'Request', cls: 'dcr-col-request' }, { label: 'Buyer', cls: 'dcr-col-buyer' }, { label: 'Serial', cls: 'dcr-col-serial' }, { label: 'Funded', cls: 'dcr-col-date' }, { label: 'Rate', cls: 'dcr-col-rate' }, { label: 'Status' }, { label: 'Principal', cls: 'dcr-col-amount dcr-right' }], list.map(function (d) {
                var s = M.summary(d), stage = M.loanStage(d);
                return { href: request_href(d.name), header: 0, cells: [build_link(d), optional(buyer(d)), serial(d), esc(fmt_date(s && s.funded_on) || '–'), esc(M.isNumber(d.loan.interest_rate) ? Number(d.loan.interest_rate) + '%' : '–'), status(stage.kind, stage.label), esc(money(s && s.outstanding_principal))] };
            })) : '<p class="dcr-note">No ' + (selected === 'repaid' ? 'repaid loans.' : 'loans yet.') + '</p>') + '</div>';
    }

    function payment_table(rows, pastDue) {
        if (!rows.length) return '<p class="dcr-note">' + (pastDue ? 'Nothing past due.' : 'No payments scheduled.') + '</p>';
        var columns = [{ label: 'Request', cls: 'dcr-col-request' }, { label: 'Buyer', cls: 'dcr-col-buyer' }, { label: 'Serial', cls: 'dcr-col-serial' },
            { label: 'Due date', cls: 'dcr-col-date' }, { label: 'Status' }, { label: 'Amount', cls: 'dcr-col-amount dcr-right' }];
        if (pastDue) columns.push({ label: 'Action', hidden: true, cls: 'dcr-c-act' });
        return table(pastDue ? 'Past due' : 'Payment schedule', columns, rows.map(function (r) {
            var deal = deal_by_name(r.deal), late = r.due_status === 'Past due';
            var values = [(deal ? build_link(deal) : esc(r.deal)) + '<span class="dcr-phone-summary">Due ' + esc(fmt_date(r.date)) + ' · ' + esc(late ? 'Past due' : 'Scheduled') + '</span>', deal ? optional(buyer(deal)) : optional(''), deal ? serial(deal) : optional(''), esc(fmt_date(r.date)), status(late ? 'action' : 'progress', late ? 'Past due' : 'Scheduled'), esc(money(r.total))];
            if (pastDue) values.push(support_link('Contact DCR', 'dcr-btn-row', 'Contact DCR about payment for ' + r.deal) || '<span class="dcr-muted">Contact DCR</span>');
            return { header: 0, cells: values };
        }));
    }

    function banking_panel() {
        var ach = state.data.ach || {}, account = (ach.accounts || [])[0];
        var action = ach.available ? '<button class="dcr-btn-row" data-action="connect-bank">' + (account ? 'Update' : 'Connect') + '</button>' : support_link('Contact DCR', 'dcr-btn-row');
        return table('Payment setup', [{ label: 'Item', cls: 'dcr-col-step' }, { label: 'Details' }, { label: 'Status', cls: 'dcr-col-status' }, { label: 'Action', hidden: true, cls: 'dcr-c-act' }], [
            { cells: ['Bank account', account ? esc((account.bank_name || 'Bank account') + ' ····' + (account.last4 || '')) : '<span class="dcr-muted">Not connected</span>', status(account ? 'done' : 'action', account ? 'On file' : 'Needs you'), action] },
            { cells: ['Automatic payments', esc(ach.automatic_payments || 'Not set up'), status('draft', ach.automatic_payments === 'Not set up' || !ach.automatic_payments ? 'Off' : 'With DCR'), support_link('Contact DCR', 'dcr-btn-row')] }]);
    }

    function page_payments(arg) {
        var pay = M.paymentGroups(deals()), selected = arg === 'bank' ? 'bank' : arg === 'schedule' || arg === 'upcoming' ? 'schedule' : 'overview';
        var nav = tabs('Payment views', [{ key: 'overview', label: 'Overview', href: '#/payments' }, { key: 'schedule', label: 'Schedule', href: '#/payments/schedule', needs: !!pay.pastDue.length }, { key: 'bank', label: 'Bank', href: '#/payments/bank' }], selected);
        var content;
        if (selected === 'bank') content = banking_panel();
        else if (selected === 'schedule') content = payment_table(pay.pastDue.concat(pay.upcoming));
        else {
            var finance = state.data.finance || {}, month = (pay.asOf || new Date().toISOString()).slice(0, 7);
            content = '<div class="dcr-overview-grid">' + line_chart('Paid to date', finance.paid_total, finance.paid_series) + side_payments('Due this month', pay.pastDue.concat(pay.upcoming).filter(function (r) { return String(r.date).slice(0, 7) === month; })) + '</div>' + section('Past due', payment_table(pay.pastDue, true));
        }
        if (pay.unavailable.length) content = '<p class="dcr-alert" role="alert">Some payment details could not load. Totals and schedules may be incomplete.</p>' + content;
        return '<div class="dcr-page">' + page_head('Payments') + nav + content + '</div>';
    }

    function page_settings() {
        var data = state.data;
        var customer = data.customer || {};
        var factories = (data.factories || []).map(function (item) { return item.label || item.name; }).join(", ");
        var onboarding = data.onboarding_documents || [];
        var dealer = [["Dealer", customer.label || ""], ["Sign-in email", customer.email || ""], ["Assigned factories", factories || "None assigned yet"]];
        var body = section("Dealer", cells(3, dealer));

        var parts = M.partitionSignatures(signatures(), deals());
        if (parts.waiting.length) {
            body += section("Waiting for your signature", sign_alert(parts.waiting.map(function (entry) { return entry.signature; })) + table("Documents waiting for your signature", [{ label: "File type", cls: "dcr-c-icon", hidden: true }, { label: "Document" }, { label: "For" }, { label: "Sent", cls: "dcr-nowrap dcr-muted" }, { label: "Actions", cls: "dcr-c-act", hidden: true }],
                parts.waiting.map(function (entry) {
                    var item = entry.signature;
                    var label = item.document_type + (entry.deal ? " for " + M.identity(entry.deal).primary : "");
                    return { header: 1, cells: [FILE_ICONS.pdf, '<span class="dcr-strong">' + esc(item.document_type) + "</span>", signature_scope(entry), esc(fmt_date(item.sent_date)), '<span class="dcr-actions">' + sign_button(item, label) + "</span>"] };
                })));
        }
        // History keeps every record; nothing is collapsed to "latest".
        var history = preview(parts.history, "signatures");
        body += section("Agreements and signatures", parts.history.length ? table("Agreement and signature history", [{ label: "File type", cls: "dcr-c-icon", hidden: true }, { label: "Document" }, { label: "For" }, { label: "Status", cls: "dcr-nowrap" }, { label: "Date", cls: "dcr-nowrap dcr-muted" }, { label: "Actions", cls: "dcr-c-act", hidden: true }],
            history.map(function (entry) {
                var item = entry.signature;
                return { header: 1, cells: [FILE_ICONS.pdf, '<span class="dcr-strong">' + esc(item.document_type) + "</span>", signature_scope(entry), signature_status(item), esc(fmt_date(item.signed_date || item.sent_date)), '<span class="dcr-actions">' + signed_document_links(item) + "</span>"] };
            })) + (parts.history.length > PREVIEW_ROWS ? toggle_button("signatures", parts.history.length, "record") : "")
            : '<p class="dcr-note">' + (parts.waiting.length ? "No earlier records." : "No agreements have been sent yet.") + "</p>", parts.history.length ? esc(plural(parts.history.length, "record")) : "");

        body += section("Dealer documents", documents_table("Dealer documents", onboarding, "customer", customer.name, true, true), onboarding.some(function (item) { return !item.uploaded || item.can_download === false; }) ? esc(UPLOAD_NOTE) : "");
        return '<div class="dcr-page">' + page_head("Settings", '<a class="dcr-btn-text dcr-signout" href="/logout">Sign out</a>') + body + "</div>";
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
        return { name: parts[0] || "home", arg: parts[1] ? decodeURIComponent(parts[1]) : "", tab: parts[2] || "" };
    }

    // reason "route": the dealer navigated, so focus moves to the new page heading.
    // reason "refresh": data or a control changed; focus returns to where it was.
    function render(reason) {
        var scrollTop = main.scrollTop;
        var route = current_route();
        var active = route.name === "request" ? "builds" : route.name === "lending" ? "loans" : route.name;
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
        else if (route.name === "request") html = page_request(route.arg, route.tab);
        else if (route.name === "builds") html = page_builds(route.arg);
        else if (route.name === "loans" || route.name === "lending") html = page_lending(route.arg);
        else if (route.name === "payments") html = page_payments(route.arg);
        else if (route.name === "settings") html = page_settings();
        else html = page_home(route.arg);
        view.innerHTML = html;

        var key = route.name + "/" + route.arg + "/" + route.tab;
        if (key !== state.lastRoute) {
            state.lastRoute = key;
            main.scrollTop = 0;
        } else if (reason === "refresh") {
            main.scrollTop = scrollTop;
        }
        var deal = route.name === "request" ? deal_by_name(route.arg) : null;
        document.title = (deal ? M.identity(deal).primary : (route.name === "request" && route.arg ? route.arg : active.charAt(0).toUpperCase() + active.slice(1))) + " · Dealer Portal";

        var same_page = reason === "route" && (route.name === "payments" || route.name === "request") && state.lastPage === route.name;
        state.lastPage = route.name;
        if (same_page) {
            var tab = view.querySelector('.dcr-tab[aria-current="page"]');
            if (tab) tab.focus({ preventScroll: true });
        } else if (reason === "route") {
            var heading = view.querySelector("h1");
            if (heading) heading.focus({ preventScroll: true });
        } else if (keep) {
            var target = Array.prototype.filter.call(view.querySelectorAll("[data-focus-key]"), function (node) { return node.getAttribute("data-focus-key") === keep; })[0];
            if (target) target.focus({ preventScroll: true });
            else {
                var refreshedHeading = view.querySelector("h1");
                if (refreshedHeading) refreshedHeading.focus({ preventScroll: true });
            }
        }
    }

    function choosing_file() {
        var active = document.activeElement;
        return active && active.closest && !!active.closest(".dcr-upload");
    }

    async function reload(background) {
        if (background && (!state.data || document.hidden || pendingLoads || pendingActions || choosing_file())) return;
        var generation = ++loadGeneration;
        pendingLoads += 1;
        var changed = false;
        state.loading = true;
        state.error = null;
        if (!state.data) render();
        try {
            var data = await api("get_portal_context");
            if (generation !== loadGeneration || (background && (pendingActions || choosing_file()))) return;
            if (!data || !data.customer || !Array.isArray(data.deals)) throw new Error("Your dashboard could not refresh. Please try again.");
            changed = JSON.stringify(state.data) !== JSON.stringify(data);
            state.data = data;
        } catch (error) {
            if (generation !== loadGeneration) return;
            state.error = error.message;
            if (error.status === 401 || error.status === 403) { state.data = null; changed = true; }
            else if (state.data && !background) toast(error.message, true);
        } finally {
            pendingLoads -= 1;
            state.loading = pendingLoads > 0;
        }
        if (generation === loadGeneration && (!background || changed)) render("refresh");
    }

    function start_refresh() {
        if (refreshTimer === null) refreshTimer = setInterval(function () { reload(true); }, 10000);
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
            var signatureName = action.getAttribute("data-signature");
            action.disabled = true;
            var failure;
            try {
                var signing = await api("start_signature", { signature_request: signatureName });
                if (signing && signing.url) { delete state.signFailed[signatureName]; window.location.href = signing.url; return; }
                failure = { message: signing && signing.message || "This signing session could not be opened. Please try again later.", canRetry: !(signing && signing.unavailable) };
            } catch (error) {
                failure = { message: error.message && error.message !== "The request could not be completed." ? error.message : "This signing session could not be opened. Please try again later.", canRetry: true };
            }
            state.signFailed[signatureName] = failure;
            state.focusKey = failure.canRetry ? action.getAttribute("data-focus-key") || "" : "";
            render("refresh");
            if (!failure.canRetry) {
                var alert = Array.from(view.querySelectorAll("[data-sign-error]")).find(function (node) { return node.getAttribute("data-sign-error") === signatureName; });
                if (alert) alert.focus({ preventScroll: true });
            }
            return;
        }
        if (name === "connect-bank") {
            action.disabled = true;
            try {
                var setup = await api("get_ach_setup_url");
                var setupUrl = setup && safe_url(setup.url);
                if (setupUrl) { window.location.href = setupUrl; return; }
                toast("Bank connection is not available. Contact DCR.", true);
            } catch (error) { toast(error.message, true); }
            action.disabled = false;
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
    document.addEventListener("visibilitychange", function () { if (!document.hidden) reload(true); });
    window.addEventListener("pagehide", function () { clearInterval(refreshTimer); refreshTimer = null; });
    window.addEventListener("pageshow", function (event) { start_refresh(); if (event.persisted) reload(true); });

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
        start_refresh();
        if (signed && state.data) toast("Signature received. Thank you.");
        if (pendingSignature && state.data) toast("Your signature is not complete yet. Your request is unchanged.");
    }
    start();
})();
