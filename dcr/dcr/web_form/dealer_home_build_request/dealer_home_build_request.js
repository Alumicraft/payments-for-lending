frappe.ready(function () {
    const form = frappe.web_form;
    const pending = new Map();
    const existing = new Map();
    let uploading = false;
    let needsRefresh = false;
    let savedValues = null;
    let generation = 0;
    const section = document.createElement("section");
    section.className = "dcr-form-documents";
    section.setAttribute("aria-label", "Request documents");
    const footer = document.querySelector(".web-form-footer");
    if (footer) footer.before(section);
    else document.querySelector(".web-form").append(section);
    const escape = value => String(value || "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
    const requestUrl = name => "/portal?request=" + encodeURIComponent(name);
    const message = document.createElement("p");
    message.setAttribute("role", "status");
    let allowLeave = false;
    let leaveDialogOpen = false;
    const fieldSnapshot = () => JSON.stringify(Array.from(document.querySelectorAll(
        ".web-form input[data-fieldname], .web-form select[data-fieldname], .web-form textarea[data-fieldname]"
    )).map(input => [input.getAttribute("data-fieldname"), input.type === "checkbox" ? input.checked : input.value]));
    let cleanSnapshot = fieldSnapshot();
    // Native make() applies initial values in promise callbacks. Capture the
    // settled inputs, without swallowing an edit made before that callback.
    let editedBeforeBaseline = false;
    document.addEventListener("input", event => {
        if (event.target.closest(".web-form")) editedBeforeBaseline = true;
    }, true);
    setTimeout(() => { if (!editedBeforeBaseline) cleanSnapshot = fieldSnapshot(); }, 0);
    const hasUnsavedWork = () => uploading || !!window.saving || needsRefresh || pending.size > 0 || fieldSnapshot() !== cleanSnapshot;
    const leave = url => { allowLeave = true; frappe.form_dirty = false; window.location.assign(url); };
    function confirmLeave(url) {
        if (uploading || window.saving) {
            frappe.msgprint("Please wait for the request and selected files to finish saving.");
            return;
        }
        if (allowLeave || !hasUnsavedWork()) { leave(url); return; }
        if (leaveDialogOpen) return;
        leaveDialogOpen = true;
        // Use Frappe's own warning dialog for both header links and Discard.
        // The confirmed navigation bypasses beforeunload, avoiding two prompts.
        const dialog = frappe.warn("Discard changes?", "Your unsaved changes and selected files will be lost.",
            () => { leaveDialogOpen = false; leave(url); }, "Discard");
        // Closing/cancelling the native dialog must permit the next attempt.
        if (dialog) {
            const onHide = dialog.onhide;
            dialog.onhide = function () { leaveDialogOpen = false; if (onHide) onHide.call(this); };
        }
    }
    window.addEventListener("beforeunload", event => {
        if (allowLeave || !hasUnsavedWork()) return;
        event.preventDefault();
        event.returnValue = "";
    });
    document.addEventListener("click", event => {
        const link = event.target.closest(".dcr-portal-header a");
        if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        confirmLeave(link.href);
    });
    form.discard_form = function () { confirmLeave(form.get_discard_url()); return false; };

    function nameNativeControls() {
        document.querySelectorAll(".web-form .frappe-control").forEach(wrapper => {
            const label = wrapper.querySelector(".control-label") || wrapper.querySelector("label");
            const help = wrapper.querySelector(".help-box");
            wrapper.querySelectorAll("input:not([type=hidden]), select, textarea").forEach((input, index) => {
                const fieldname = input.getAttribute("data-fieldname");
                if (!fieldname) return;
                const id = "dcr-field-" + fieldname + "-" + index;
                if (!input.id) input.id = id;
                if (label) {
                    if (!label.id) label.id = "dcr-label-" + fieldname;
                    label.setAttribute("for", input.id);
                    input.setAttribute("aria-labelledby", label.id);
                    input.setAttribute("aria-required", String(label.classList.contains("reqd") || !!form.fields_dict?.[fieldname]?.df?.reqd));
                } else if (form.fields_dict?.[fieldname]?.df?.label) {
                    input.setAttribute("aria-label", form.fields_dict[fieldname].df.label);
                }
                if (help && help.textContent.trim()) {
                    if (!help.id) help.id = "dcr-help-" + fieldname;
                    const descriptions = new Set((input.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean));
                    descriptions.add(help.id);
                    input.setAttribute("aria-describedby", Array.from(descriptions).join(" "));
                }
                input.setAttribute("aria-invalid", String(wrapper.classList.contains("has-error") || !!form.fields_dict?.[fieldname]?.df?.invalid));
            });
        });
    }
    nameNativeControls();
    const heading = document.querySelector(".web-form-title h1");
    let requestIdentity;
    function showRequestIdentity() {
        if (!heading) return;
        heading.textContent = form.doc.name ? "Edit home request" : "New home request";
        document.title = heading.textContent + " · Dealer Portal";
        if (form.doc.name) {
            if (!requestIdentity) {
                requestIdentity = document.createElement("p");
                requestIdentity.className = "dcr-native-request-id";
                heading.after(requestIdentity);
            }
            requestIdentity.textContent = form.doc.name;
        }
    }
    showRequestIdentity();
    const accessibleForm = document.querySelector(".web-form");
    if (accessibleForm) new MutationObserver(nameNativeControls).observe(accessibleForm, {
        subtree: true, childList: true, attributes: true, attributeFilter: ["class"]
    });
    const nativeValidate = form.validate;
    async function recoverSaved() {
        if (uploading) return;
        uploading = true;
        try {
            await refreshSaved(form.doc.name);
            needsRefresh = false;
            await renderDocuments();
            document.querySelectorAll(".web-form-footer button").forEach(button => { button.disabled = false; });
            message.textContent = "Saved request refreshed. Save again to retry selected files.";
        } catch (error) {
            message.textContent = error.requestChanged ? error.message : "The saved request could not refresh. Try Refresh saved request again, or open the saved request below.";
        } finally { uploading = false; }
    }
    form.validate = function () {
        if (uploading) return false;
        if (needsRefresh) {
            recoverSaved();
            frappe.throw("Your request is saved. Its latest version needs to refresh before another save. Please wait, then Save again to retry your files.");
        }
        return nativeValidate ? nativeValidate.call(form) : undefined;
    };
    const nativeForm = document.querySelector(".web-form");
    if (nativeForm) nativeForm.addEventListener("submit", event => {
        if (!uploading && !needsRefresh) return;
        // Block implicit Enter submissions too; a thrown validation hook must
        // never fall through to a browser reload and discard selected files.
        event.preventDefault();
        event.stopImmediatePropagation();
        if (needsRefresh && !uploading) recoverSaved();
    }, true);
    async function renderDocuments() {
        const revision = ++generation;
        try {
            const result = await frappe.call({
                method: "dcr.dcr.doctype.home_build_request.home_build_request.get_required_docs",
                args: {home_type: form.get_value("home_type"), financing_type: form.get_value("financing_type"), property_type: form.get_value("property_type")}
            });
            if (revision !== generation) return;
            const docs = result.message || [];
            for (const key of pending.keys()) if (!docs.includes(key)) pending.delete(key);
            section.innerHTML = '<h2>Documents</h2><p>PDF, Word or image, up to 10 MB. Selected files upload when you save.</p>';
            if (!docs.length) {
                section.insertAdjacentHTML("beforeend", '<p>Choose the home, deal and property types to see the required documents.</p>');
                return;
            }
            const table = document.createElement("table");
            table.innerHTML = '<thead><tr><th scope="col">Document</th><th scope="col">File</th><th scope="col">Action</th></tr></thead><tbody></tbody>';
            for (const type of docs) {
                const row = document.createElement("tr");
                const saved = existing.get(type);
                row.innerHTML = '<th scope="row">' + escape(type) + '</th><td class="dcr-selected-file">' + escape(pending.get(type)?.name || (saved?.uploaded ? saved.file_name || "Uploaded" : saved?.complete ? "Not required" : "Needed")) + '</td><td></td>';
                const cell = row.lastElementChild;
                if (saved?.uploaded && form.doc.name) {
                    const view = document.createElement("a");
                    const params = new URLSearchParams({target_type:"hbr", target_name:form.doc.name, document_type:type});
                    view.href = "/api/method/dcr.api.dealer_portal.download_document?" + params;
                    view.textContent = "View";
                    view.setAttribute("aria-label", "View " + type);
                    view.target = "_blank";
                    view.rel = "noopener";
                    cell.append(view);
                    const download = document.createElement("a");
                    download.href = view.href;
                    download.textContent = "Download";
                    download.setAttribute("download", "");
                    download.setAttribute("aria-label", "Download " + type);
                    cell.append(download);
                }
                if (form.is_new || form.in_edit_mode) {
                    const label = document.createElement("label");
                    label.className = "dcr-file-select";
                    label.append(document.createTextNode(pending.has(type) || saved?.uploaded ? "Replace file" : "Choose file"));
                    const input = document.createElement("input");
                    input.type = "file";
                    input.accept = ".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp";
                    input.setAttribute("aria-label", "Choose " + type);
                    input.addEventListener("change", () => {
                        const file = input.files[0];
                        if (!file) return;
                        if (file.size === 0 || file.size > 10 * 1024 * 1024 || !/\.(pdf|docx?|png|jpe?g|webp)$/i.test(file.name)) {
                            message.textContent = "Choose a PDF, Word document or image that is not empty and is 10 MB or smaller.";
                            input.value = "";
                            return;
                        }
                        pending.set(type, file);
                        row.querySelector(".dcr-selected-file").textContent = file.name;
                        form.make_form_dirty();
                        message.textContent = "Selected files will upload when you save.";
                    });
                    label.append(input);
                    cell.append(label);
                }
                table.querySelector("tbody").append(row);
            }
            section.append(table, message);
        } catch (_) {
            section.textContent = "The document checklist could not load. Check your connection and try again.";
            section.append(message);
            const retry = document.createElement("button");
            retry.type = "button";
            retry.className = "btn btn-default btn-sm";
            retry.textContent = "Retry checklist";
            retry.addEventListener("click", renderDocuments);
            section.append(retry);
        }
    }
    async function refreshSaved(name) {
        const result = await frappe.call({method:"dcr.api.dealer_portal.get_deal", args:{name}});
        if (savedValues) {
            const record = result.message;
            const comparable = (key, value) => {
                const type = form.fields_dict?.[key]?.df?.fieldtype;
                if (["Currency", "Float", "Int", "Percent", "Check"].includes(type) || typeof value === "number" || typeof savedValues[key] === "number") return Number(value || 0);
                return String(value || "");
            };
            if (!record.editable || Object.keys(record.editable).some(key => key in savedValues && comparable(key, record.editable[key]) !== comparable(key, savedValues[key]))) {
                const error = new Error("The saved request changed or is now locked. Open the saved request again before saving more changes.");
                error.requestChanged = true;
                throw error;
            }
        }
        form.doc.modified = result.message.modified;
        existing.clear();
        for (const item of result.message.documents.items) existing.set(item.document_type, item);
    }
    form.handle_success = async function (saved) {
        form.doc.name = saved.name;
        // A partially failed upload is already an existing request. Make its
        // identity visible immediately, without requiring a reload.
        showRequestIdentity();
        form.is_new = false;
        form.in_edit_mode = true;
        savedValues = Object.assign({}, form.doc);
        cleanSnapshot = fieldSnapshot();
        // Reloads after partial upload failure must reopen this saved record,
        // rather than showing a blank /new form that creates a duplicate.
        window.history.replaceState(null, "", "/dealer-home-request/" + encodeURIComponent(saved.name) + "/edit");
        uploading = true;
        const controls = Array.from(document.querySelectorAll(".web-form input, .web-form select, .web-form textarea"));
        const wasDisabled = controls.map(control => control.disabled);
        controls.forEach(control => { control.disabled = true; });
        const buttons = document.querySelectorAll(".web-form-footer button");
        buttons.forEach(button => { button.disabled = true; });
        let failed = 0;
        for (const [type, file] of Array.from(pending)) {
            message.textContent = "Request saved. Uploading " + type + "…";
            try {
                const data = new FormData();
                data.append("file", file);
                data.append("target_type", "hbr");
                data.append("target_name", saved.name);
                data.append("document_type", type);
                const response = await fetch("/api/method/dcr.api.dealer_portal.upload_document", {
                    method:"POST", credentials:"same-origin", headers:{"X-Frappe-CSRF-Token":frappe.csrf_token}, body:data
                });
                if (!response.ok) throw new Error("Upload failed");
                const result = await response.json();
                if (!result.message?.uploaded) throw new Error("Upload failed");
                pending.delete(type);
            } catch (_) { failed++; }
        }
        uploading = false;
        controls.forEach((control, index) => { control.disabled = wasDisabled[index]; });
        buttons.forEach(button => { button.disabled = false; });
        if (failed) {
            try { await refreshSaved(saved.name); needsRefresh = false; } catch (_) { needsRefresh = true; }
            await renderDocuments();
            message.textContent = "Request saved. " + failed + " file(s) could not upload. Save again to retry, or open the request from Home.";
            const open = document.createElement("a");
            open.href = requestUrl(saved.name);
            open.textContent = "Open saved request";
            section.append(open);
            if (needsRefresh) {
                buttons.forEach(button => { button.disabled = true; });
                message.textContent = "Request saved. Some files could not upload, and its latest version could not refresh. Refresh the saved request before retrying.";
                const retry = document.createElement("button");
                retry.type = "button";
                retry.className = "dcr-btn";
                retry.textContent = "Refresh saved request";
                retry.addEventListener("click", recoverSaved);
                section.append(retry);
            }
            form.make_form_dirty();
            return;
        }
        leave(requestUrl(saved.name));
    };
    form.get_discard_url = function () { return "/portal"; };
    for (const field of ["home_type", "financing_type", "property_type"]) form.on(field, renderDocuments);
    if (form.doc.name) refreshSaved(form.doc.name).then(renderDocuments).catch(renderDocuments);
    else renderDocuments();
});
