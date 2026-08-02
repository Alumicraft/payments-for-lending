(function () {
    "use strict";

    var root = document.getElementById("dcr-dealer-portal");
    if (!root) return;

    var app = document.getElementById("dcr-portal-app");
    var loading = document.getElementById("dcr-portal-loading");
    var alertBox = document.getElementById("dcr-portal-alert");
    var state = { data: null, currentDeal: null, view: "dashboard" };

    function escape_html(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function format_currency(value) {
        if (value === null || value === undefined || value === "") return "—";
        var number = Number(value);
        if (Number.isNaN(number)) return "—";
        return new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: "USD",
            maximumFractionDigits: 2,
        }).format(number);
    }

    function format_date(value) {
        if (!value) return "";
        var date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value);
        return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date);
    }

    function chip_class(value) {
        var text = String(value || "").toLowerCase();
        if (text.indexOf("accepted") >= 0 || text.indexOf("approved") >= 0 || text.indexOf("delivered") >= 0 || text.indexOf("signed") >= 0 || text.indexOf("active") >= 0) return "green";
        if (text.indexOf("review") >= 0 || text.indexOf("applied") >= 0 || text.indexOf("ordered") >= 0 || text.indexOf("sent") >= 0) return "gold";
        if (text.indexOf("funded") >= 0 || text.indexOf("paused") >= 0) return "blue";
        return "";
    }

    function show_alert(message) {
        alertBox.textContent = message || "Something went wrong. Please try again.";
        alertBox.hidden = false;
        window.setTimeout(function () {
            alertBox.hidden = true;
        }, 6000);
    }

    function csrf_headers() {
        var token = root.getAttribute("data-csrf-token") || window.csrf_token || "";
        return token ? { "X-Frappe-CSRF-Token": token } : {};
    }

    function error_message(payload) {
        if (!payload) return "The request could not be completed.";
        if (payload.message && typeof payload.message === "string") return payload.message;
        if (payload._server_messages) {
            try {
                var messages = JSON.parse(payload._server_messages);
                if (messages.length) return JSON.parse(messages[0]).message;
            } catch (error) {
                // Fall through to the generic response.
            }
        }
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

    function show_view(view) {
        state.view = view;
        document.querySelectorAll("[data-view-panel]").forEach(function (panel) {
            panel.hidden = panel.getAttribute("data-view-panel") !== view;
        });
        document.querySelectorAll("[data-view]").forEach(function (button) {
            button.classList.toggle("is-active", button.getAttribute("data-view") === view);
        });
    }

    function stat_card(value, label) {
        return '<article class="dcr-stat-card"><div class="dcr-stat-value">' + escape_html(value) + '</div><div class="dcr-stat-label">' + escape_html(label) + "</div></article>";
    }

    function render_stats() {
        var deals = state.data.deals || [];
        var missing = deals.reduce(function (total, deal) { return total + ((deal.documents && deal.documents.missing) || []).length; }, 0);
        var signatures = (state.data.signatures || []).filter(function (item) { return item.actionable; }).length;
        var active = deals.filter(function (deal) { return deal.portal_status !== "Accepted" || deal.order_stage !== "Delivered"; }).length;
        document.querySelector("[data-stats]").innerHTML = [
            stat_card(active, "Active requests"),
            stat_card(missing, "Documents needed"),
            stat_card(signatures, "Signatures waiting"),
            stat_card((state.data.ach && state.data.ach.accounts || []).length, "Auto-pay accounts"),
        ].join("");
        document.querySelector("[data-deal-count]").textContent = deals.length + (deals.length === 1 ? " request" : " requests");
    }

    function render_deals() {
        var deals = state.data.deals || [];
        var target = document.getElementById("dcr-deal-grid");
        if (!deals.length) {
            target.innerHTML = '<div class="dcr-empty-state"><strong>No home requests yet.</strong><br>Start your first request and save it as you gather the details.</div>';
            return;
        }
        target.innerHTML = deals.map(function (deal) {
            var factory = deal.factory && deal.factory.label || "Factory not selected";
            var missing = deal.documents && deal.documents.missing || [];
            return '<article class="dcr-deal-card" data-deal="' + escape_html(deal.name) + '" tabindex="0" role="button">' +
                '<div class="dcr-deal-top"><div><div class="dcr-deal-number">' + escape_html(deal.name) + '</div><div class="dcr-deal-title">' + escape_html(factory) + '</div></div><span class="dcr-stage-chip ' + chip_class(deal.portal_status) + '">' + escape_html(deal.portal_status) + '</span></div>' +
                '<div class="dcr-deal-meta">' + escape_html([deal.home_type, deal.financing_type, deal.property_type].filter(Boolean).join(" · ")) + '<br>' + escape_html(deal.floor_plan || "Floorplan not added") + '</div>' +
                '<div class="dcr-deal-footer"><span class="dcr-stage-chip ' + chip_class(deal.order_stage) + '">' + escape_html(deal.order_stage || "Pending") + '</span><span class="dcr-muted dcr-small">' + escape_html(missing.length ? missing.length + " docs needed" : "Checklist ready") + '</span></div>' +
                '</article>';
        }).join("");
    }

    function download_button(target, name, document_type) {
        return '<button class="dcr-text-button" data-download="1" data-target-type="' + escape_html(target) + '" data-target-name="' + escape_html(name || "") + '" data-document-type="' + escape_html(document_type) + '">View</button>';
    }

    function document_card(item, target, name) {
        var complete = item.complete || item.uploaded;
        var actions = item.uploaded ? download_button(target, name, item.fieldname || item.document_type) : "";
        var input = complete ? "" : '<label class="dcr-upload-label">Upload<input type="file" accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp" data-upload-target="' + escape_html(target) + '" data-target-name="' + escape_html(name || "") + '" data-document-type="' + escape_html(item.fieldname || item.document_type) + '"></label>';
        var status = item.uploaded ? "Uploaded and ready for review" : (complete ? "Complete" : "Needed");
        return '<article class="dcr-document-card"><div class="dcr-document-info"><div class="dcr-document-label">' + escape_html(item.label || item.document_type) + '</div><div class="dcr-document-status">' + status + '</div></div><div class="dcr-document-actions">' + actions + input + '</div></article>';
    }

    function render_documents() {
        var customer = state.data.customer || {};
        document.getElementById("dcr-onboarding-documents").innerHTML = (state.data.onboarding_documents || []).map(function (item) {
            return document_card(item, "customer", customer.name);
        }).join("");
        var deals = state.data.deals || [];
        document.getElementById("dcr-checklist-documents").innerHTML = deals.length ? deals.map(function (deal) {
            return '<div class="dcr-checklist-deal"><h3>' + escape_html(deal.name) + ' <span class="dcr-muted dcr-small">' + escape_html(deal.factory && deal.factory.label || "Home request") + '</span></h3><div class="dcr-document-grid">' + ((deal.documents && deal.documents.items) || []).map(function (item) {
            return document_card({
                    label: item.document_type,
                    document_type: item.document_type,
                    uploaded: item.uploaded,
                    complete: item.complete,
                }, "hbr", deal.name);
            }).join("") + '</div></div>';
        }).join("") : '<div class="dcr-empty-state">Create a home request to see its document checklist here.</div>';
    }

    function render_deal_detail() {
        var target = document.getElementById("dcr-deal-detail");
        var deal = state.currentDeal;
        if (!deal) { target.innerHTML = ""; return; }
        var loan = deal.loan || {};
        var can_submit = deal.portal_status === "Draft" || deal.portal_status === "Changes Requested";
        var request_actions = can_submit ? '<div class="dcr-form-actions dcr-detail-actions">' +
            (deal.editable ? '<button class="dcr-secondary-button" data-action="edit-request" data-hbr="' + escape_html(deal.name) + '">Edit request</button>' : '') +
            '<button class="dcr-primary-button" data-action="submit-review" data-hbr="' + escape_html(deal.name) + '">Submit to DCR for review</button></div>' : '';
        var document_items = ((deal.documents && deal.documents.items) || []).map(function (item) {
            return document_card({ label: item.document_type, document_type: item.document_type, uploaded: item.uploaded, complete: item.complete }, "hbr", deal.name);
        }).join("");
        target.innerHTML = '<div class="dcr-section-heading dcr-section-heading-first"><div><p class="dcr-eyebrow">Home request</p><h1>' + escape_html(deal.name) + '</h1><p class="dcr-muted">' + escape_html([deal.home_type, deal.financing_type, deal.property_type].filter(Boolean).join(" · ")) + '</p></div><span class="dcr-stage-chip ' + chip_class(deal.portal_status) + '">' + escape_html(deal.portal_status) + '</span></div>' +
            '<div class="dcr-account-grid"><article class="dcr-panel"><div class="dcr-panel-heading"><div><p class="dcr-eyebrow">Request</p><h2>Home details</h2></div></div><div class="dcr-account-row"><div><div class="dcr-account-name">Factory</div><div class="dcr-account-detail">' + escape_html(deal.factory && deal.factory.label || "Not selected") + '</div></div><span class="dcr-stage-chip ' + chip_class(deal.order_stage) + '">' + escape_html(deal.order_stage || "Pending") + '</span></div><div class="dcr-account-row"><div><div class="dcr-account-name">Quoted amount</div><div class="dcr-account-detail">' + escape_html(format_currency(deal.quoted_amount)) + '</div></div><span class="dcr-stage-chip">' + escape_html(deal.loan_stage || "Not started") + '</span></div>' + request_actions + '</article>' +
            '<article class="dcr-panel"><div class="dcr-panel-heading"><div><p class="dcr-eyebrow">Financing</p><h2>Loan summary</h2></div></div><div class="dcr-account-row"><div><div class="dcr-account-name">Principal</div><div class="dcr-account-detail">' + escape_html(format_currency(loan.principal)) + '</div></div></div><div class="dcr-account-row"><div><div class="dcr-account-name">Interest</div><div class="dcr-account-detail">' + escape_html(format_currency(loan.total_interest)) + (loan.interest_rate ? ' · ' + escape_html(loan.interest_rate) + '%' : '') + '</div></div></div><div class="dcr-account-row"><div><div class="dcr-account-name">Total payable</div><div class="dcr-account-detail">' + escape_html(format_currency(loan.total_payable)) + '</div></div><span class="dcr-stage-chip ' + chip_class(loan.status) + '">' + escape_html(loan.status || "Not started") + '</span></div></article></div>' +
            '<div class="dcr-subsection"><div class="dcr-section-heading"><div><p class="dcr-eyebrow">Checklist</p><h2>Documents for this request</h2></div><span class="dcr-muted dcr-small">' + escape_html((deal.documents && deal.documents.uploaded) || 0) + ' of ' + escape_html((deal.documents && deal.documents.required) || 0) + ' uploaded</span></div><div class="dcr-document-grid">' + document_items + '</div></div>';
    }

    function render_account() {
        var ach = state.data.ach || {};
        var accounts = ach.accounts || [];
        var ach_target = document.getElementById("dcr-ach-status");
        if (accounts.length) {
            ach_target.innerHTML = accounts.map(function (account) {
                return '<div class="dcr-account-row"><div><div class="dcr-account-name">' + escape_html(account.bank_name || "Connected bank") + ' ····' + escape_html(account.last4 || "") + '</div><div class="dcr-account-detail">' + escape_html(account.status || "Active") + (account.is_default ? " · Default" : "") + '</div></div><span class="dcr-stage-chip green">Connected</span></div>';
            }).join("");
        } else if (ach.available) {
            ach_target.innerHTML = '<p class="dcr-muted">Connect a bank account securely through Plaid. Your bank credentials are never stored by DCR.</p><button class="dcr-action-button" data-action="connect-ach">Connect bank account</button>';
        } else {
            ach_target.innerHTML = '<p class="dcr-muted">Bank connection is not available right now. DCR can help you complete auto-pay setup.</p>';
        }

        var signatures = state.data.signatures || [];
        document.getElementById("dcr-signatures").innerHTML = signatures.length ? signatures.map(function (item) {
            return '<div class="dcr-account-row"><div><div class="dcr-account-name">' + escape_html(item.document_type) + '</div><div class="dcr-account-detail">' + escape_html(item.status) + (item.sent_date ? " · Sent " + escape_html(format_date(item.sent_date)) : "") + '</div></div>' + (item.actionable ? '<button class="dcr-action-button" data-action="sign" data-signature="' + escape_html(item.name) + '">Review and sign</button>' : '<span class="dcr-stage-chip ' + chip_class(item.status) + '">' + escape_html(item.status) + '</span>') + '</div>';
        }).join("") : '<p class="dcr-muted">No documents are waiting for your signature.</p>';
    }

    function render() {
        var customer = state.data.customer || {};
        document.querySelectorAll("[data-customer-label]").forEach(function (node) { node.textContent = customer.label || "there"; });
        render_stats();
        render_deals();
        render_documents();
        render_account();
        render_deal_detail();
    }

    function populate_factories() {
        var select = document.querySelector("[data-factory-options]");
        if (!select) return;
        select.innerHTML = '<option value="">Choose an assigned factory</option>' + (state.data.factories || []).map(function (factory) {
            return '<option value="' + escape_html(factory.name) + '">' + escape_html(factory.label) + '</option>';
        }).join("");
    }

    async function reload() {
        try {
            state.data = await api("get_portal_context");
            render();
            loading.hidden = true;
            app.hidden = false;
            show_view(state.view);
        } catch (error) {
            loading.hidden = true;
            show_alert(error.message);
        }
    }

    function show_new_request() {
        var form = document.getElementById("dcr-hbr-form");
        form.reset();
        form.setAttribute("data-hbr-name", "");
        document.querySelector("[data-request-title]").textContent = "Start a home request";
        document.querySelector("[data-request-description]").textContent = "Save a draft as you gather details. Submit it to DCR for review when you are ready.";
        populate_factories();
        show_view("request");
    }

    function show_edit_request(deal) {
        var form = document.getElementById("dcr-hbr-form");
        var values = deal && deal.editable || {};
        form.reset();
        form.setAttribute("data-hbr-name", deal.name);
        document.querySelector("[data-request-title]").textContent = "Edit home request";
        document.querySelector("[data-request-description]").textContent = "Update this draft, save your changes, and submit it to DCR when the details are ready.";
        populate_factories();
        Array.prototype.forEach.call(form.elements, function (field) {
            if (!field.name || !Object.prototype.hasOwnProperty.call(values, field.name)) return;
            if (field.type === "checkbox") field.checked = Boolean(values[field.name]);
            else field.value = values[field.name] === null || values[field.name] === undefined ? "" : values[field.name];
        });
        show_view("request");
    }

    function download_document(button) {
        var params = new URLSearchParams({
            target_type: button.getAttribute("data-target-type") || "",
            target_name: button.getAttribute("data-target-name") || "",
            document_type: button.getAttribute("data-document-type") || "",
        });
        window.location.href = "/api/method/dcr.api.dealer_portal.download_document?" + params.toString();
    }

    root.addEventListener("click", async function (event) {
        var nav = event.target.closest("[data-view]");
        if (nav) {
            show_view(nav.getAttribute("data-view"));
            return;
        }
        var download = event.target.closest("[data-download]");
        if (download) {
            download_document(download);
            return;
        }
        var deal_card = event.target.closest("[data-deal]");
        if (deal_card) {
            try {
                state.currentDeal = await api("get_deal", { name: deal_card.getAttribute("data-deal") });
                render_deal_detail();
                show_view("deal");
            } catch (error) { show_alert(error.message); }
            return;
        }
        var action = event.target.closest("[data-action]");
        if (!action) return;
        var action_name = action.getAttribute("data-action");
        if (action_name === "new-request") { show_new_request(); return; }
        if (action_name === "edit-request") {
            if (state.currentDeal) show_edit_request(state.currentDeal);
            return;
        }
        if (action_name === "back-dashboard") { show_view("dashboard"); return; }
        if (action_name === "connect-ach") {
            try {
                var ach = await api("get_ach_setup_url");
                if (ach && ach.url) window.location.href = ach.url;
                else show_alert("Bank connection is not available right now.");
            } catch (error) { show_alert(error.message); }
            return;
        }
        if (action_name === "sign") {
            try {
                var signing = await api("start_signature", { signature_request: action.getAttribute("data-signature") });
                if (signing && signing.url) window.location.href = signing.url;
            } catch (error) { show_alert(error.message); }
            return;
        }
        if (action_name === "submit-review") {
            action.disabled = true;
            try {
                await api("submit_hbr_for_review", { name: action.getAttribute("data-hbr") });
                show_alert("Your request is now with DCR for review.");
                state.view = "dashboard";
                await reload();
            } catch (error) { action.disabled = false; show_alert(error.message); }
        }
    });

    root.addEventListener("change", async function (event) {
        var input = event.target.closest("input[type=file][data-upload-target]");
        if (!input || !input.files || !input.files.length) return;
        var label = input.closest(".dcr-upload-label");
        if (label) label.childNodes[0].nodeValue = "Uploading… ";
        try {
            await upload_file(input);
            show_alert("Document uploaded successfully.");
            await reload();
        } catch (error) {
            show_alert(error.message);
            if (label) label.childNodes[0].nodeValue = "Upload ";
        } finally {
            input.value = "";
        }
    });

    document.getElementById("dcr-hbr-form").addEventListener("submit", async function (event) {
        event.preventDefault();
        var form = event.target;
        var payload = {};
        var editing = Boolean(form.getAttribute("data-hbr-name"));
        Array.prototype.forEach.call(form.elements, function (field) {
            if (!field.name) return;
            if (field.type === "checkbox") payload[field.name] = field.checked ? 1 : 0;
            else if (editing || field.value !== "") payload[field.name] = field.value;
        });
        var submit = form.querySelector("button[type=submit]");
        submit.disabled = true;
        try {
            await api("save_hbr_draft", {
                payload: JSON.stringify(payload),
                name: form.getAttribute("data-hbr-name") || "",
            });
            show_alert("Draft saved. Add documents from the Documents tab, then submit it for review.");
            state.view = "dashboard";
            await reload();
        } catch (error) {
            show_alert(error.message);
            submit.disabled = false;
        }
    });

    reload();
})();
