// Saving an assignment and viewing it never send the retailer packet.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
let handler;
let confirmation;
const calls = [];
const frappe = {
    ui: { form: { on: (doctype, callbacks) => { handler = callbacks; } } },
    confirm: (message, callback) => { confirmation = callback; },
    call: (request) => { calls.push(request); },
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../public/js/factory_assignment.js"), "utf8"), { frappe, __: (value) => value });
function buttons(docstatus, status) {
    const buttons = new Map();
    handler.refresh({ doc: { name: "FA-A", factory: "FACTORY-A", docstatus, retailer_application_status: status },
        add_custom_button: (label, callback) => { buttons.set(label, callback); }, change_custom_button_type: () => {}, reload_doc: () => {} });
    return buttons;
}
assert.equal(buttons(0, "Not Submitted").size, 0);
assert.equal(buttons(1, "Approved").has("Send Retailer Application"), false);
assert.equal(buttons(1, "Submitted").has("Send Retailer Application"), false);
const ready = buttons(1, "Not Submitted");
assert.equal(calls.length, 0);
ready.get("Send Retailer Application")();
assert.equal(calls.length, 0, "clicking the button first requires the dealer-document send confirmation");
confirmation();
assert.equal(calls.length, 1);
assert.equal(calls[0].method, "dcr.api.factory_packets.send_packet");
assert.equal(calls[0].args.name, "FA-A");
console.log("Factory packet action: no automatic sends, status gating, explicit confirmation and named assignment passed");
