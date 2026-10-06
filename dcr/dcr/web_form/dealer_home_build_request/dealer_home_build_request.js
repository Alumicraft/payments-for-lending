frappe.ready(function () {
    const form = frappe.web_form;
    const pending = new Map();
    const existing = new Map();
    let uploading = false;
    let needsRefresh = false;
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
    const nativeValidate = form.validate;
    form.validate = function () {
        if (uploading) return false;
        if (needsRefresh) {
            uploading = true;
            refreshSaved(form.doc.name).then(async () => {
                needsRefresh = false;
                await renderDocuments();
                message.textContent = "Saved request refreshed. Save again to retry selected files.";
            }).catch(() => {
                message.textContent = "The saved request could not refresh. Try Save again, or open the saved request below.";
            }).finally(() => { uploading = false; });
            return false;
        }
        return nativeValidate ? nativeValidate.call(form) : undefined;
    };
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
            table.innerHTML = '<thead><tr><th>Document</th><th>File</th><th>Action</th></tr></thead><tbody></tbody>';
            for (const type of docs) {
                const row = document.createElement("tr");
                const saved = existing.get(type);
                row.innerHTML = '<td>' + escape(type) + '</td><td class="dcr-selected-file">' + escape(pending.get(type)?.name || (saved?.uploaded ? "Uploaded" : saved?.complete ? "Complete" : "Needed")) + '</td><td></td>';
                const cell = row.lastElementChild;
                if (saved?.uploaded && form.doc.name) {
                    const view = document.createElement("a");
                    const params = new URLSearchParams({target_type:"hbr", target_name:form.doc.name, document_type:type});
                    view.href = "/api/method/dcr.api.dealer_portal.download_document?" + params;
                    view.textContent = "View";
                    view.target = "_blank";
                    view.rel = "noopener";
                    cell.append(view);
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
            section.textContent = "The document checklist could not load. Save the request, then open it from Home to add documents.";
        }
    }
    async function refreshSaved(name) {
        const result = await frappe.call({method:"dcr.api.dealer_portal.get_deal", args:{name}});
        form.doc.modified = result.message.modified;
        existing.clear();
        for (const item of result.message.documents.items) existing.set(item.document_type, item);
    }
    form.handle_success = async function (saved) {
        form.doc.name = saved.name;
        form.is_new = false;
        form.in_edit_mode = true;
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
            form.make_form_dirty();
            return;
        }
        window.location.assign(requestUrl(saved.name));
    };
    form.get_discard_url = function () { return "/portal"; };
    for (const field of ["home_type", "financing_type", "property_type"]) form.on(field, renderDocuments);
    if (form.doc.name) refreshSaved(form.doc.name).then(renderDocuments).catch(renderDocuments);
    else renderDocuments();
});
