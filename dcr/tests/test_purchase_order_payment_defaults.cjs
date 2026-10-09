const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
let handlers;
let pending = [];
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../public/js/email_preview.js'), 'utf8'), {
    __: text => text,
    frappe: {
        ui: { form: { on: (name, callbacks) => { handlers = callbacks; } } },
        db: { get_value: (...args) => pending.push(args) }
    }
});
function form(docstatus = 0) {
    return { doc: { docstatus, custom_home_build_request: 'HBR-A' },
        fields_dict: { custom_payment_type: {} }, custom_buttons: { 'Preview Email': {} },
        writes: [], set_value(name, value) { this.writes.push([name, value]); this.doc[name] = value; }
    };
}
for (const status of [1, 2]) {
    pending = [];
    const frm = form(status);
    handlers.refresh(frm);
    assert.equal(pending.length, 0, 'Opening a submitted/cancelled order must not fetch a draft default');
    assert.deepEqual(frm.writes, []);
}
for (const [financing, expected] of [['Cash', 'COD'], ['Floored', 'Flooring']]) {
    pending = [];
    const frm = form();
    handlers.custom_home_build_request(frm);
    pending[0][3]({ financing_type: financing });
    assert.equal(frm.doc.custom_payment_type, expected);
}
for (const mutate of [frm => { frm.doc.docstatus = 2; }, frm => { frm.doc.docstatus = 1; },
    frm => { frm.doc.custom_home_build_request = 'HBR-B'; },
    frm => { frm.doc.custom_payment_type = 'Staff override'; }]) {
    pending = [];
    const frm = form();
    handlers.custom_home_build_request(frm);
    mutate(frm);
    pending[0][3]({ financing_type: 'Cash' });
    assert.deepEqual(frm.writes, [], 'A late lookup must not overwrite current state or staff input');
}
console.log('PO payment defaults: draft Cash/Flooring, submitted/cancelled no-op, stale lookups and staff overrides passed');
