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
if (typeof module !== "undefined" && module.exports) module.exports = { dcrScheduledPrincipal: dcrScheduledPrincipal };
(function () {
    "use strict";
    if (typeof document === "undefined") return;

    var root = document.getElementById("dcr-dealer-portal");
    if (!root) return;

    var view = document.getElementById("dcr-portal-view");
    var main = document.getElementById("dcr-portal-main");
    var toastBox = document.getElementById("dcr-portal-toast");
    var toastTimer = null;
    var state = { data: null, error: null, loading: true, lastRoute: "" };

    var WEB_FORM = "/dealer-home-request";
    var MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
    var UPLOAD_ACCEPT = ".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp";
    var UPLOAD_NOTE = "PDF, Word or image, up to 10 MB";
    var LOAN_STAGES = ["Not Applicable", "Not Started", "Applied", "Approved", "Funded", "Active", "Closed"];
    var ORDER_STAGES = ["Draft", "Pending", "Ordered", "Delivered", "Closed"];

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
        cancelled: '<circle cx="7" cy="7" r="6.3" fill="#8c8c8c"></circle><path d="M4.8 4.8l4.4 4.4M9.2 4.8L4.8 9.2" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round"></path>'
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

    function is_number(value) {
        return value !== null && value !== undefined && value !== "" && !Number.isNaN(Number(value));
    }

    // null and undefined mean "the server has no figure"; zero is a real amount.
    function money(value, currency) {
        if (!is_number(value)) return "—";
        try {
            return new Intl.NumberFormat("en-US", { style: "currency", currency: currency || "USD" }).format(Number(value));
        } catch (error) {
            return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value));
        }
    }

    function parse_date(value) {
        if (!value) return null;
        var parts = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value));
        var date = parts ? new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3])) : new Date(value);
        return Number.isNaN(date.getTime()) ? null : date;
    }

    function fmt_date(value) {
        var date = parse_date(value);
        if (!date) return "";
        var options = { month: "short", day: "numeric" };
        if (date.getFullYear() !== new Date().getFullYear()) options.year = "numeric";
        return new Intl.DateTimeFormat("en-US", options).format(date);
    }

    function sentence(value) {
        var text = String(value || "");
        return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
    }

    function mark(kind, size) {
        size = size || 14;
        return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 14 14" fill="none" aria-hidden="true">' + MARKS[kind] + "</svg>";
    }

    function status(kind, label) {
        return '<span class="dcr-status">' + mark(kind) + esc(label) + "</span>";
    }

    function cell(cls, html) {
        return '<span class="' + cls + '">' + html + "</span>";
    }

    function section(title, body, aside) {
        return '<section class="dcr-section"><div class="dcr-section-head"><h2>' + esc(title) + "</h2>" + (aside ? '<span class="dcr-small">' + esc(aside) + "</span>" : "") + "</div>" + body + "</section>";
    }

    function cells(columns, pairs) {
        var list = pairs.slice();
        while (list.length % columns) list.push(["", ""]);
        return '<dl class="dcr-cells dcr-cells-' + columns + '">' + list.map(function (pair) {
            return "<div><dt>" + esc(pair[0]) + "</dt><dd>" + esc(pair[1]) + "</dd></div>";
        }).join("") + "</dl>";
    }

    function toast(message, is_error) {
        if (toastTimer) window.clearTimeout(toastTimer);
        toastBox.innerHTML = (is_error ? '<span style="display:inline-flex;color:#e03636">' + ICONS.danger + "</span>" : mark("done")) + "<span>" + esc(message || "Something went wrong. Please try again.") + "</span>";
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

    // ------------------------------------------------------------ request model
    function deals() { return (state.data && state.data.deals) || []; }
    function signatures() { return (state.data && state.data.signatures) || []; }

    function is_cancelled(deal) { return deal.docstatus === 2 || deal.portal_status === "Cancelled"; }
    function is_accepted(deal) { return !is_cancelled(deal) && (deal.portal_status === "Accepted" || deal.docstatus === 1); }
    function is_open(deal) { return !is_cancelled(deal) && !is_accepted(deal); }
    function can_edit(deal) { return is_open(deal) && deal.docstatus === 0; }
    function loan_rank(deal) { return LOAN_STAGES.indexOf(deal.loan_stage); }
    function order_rank(deal) { return ORDER_STAGES.indexOf(deal.order_stage); }
    function has_loan(deal) { return !!(deal.loan && deal.loan.source); }
    function summary(deal) { return has_loan(deal) && deal.loan.payments_summary ? deal.loan.payments_summary : null; }

    function documents(deal) { return (deal.documents && deal.documents.items) || []; }
    function missing_documents(deal) { return documents(deal).filter(function (item) { return !item.complete && !item.uploaded; }); }

    function deal_signatures(deal) {
        return signatures().filter(function (item) {
            return item.reference_name && (item.reference_name === deal.name || (deal.loan && (item.reference_name === deal.loan.name || item.reference_name === deal.loan.application_name)));
        });
    }

    function unlinked_signatures() {
        var linked = {};
        deals().forEach(function (deal) { deal_signatures(deal).forEach(function (item) { linked[item.name] = true; }); });
        return signatures().filter(function (item) { return !linked[item.name]; });
    }

    // One dealer-facing status per request. Draft, Submitted for Review and
    // Changes Requested are all "In review": the dealer saves, DCR reviews.
    function stage(deal) {
        if (is_cancelled(deal)) return { label: "Cancelled", kind: "cancelled", group: "Closed" };
        if (!is_accepted(deal)) return { label: "In review", kind: "progress", group: "In review" };
        if (deal.loan_stage === "Closed" || deal.order_stage === "Closed") return { label: "Closed", kind: "closed", group: "Closed" };
        if (deal.loan_stage === "Active") return { label: "Active", kind: "done", group: "Active" };
        if (deal.order_stage === "Delivered") return { label: "Delivered", kind: "done", group: "In progress" };
        if (deal.order_stage === "Ordered") return { label: "Ordered", kind: "progress", group: "In progress" };
        if (deal.loan_stage === "Funded") return { label: "Funded", kind: "progress", group: "In progress" };
        if (deal.loan_stage === "Approved") return { label: "Approved", kind: "progress", group: "In progress" };
        if (deal.loan_stage === "Applied") return { label: "Loan applied", kind: "progress", group: "In progress" };
        return { label: "Accepted", kind: "done", group: "In progress" };
    }

    function needs(deal) {
        var waiting = deal_signatures(deal).filter(function (item) { return item.actionable; });
        if (waiting.length) return "Sign the " + waiting[0].document_type;
        if (is_open(deal)) {
            var count = missing_documents(deal).length;
            if (count) return "Upload " + count + (count === 1 ? " document" : " documents");
        }
        return "";
    }

    function home_label(deal) {
        return [deal.factory && deal.factory.label, deal.home_type, deal.financing_type === "Cash" ? "Cash" : ""].filter(Boolean).join(" · ") || "Home request";
    }

    function field(deal, name) {
        var value = deal[name];
        if ((value === null || value === undefined || value === "") && deal.editable) value = deal.editable[name];
        return value === null || value === undefined ? "" : value;
    }

    function upcoming_payments() {
        var rows = [];
        deals().forEach(function (deal) {
            var data = summary(deal);
            ((data && data.upcoming) || []).forEach(function (row) { rows.push(Object.assign({ deal: deal.name }, row)); });
        });
        return rows.sort(function (a, b) { return String(a.date).localeCompare(String(b.date)); });
    }

    function payment_history() {
        var rows = [];
        deals().forEach(function (deal) {
            var data = summary(deal);
            ((data && data.history) || []).forEach(function (row) { rows.push(Object.assign({ deal: deal.name }, row)); });
        });
        return rows.sort(function (a, b) { return String(b.date).localeCompare(String(a.date)); });
    }

    function payments_reported() { return deals().some(function (deal) { return !!summary(deal); }); }

    // ------------------------------------------------------------ shared pieces
    function request_href(deal) { return "#/request/" + encodeURIComponent(deal.name); }

    function upload_control(cls, target, name, document_type, label) {
        return '<label class="' + cls + ' dcr-upload" tabindex="0" role="button">' + esc(label || "Upload") +
            '<input type="file" accept="' + UPLOAD_ACCEPT + '" data-upload-target="' + esc(target) + '" data-target-name="' + esc(name || "") + '" data-document-type="' + esc(document_type) + '"></label>';
    }

    function view_button(target, name, document_type) {
        return '<button type="button" class="dcr-btn-text" data-action="download" data-target-type="' + esc(target) + '" data-target-name="' + esc(name || "") + '" data-document-type="' + esc(document_type) + '">View</button>';
    }

    function file_icon(item) {
        if (!item.uploaded) return '<span class="dcr-slot">' + ICONS.paperupload.replace('width="16" height="16"', 'width="12" height="12"') + "</span>";
        var match = /\.([a-z0-9]+)$/i.exec(item.file_name || "");
        var ext = match ? match[1].toLowerCase() : "";
        if (ext === "pdf") return FILE_ICONS.pdf;
        if (ext === "doc" || ext === "docx") return FILE_ICONS.docx;
        if (ext === "png" || ext === "jpg" || ext === "jpeg" || ext === "webp") return FILE_ICONS.img;
        return '<span class="dcr-slot dcr-slot-filled">' + ICONS.paper.replace('width="16" height="16"', 'width="12" height="12"') + "</span>";
    }

    // One documents table for request checklists and dealer documents.
    function documents_table(items, target, name, can_upload) {
        var dated = items.some(function (item) { return item.uploaded_on; });
        var head = '<div class="dcr-thead">' + cell("dcr-c-icon", "") + cell("dcr-c-grow", "Document") + cell("dcr-c-grow", "File") + (dated ? cell("dcr-c-date", "Added") : "") + cell("dcr-c-act", "") + "</div>";
        var rows = items.map(function (item) {
            var type = item.fieldname || item.document_type;
            var file = item.uploaded ? esc(item.file_name || "Uploaded") : (item.complete ? "Not required" : (can_upload ? '<span class="dcr-needed">Needed</span>' : "Not provided"));
            var actions = (item.uploaded ? view_button(target, name, type) : "") + (!item.uploaded && !item.complete && can_upload ? upload_control("dcr-btn-row", target, name, type) : "");
            return '<div class="dcr-row">' + cell("dcr-c-icon", file_icon(item)) + cell("dcr-c-grow dcr-strong", esc(item.label || item.document_type)) + cell("dcr-c-grow dcr-muted", file) + (dated ? cell("dcr-c-date", esc(fmt_date(item.uploaded_on))) : "") + cell("dcr-c-act", actions) + "</div>";
        }).join("");
        return '<div class="dcr-table">' + head + rows + "</div>";
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

    function signatures_table(items) {
        var head = '<div class="dcr-thead">' + cell("dcr-c-icon", "") + cell("dcr-c-grow", "Document") + cell("dcr-c-grow", "Status") + cell("dcr-c-date", "Date") + cell("dcr-c-act", "") + "</div>";
        var rows = items.map(function (item) {
            var action = item.actionable ? '<button type="button" class="dcr-btn-row" data-action="sign" data-signature="' + esc(item.name) + '">Sign</button>' : (item.status === "Declined" || item.status === "Voided" ? '<span class="dcr-muted">Contact us</span>' : "");
            return '<div class="dcr-row">' + cell("dcr-c-icon", FILE_ICONS.pdf) + cell("dcr-c-grow dcr-strong", esc(item.document_type)) + cell("dcr-c-grow", signature_status(item)) + cell("dcr-c-date", esc(fmt_date(item.signed_date || item.sent_date))) + cell("dcr-c-act", action) + "</div>";
        }).join("");
        return '<div class="dcr-table">' + head + rows + "</div>";
    }

    function empty_state(icon, title, text, action) {
        return '<div class="dcr-empty"><span class="dcr-empty-tile">' + icon.replace('width="16" height="16"', 'width="20" height="20"') + "</span><h3>" + esc(title) + "</h3><p>" + esc(text) + "</p>" + (action || "") + "</div>";
    }

    function new_request_button() {
        return '<a class="dcr-btn-primary" href="' + WEB_FORM + '/new">' + PLUS + "New request</a>";
    }

    // ------------------------------------------------------------ Home
    function greeting() {
        var hour = new Date().getHours();
        return hour < 12 ? "Good morning" : (hour < 18 ? "Good afternoon" : "Good evening");
    }

    function setup_rows() {
        var data = state.data;
        var rows = [];
        var agreements = signatures().filter(function (item) { return item.document_type === "Dealer Agreement" || item.document_type === "MIFA"; });
        var unsigned = agreements.filter(function (item) { return item.status !== "Signed"; });
        if (unsigned.length) {
            var waiting = unsigned.filter(function (item) { return item.actionable; });
            rows.push({ label: "Sign your agreements", detail: unsigned.map(function (item) { return item.document_type; }).join(" and "), action: waiting.length ? '<a class="dcr-btn-row" href="#/settings">Sign</a>' : "", open: waiting.length > 0 });
        }
        var documents_needed = (data.onboarding_documents || []).filter(function (item) { return !item.uploaded; });
        if (documents_needed.length) {
            rows.push({ label: "Upload dealer documents", detail: documents_needed.map(function (item) { return item.label; }).join(", "), action: '<a class="dcr-btn-row" href="#/settings">Upload</a>', open: true });
        }
        unlinked_signatures().filter(function (item) { return item.actionable && agreements.indexOf(item) < 0; }).forEach(function (item) {
            rows.push({ label: "Sign the " + item.document_type, detail: item.sent_date ? "Sent " + fmt_date(item.sent_date) : "", action: '<button type="button" class="dcr-btn-row" data-action="sign" data-signature="' + esc(item.name) + '">Sign</button>', open: true });
        });
        return rows;
    }

    function setup_section() {
        var rows = setup_rows();
        if (!rows.length) return "";
        var head = '<div class="dcr-thead">' + cell("dcr-c-status", "Status") + cell("dcr-c-grow", "Step") + cell("dcr-c-grow", "Details") + cell("dcr-c-act", "") + "</div>";
        return section("Set up your dealer profile", '<div class="dcr-table">' + head + rows.map(function (row) {
            return '<div class="dcr-row">' + cell("dcr-c-status", row.open ? status("action", "To do") : status("progress", "With DCR")) + cell("dcr-c-grow dcr-strong", esc(row.label)) + cell("dcr-c-grow dcr-muted", esc(row.detail)) + cell("dcr-c-act", row.action) + "</div>";
        }).join("") + "</div>");
    }

    // Projected balance for the next six months, from each loan's own schedule.
    function month_bars() {
        var now = new Date();
        var months = [];
        for (var i = 0; i < 6; i++) months.push({ date: new Date(now.getFullYear(), now.getMonth() + i, 1), end: new Date(now.getFullYear(), now.getMonth() + i + 1, 0, 23, 59, 59), total: 0 });
        var any = false;
        deals().forEach(function (deal) {
            var data = summary(deal);
            if (!data || !is_number(data.outstanding_principal)) return;
            any = true;
            var schedule = (data.upcoming || []).filter(function (row) { return parse_date(row.date) && is_number(row.principal); });
            months.forEach(function (month) {
                var end = month.end.getFullYear() + "-" + String(month.end.getMonth() + 1).padStart(2, "0") + "-" + String(month.end.getDate()).padStart(2, "0");
                var balance = dcrScheduledPrincipal(data.outstanding_principal, schedule, end, data.as_of);
                month.total += balance;
            });
        });
        var max = Math.max.apply(null, months.map(function (month) { return month.total; }));
        if (!any || !max) return "";
        var label = new Intl.DateTimeFormat("en-US", { month: "short" });
        return '<div class="dcr-card-foot"><span class="dcr-small">Scheduled principal outlook</span><div class="dcr-bars" role="img" aria-label="Scheduled principal outlook by month">' + months.map(function (month, index) {
            return '<span class="' + (index === 0 ? "is-now" : "") + '" style="height:' + Math.round(month.total / max * 100) + '%" title="' + esc(money(month.total)) + '"></span>';
        }).join("") + '</div><div class="dcr-bar-labels">' + months.map(function (month) { return "<span>" + esc(label.format(month.date)) + "</span>"; }).join("") + "</div></div>";
    }

    function home_cards() {
        var list = deals();
        var loans = list.filter(has_loan);
        var upcoming = upcoming_payments();
        var reported = payments_reported();

        var balances = loans.map(function (deal) { var data = summary(deal); return data ? data.outstanding_principal : null; }).filter(is_number);
        var balance = balances.length ? money(balances.reduce(function (total, value) { return total + Number(value); }, 0)) : "—";
        var unavailable = loans.some(function (deal) { var data = summary(deal); return deal.loan.payments_unavailable || (data && data.funded !== false && !is_number(data.outstanding_principal)); });
        if (unavailable) balance = "—";
        var balance_note = unavailable ? "Balance details could not load" : !loans.length ? "No loans yet" : (balances.length ? "Across " + balances.length + (balances.length === 1 ? " funded loan" : " funded loans") : "No funded loans yet");
        var card_balance = '<div class="dcr-card"><span class="dcr-small">Outstanding principal</span><span class="dcr-metric">' + esc(balance) + '</span><span class="dcr-small">' + esc(balance_note) + "</span>" + (unavailable ? "" : month_bars()) + "</div>";

        var groups = [["In review", "#0070cc"], ["In progress", "#8fc0e8"], ["Active", "#30a66d"], ["Closed", "#c7c7c7"]].map(function (group) {
            return { label: group[0], color: group[1], count: list.filter(function (deal) { return stage(deal).group === group[0]; }).length };
        });
        var need = list.filter(function (deal) { return needs(deal); }).length;
        var card_requests = '<div class="dcr-card"><span class="dcr-small">Home build requests</span><span class="dcr-metric">' + list.length + '</span><span class="dcr-small">' + (need ? need + (need === 1 ? " needs" : " need") + " something from you" : "Nothing needed from you") + '</span><div class="dcr-card-foot"><div class="dcr-stack" role="img" aria-label="Requests by stage">' +
            groups.filter(function (group) { return group.count; }).map(function (group) { return '<span style="flex:' + group.count + " 1 0;background:" + group.color + '"></span>'; }).join("") +
            '</div><div class="dcr-legend">' + groups.map(function (group) { return '<span><i style="background:' + group.color + '"></i><em>' + esc(group.label) + '</em><span class="dcr-num">' + group.count + "</span></span>"; }).join("") + "</div></div></div>";

        var next = upcoming[0];
        var card_next = '<div class="dcr-card"><span class="dcr-small">' + (next && next.due_status === "Past due" ? "Past-due payment" : "Next payment") + '</span><span class="dcr-metric">' + esc(next ? fmt_date(next.date) : "—") + '</span><span class="dcr-small">' + esc(next ? money(next.total) : (!loans.length ? "No loans yet" : (unavailable ? "Payment details could not load" : reported ? "Nothing scheduled" : "No payments before funding"))) + "</span>" +
            (upcoming.length ? '<div class="dcr-card-foot">' + upcoming.slice(0, 3).map(function (row) {
                return '<div class="dcr-due"><span class="dcr-num" style="flex:0 0 64px">' + esc(fmt_date(row.date)) + '</span><span class="dcr-c-grow dcr-num">' + esc(row.deal) + '</span><span class="dcr-num">' + esc(money(row.total)) + "</span></div>";
            }).join("") + "</div>" : "") + "</div>";

        return '<section class="dcr-cards" aria-label="At a glance">' + card_balance + card_requests + card_next + "</section>";
    }

    function requests_table(list) {
        var head = '<div class="dcr-thead">' + cell("dcr-c-status", "Status") + cell("dcr-c-id", "Request") + cell("dcr-c-grow", "Home") + cell("dcr-c-count", "Documents") + cell("dcr-c-grow", "Needs from you") + cell("dcr-c-chev", "") + "</div>";
        var rows = list.map(function (deal) {
            var current = stage(deal);
            var need = needs(deal);
            var docs = deal.documents || {};
            return '<a class="dcr-row" href="' + request_href(deal) + '">' + cell("dcr-c-status", status(current.kind, current.label)) + cell("dcr-c-id", esc(deal.name)) + cell("dcr-c-grow", esc(home_label(deal))) +
                cell("dcr-c-count", esc((docs.complete === undefined ? docs.uploaded || 0 : docs.complete) + " of " + (docs.required || 0))) +
                cell("dcr-c-grow " + (need ? "dcr-strong" : "dcr-muted"), esc(need || "Nothing right now")) + cell("dcr-c-chev", CHEVRON) + "</a>";
        }).join("");
        return '<div class="dcr-table">' + head + rows + "</div>";
    }

    function page_home() {
        var list = deals();
        var order = list.slice().sort(function (a, b) { return (needs(b) ? 1 : 0) - (needs(a) ? 1 : 0); });
        var requests = list.length ? requests_table(order) : empty_state(ICONS.home, "No home build requests yet", "Your requests, loans and payments will show up here.", new_request_button());
        return '<div class="dcr-page"><div class="dcr-page-head"><h1>' + greeting() + "</h1>" + (list.length ? new_request_button() : "") + "</div>" +
            setup_section() + (list.length ? home_cards() : "") + section("Home build requests", requests) + "</div>";
    }

    // ------------------------------------------------------------ request
    function progress_steps(deal) {
        var steps = [{ label: "Saved", kind: "done", note: fmt_date(deal.created_on) }];
        var open = is_open(deal);
        if (open) {
            missing_documents(deal).forEach(function (item) { steps.push({ label: "Upload " + item.document_type, kind: "action", upload: item }); });
        }
        if (is_cancelled(deal)) {
            steps.push({ label: "Cancelled", kind: "cancelled", note: fmt_date(deal.cancelled_on) });
            return steps;
        }
        steps.push({ label: "Review", kind: open ? "current" : "done", note: open ? "In progress" : "" });
        steps.push({ label: "Accepted", kind: open ? "upcoming" : "done", note: open ? "" : fmt_date(deal.accepted_on) });
        if (open) return steps;

        var chain = [];
        var floored = deal.financing_type === "Floored";
        var loan = loan_rank(deal);
        var order = order_rank(deal);
        if (floored) {
            var packets = deal_signatures(deal).filter(function (item) { return item.document_type === "Flooring Packet"; });
            var waiting = packets.filter(function (item) { return item.actionable; })[0];
            var signed = !!(deal.loan && deal.loan.signed) || packets.some(function (item) { return item.status === "Signed"; });
            chain.push({ label: "Loan approved", done: loan >= 3 });
            chain.push({ label: signed ? "Flooring Packet signed" : waiting ? "Sign Flooring Packet" : "Flooring Packet with DCR", done: signed, signature: waiting });
            chain.push({ label: "Loan funded", done: loan >= 4 });
        }
        chain.push({ label: "Home ordered", done: order >= 2 });
        chain.push({ label: "Home delivered", done: order >= 3 });
        if (floored) chain.push({ label: loan >= 6 ? "Loan repaid" : "Repaying the loan", done: loan >= 6 });
        chain.push({ label: "Closed", done: order >= 4 || loan >= 6 });
        var found = false;
        chain.forEach(function (step) {
            if (step.done) { steps.push({ label: step.label, kind: "done" }); return; }
            if (step.signature) { steps.push({ label: step.label, kind: "action", signature: step.signature }); found = true; return; }
            steps.push({ label: step.label, kind: found ? "upcoming" : "current" });
            found = true;
        });
        return steps;
    }

    function progress_list(deal) {
        return '<ol class="dcr-steps">' + progress_steps(deal).map(function (step) {
            var aside = step.note ? '<span class="dcr-small">' + esc(step.note) + "</span>" : "";
            if (step.upload) aside = upload_control("dcr-btn-mini", "hbr", deal.name, step.upload.document_type);
            if (step.signature) aside = '<button type="button" class="dcr-btn-mini" data-action="sign" data-signature="' + esc(step.signature.name) + '">Sign</button>';
            return '<li class="is-' + step.kind + '"><span class="dcr-step-mark">' + mark(step.kind) + '</span><span class="dcr-step-body"><span>' + esc(step.label) + "</span>" + aside + "</span></li>";
        }).join("") + "</ol>";
    }

    function tracker(deal) {
        var rank = Math.max(order_rank(deal), 1);
        var labels = ["Pending", "Ordered", "Delivered", "Closed"];
        return '<ol class="dcr-tracker">' + labels.map(function (label, index) {
            var position = index + 1;
            var cls = rank === 4 || position < rank ? "is-done" : (position === rank ? "is-now" : "");
            return '<li class="' + cls + '"><i></i><span>' + label + "</span></li>";
        }).join("") + "</ol>";
    }

    function payments_section(deal) {
        var data = summary(deal);
        if (!data) return section("Payments", '<p class="dcr-note">' + (deal.loan.payments_unavailable ? "Payment details could not load. Refresh to try again." : "No payments yet. The schedule starts when the loan is funded.") + '</p>');
        var upcoming = data.upcoming || [];
        var history = data.history || [];
        if (!upcoming.length && !history.length) return section("Payments", '<p class="dcr-note">No payments yet. The schedule starts when the loan is funded.</p>');
        var head = '<div class="dcr-thead">' + cell("dcr-c-icon", "") + cell("dcr-c-date", "Date") + cell("dcr-c-grow", "Status") + cell("dcr-c-money", "Principal") + cell("dcr-c-money", "Interest") + cell("dcr-c-money", "Charges") + cell("dcr-c-money", "Amount") + "</div>";
        var rows = upcoming.map(function (row) {
            return '<div class="dcr-row">' + cell("dcr-c-icon", mark("progress")) + cell("dcr-c-date", esc(fmt_date(row.date))) + cell("dcr-c-grow dcr-muted", esc(row.due_status || "Scheduled")) + cell("dcr-c-money", esc(money(row.principal))) + cell("dcr-c-money", esc(money(row.interest))) + cell("dcr-c-money", esc(money(row.charges || 0))) + cell("dcr-c-money", esc(money(row.total))) + "</div>";
        }).concat(history.map(function (row) {
            return '<div class="dcr-row">' + cell("dcr-c-icon", mark("done")) + cell("dcr-c-date", esc(fmt_date(row.date))) + cell("dcr-c-grow dcr-muted", esc(row.type || "Paid")) + cell("dcr-c-money", "") + cell("dcr-c-money", "") + cell("dcr-c-money", "") + cell("dcr-c-money", esc(money(row.amount))) + "</div>";
        })).join("");
        var aside = [data.as_of ? "As of " + fmt_date(data.as_of) : "", data.history_truncated ? "most recent payments shown" : ""].filter(Boolean).join(" · ");
        return section("Payments", '<div class="dcr-table">' + head + rows + "</div>", aside);
    }

    function page_request(name) {
        var deal = deals().filter(function (item) { return item.name === name; })[0];
        if (!deal) {
            return '<div class="dcr-topbar"><nav class="dcr-crumbs" aria-label="Breadcrumb"><a href="#/home">Home</a>' + CHEVRON + "<h1>" + esc(name || "Request") + '</h1></nav></div><div class="dcr-page">' +
                empty_state(ICONS.home, "This request is not available", "It may belong to another dealer account, or it is no longer in your list.", '<a class="dcr-btn" href="#/home" style="margin-top:14px">Back to Home</a>') + "</div>";
        }
        var current = stage(deal);
        var open = is_open(deal);
        var accepted = is_accepted(deal);
        var loan = deal.loan || {};
        var data = summary(deal);
        var payoff = loan.payoff || {};

        var actions = "";
        if (can_edit(deal)) actions += '<a class="dcr-btn" href="' + WEB_FORM + "/" + encodeURIComponent(deal.name) + '/edit">' + ICONS.edit.replace('width="16" height="16"', 'width="14" height="14"') + "Edit</a>";
        if (payoff.can_request) actions += '<button type="button" class="dcr-btn" data-action="payoff" data-hbr="' + esc(deal.name) + '">' + ICONS.send.replace('width="16" height="16"', 'width="14" height="14"') + "Request payoff letter</button>";

        var address = [field(deal, "delivery_address"), field(deal, "address_line_2"), field(deal, "city"), [field(deal, "state"), field(deal, "zip")].filter(Boolean).join(" ")].filter(Boolean).join(", ");
        var details = [["Factory", deal.factory && deal.factory.label || ""], ["Floorplan", deal.floor_plan || ""], ["Serial number", deal.home_serial_no || ""], ["Factory quote", deal.quote_no || ""], ["Quoted amount", money(deal.quoted_amount)]];
        if (address) details.push(["Delivery address", address]);
        if (deal.property_type === "Park") {
            var community = [field(deal, "community_name"), field(deal, "space_number") ? "Space " + field(deal, "space_number") : ""].filter(Boolean).join(" · ");
            if (community) details.push(["Community", community]);
        }
        if (deal.home_type === "Customer Sold") {
            if (deal.end_buyer_name) details.push(["End buyer", deal.end_buyer_name]);
            if (is_number(field(deal, "selling_price"))) details.push(["Selling price", money(field(deal, "selling_price"))]);
            if (is_number(deal.installed_value)) details.push(["Installed value", money(deal.installed_value)]);
        }

        var body = section("Home details", cells(3, details));
        if (accepted && has_loan(deal)) {
            var loan_cells = [[data && is_number(data.outstanding_principal) ? "Outstanding principal" : "Principal", money(data && is_number(data.outstanding_principal) ? data.outstanding_principal : loan.principal)],
                ["Interest rate", is_number(loan.interest_rate) ? Number(loan.interest_rate) + "%" : "—"], ["Total interest", money(loan.total_interest)], ["Total payable", money(loan.total_payable)]];
            body += '<section class="dcr-section"><div class="dcr-section-head"><h2>Loan details</h2><span class="dcr-small" style="color:inherit">' + status(loan_rank(deal) >= 5 ? (loan_rank(deal) === 6 ? "closed" : "done") : "progress", sentence(deal.loan_stage || loan.status || "Applied")) + "</span></div>" + cells(4, loan_cells) + "</section>";
        }
        if (accepted) body += section("Home status", tracker(deal), deal.order_stage || "Pending");
        body += section("Documents", documents(deal).length ? documents_table(documents(deal), "hbr", deal.name, open) : '<p class="dcr-note">No documents are required for this request.</p>', open && missing_documents(deal).length ? UPLOAD_NOTE : "");
        var signed = deal_signatures(deal);
        if (signed.length) body += section("Signatures", signatures_table(signed));
        if (accepted && has_loan(deal)) body += payments_section(deal);

        var panel = '<aside class="dcr-float" aria-label="Progress and details"><section><h2>Progress</h2>' + progress_list(deal) + '</section><section><h2>Details</h2><dl class="dcr-kv">' +
            "<dt>Status</dt><dd>" + status(current.kind, current.label) + "</dd>" +
            "<dt>Home status</dt><dd>" + esc(is_cancelled(deal) ? "Cancelled" : (open ? "Not started" : (deal.order_stage || "Pending"))) + "</dd>" +
            "<dt>Loan stage</dt><dd>" + esc(deal.financing_type === "Cash" ? "Not applicable" : sentence(deal.loan_stage || "Not started")) + "</dd>" +
            "<dt>Home type</dt><dd>" + esc(deal.home_type || "—") + "</dd><dt>Deal type</dt><dd>" + esc(deal.financing_type || "—") + "</dd><dt>Property</dt><dd>" + esc(deal.property_type || "—") + "</dd></dl></section></aside>";

        return '<div class="dcr-topbar"><nav class="dcr-crumbs" aria-label="Breadcrumb"><a href="#/home">Home</a>' + CHEVRON + "<h1>" + esc(deal.name) + '</h1></nav><div style="display:flex;gap:8px">' + actions + '</div></div><div class="dcr-record"><div class="dcr-record-main">' + body + "</div>" + panel + "</div>";
    }

    // ------------------------------------------------------------ Lending
    function page_lending() {
        var loans = deals().filter(has_loan);
        var body;
        if (!loans.length) {
            body = empty_state(ICONS.paper, "No loans yet", "A loan appears here once DCR opens it for an accepted floored request.");
        } else {
            var head = '<div class="dcr-thead">' + cell("dcr-c-status", "Loan") + cell("dcr-c-id", "Request") + cell("dcr-c-grow", "Home") + cell("dcr-c-money", "Outstanding") + cell("dcr-c-grow", "Next") + cell("dcr-c-chev", "") + "</div>";
            body = '<div class="dcr-table">' + head + loans.map(function (deal) {
                var current = stage(deal);
                var data = summary(deal);
                var next = data && data.upcoming && data.upcoming[0];
                var need = needs(deal);
                var text = need || (next ? (next.due_status === "Past due" ? "Past due " : "Payment ") + fmt_date(next.date) + " · " + money(next.total) : (current.label === "Closed" ? "Paid off" : (!data || data.funded === false) ? "Not funded yet" : ""));
                return '<a class="dcr-row" href="' + request_href(deal) + '">' + cell("dcr-c-status", status(current.kind, current.label)) + cell("dcr-c-id", esc(deal.name)) + cell("dcr-c-grow", esc(home_label(deal))) +
                    cell("dcr-c-money", esc(money(data ? data.outstanding_principal : null))) + cell("dcr-c-grow " + (need ? "dcr-strong" : "dcr-muted"), esc(text || "Nothing right now")) + cell("dcr-c-chev", CHEVRON) + "</a>";
            }).join("") + "</div>";
        }
        return '<div class="dcr-page"><div class="dcr-page-head"><h1>Lending</h1></div>' + body + "</div>";
    }

    // ------------------------------------------------------------ Payments
    function page_payments() {
        var ach = (state.data && state.data.ach) || {};
        var accounts = ach.accounts || [];
        var method;
        if (accounts.length) {
            method = '<div class="dcr-table">' + accounts.map(function (account) {
                var name = account.bank_name || "Bank account";
                var initials = name.split(/\s+/).map(function (word) { return word.charAt(0); }).join("").slice(0, 2).toUpperCase();
                return '<div class="dcr-row">' + cell("dcr-c-icon", '<span class="dcr-bank-mark" aria-hidden="true">' + esc(initials) + "</span>") + cell("dcr-c-grow dcr-strong", esc(name) + (account.last4 ? ' <span class="dcr-num">····' + esc(account.last4) + "</span>" : "")) +
                    cell("dcr-c-grow dcr-muted", account.is_default ? "Default" : "") + cell("dcr-c-act", account.status === "Paused" ? status("draft", "Paused") : status("done", "Connected")) + "</div>";
            }).join("") + '<div class="dcr-row">' + cell("dcr-c-icon", "") + cell("dcr-c-grow dcr-strong", "Auto-pay") + cell("dcr-c-grow dcr-muted", "DCR manages payment setup. Contact DCR to confirm automatic payments.") + cell("dcr-c-act", "") + "</div></div>";
        } else {
            method = '<p class="dcr-note">No bank account is connected. Bank setup is not available in the portal yet; DCR will set up auto-pay with you.</p>';
        }

        var loans = deals().filter(has_loan);
        var body = section("Payment method", method);
        if (!loans.length) {
            body += section("Upcoming", '<p class="dcr-note">No payments yet. They appear here once a loan is funded.</p>');
        } else if (!payments_reported()) {
            body += section("Due and scheduled", '<p class="dcr-note">' + (loans.some(function (deal) { return deal.loan.payments_unavailable; }) ? "Payment details could not load. Refresh to try again." : "No payments yet. The schedule starts when a loan is funded.") + '</p>');
        } else {
            var upcoming = upcoming_payments();
            var history = payment_history();
            var head = function (label) { return '<div class="dcr-thead">' + cell("dcr-c-icon", "") + cell("dcr-c-date", label) + cell("dcr-c-id", "Loan") + cell("dcr-c-grow", "Details") + cell("dcr-c-money", "Amount") + "</div>"; };
            if (loans.some(function (deal) { return deal.loan.payments_unavailable; })) body += '<p class="dcr-note">Some payment details could not load. Refresh to try again.</p>';
            body += section("Due and scheduled", upcoming.length ? '<div class="dcr-table">' + head("Due") + upcoming.map(function (row) {
                var parts = [row.due_status === "Past due" ? "Past due" : "Scheduled", is_number(row.principal) ? "Principal " + money(row.principal) : "", is_number(row.interest) ? "Interest " + money(row.interest) : "", row.charges ? "Charges " + money(row.charges) : ""].filter(Boolean).join(" · ");
                return '<a class="dcr-row" href="#/request/' + encodeURIComponent(row.deal) + '">' + cell("dcr-c-icon", mark("progress")) + cell("dcr-c-date", esc(fmt_date(row.date))) + cell("dcr-c-id", esc(row.deal)) + cell("dcr-c-grow dcr-muted", esc(parts)) + cell("dcr-c-money", esc(money(row.total))) + "</a>";
            }).join("") + "</div>" : '<p class="dcr-note">Nothing is scheduled right now.</p>');
            body += section("Paid", history.length ? '<div class="dcr-table">' + head("Paid") + history.map(function (row) {
                return '<a class="dcr-row" href="#/request/' + encodeURIComponent(row.deal) + '">' + cell("dcr-c-icon", mark("done")) + cell("dcr-c-date", esc(fmt_date(row.date))) + cell("dcr-c-id", esc(row.deal)) + cell("dcr-c-grow dcr-muted", esc(row.type || "Payment")) + cell("dcr-c-money", esc(money(row.amount))) + "</a>";
            }).join("") + "</div>" : '<p class="dcr-note">No payments have been made yet.</p>', deals().some(function (deal) { var data = summary(deal); return data && data.history_truncated; }) ? "Most recent payments shown" : "");
        }
        return '<div class="dcr-page"><div class="dcr-page-head"><h1>Payments</h1></div>' + body + "</div>";
    }

    // ------------------------------------------------------------ Settings
    function page_settings() {
        var data = state.data;
        var customer = data.customer || {};
        var factories = (data.factories || []).map(function (item) { return item.label || item.name; }).join(", ");
        var onboarding = data.onboarding_documents || [];
        var all_signatures = signatures();
        var body = section("Dealer", cells(2, [["Dealer", customer.label || ""], ["Sign-in email", customer.email || ""], ["Assigned factories", factories || "None assigned yet"]]));
        body += section("Agreements", all_signatures.length ? signatures_table(all_signatures) : '<p class="dcr-note">No agreements have been sent yet.</p>');
        body += section("Dealer documents", documents_table(onboarding, "customer", customer.name, true), onboarding.some(function (item) { return !item.uploaded; }) ? UPLOAD_NOTE : "");
        return '<div class="dcr-page"><div class="dcr-page-head"><h1>Settings</h1></div>' + body + "</div>";
    }

    // ------------------------------------------------------------ loading and errors
    function page_loading() {
        var card = '<div class="dcr-card"><i style="width:96px"></i><i style="width:140px;height:16px"></i><i style="margin-top:auto;height:72px;border-radius:8px"></i></div>';
        return '<div class="dcr-page dcr-skeleton" role="status" aria-label="Loading"><i style="width:220px;height:20px"></i><div class="dcr-cards">' + card + card + card + '</div><div class="dcr-table"><div class="dcr-thead"><span class="dcr-spinner" aria-hidden="true"></span>Loading…</div>' +
            [[120, 96, 280], [96, 96, 220], [136, 96, 260]].map(function (widths) { return '<div class="dcr-row">' + widths.map(function (width) { return '<i style="width:' + width + 'px"></i>'; }).join("") + "</div>"; }).join("") + "</div></div>";
    }

    function page_error(message) {
        var no_access = /not linked|not active|more than one dealer|could not be found/i.test(message || "");
        if (no_access) {
            return '<div class="dcr-page">' + empty_state(ICONS.home, "No dealer access yet", "To set up your dealer access, contact us.", '<a class="dcr-btn" href="/logout" style="margin-top:14px">Sign out</a>') + "</div>";
        }
        return '<div class="dcr-page"><div class="dcr-page-head"><h1>' + greeting() + '</h1></div><div class="dcr-alert" role="alert"><span><span class="dcr-strong">We could not load your dashboard.</span> ' + esc(message || "") + '</span><button type="button" class="dcr-btn" data-action="retry">Try again</button></div></div>';
    }

    // ------------------------------------------------------------ routing and render
    function current_route() {
        var parts = window.location.hash.replace(/^#\/?/, "").split("/");
        return { name: parts[0] || "home", arg: parts.length > 1 ? decodeURIComponent(parts.slice(1).join("/")) : "" };
    }

    function render() {
        var route = current_route();
        var active = route.name === "request" ? "home" : route.name;
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
        document.title = (route.name === "request" && route.arg ? route.arg : active.charAt(0).toUpperCase() + active.slice(1)) + " · Dealer Portal";
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
        render();
    }

    // ------------------------------------------------------------ events
    root.querySelectorAll("[data-icon]").forEach(function (node) {
        node.innerHTML = ICONS[node.getAttribute("data-icon")] || "";
        node.style.display = "inline-flex";
    });

    root.addEventListener("click", async function (event) {
        var action = event.target.closest("[data-action]");
        if (!action) return;
        var name = action.getAttribute("data-action");
        if (name === "retry") { state.data = null; await reload(); return; }
        if (name === "download") {
            var params = new URLSearchParams({
                target_type: action.getAttribute("data-target-type") || "",
                target_name: action.getAttribute("data-target-name") || "",
                document_type: action.getAttribute("data-document-type") || "",
            });
            window.location.href = "/api/method/dcr.api.dealer_portal.download_document?" + params.toString();
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
        if (label) { label.classList.add("is-busy"); label.childNodes[0].nodeValue = "Uploading…"; }
        try {
            await upload_file(input);
            toast("Document uploaded.");
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

    window.addEventListener("hashchange", render);

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
