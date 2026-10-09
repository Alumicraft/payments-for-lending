const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

for (const [file, setter] of [['loan_application.js', 'set_calculated_value'], ['loan.js', 'set_loan_calculated_value']]) {
    const context = {frappe: {ui: {form: {on() {}}}}};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../public/js', file), 'utf8'), context);
    const frm = {
        doc: {custom_projected_equity: 0, custom_projected_ltv: 0},
        fields_dict: {
            custom_projected_equity: {df: {fieldtype: 'Currency'}},
            custom_projected_ltv: {df: {fieldtype: 'Percent'}},
            note: {df: {fieldtype: 'Data'}}
        },
        changes: [],
        set_value(field, value) { this.changes.push([field, value]); this.doc[field] = value; }
    };
    // Frappe reloads empty Currency/Percent fields as 0. The unknown preview
    // must not change them back to null on every refresh/save cycle.
    for (let cycle = 0; cycle < 3; cycle++) {
        for (const field of ['custom_projected_equity', 'custom_projected_ltv']) {
            context[setter](frm, field, null);
            frm.doc[field] = Number(frm.doc[field] || 0);
        }
    }
    assert.deepEqual(frm.changes, [], `${file}: a saved draft with empty projections must stay clean`);
    frm.doc.custom_projected_equity = 5000;
    context[setter](frm, 'custom_projected_equity', null);
    assert.deepEqual(frm.changes, [['custom_projected_equity', null]], 'A stale nonzero forecast must still clear');
    frm.doc.custom_projected_equity = 0;
    frm.changes = [];
    context[setter](frm, 'custom_projected_equity', 10000);
    assert.deepEqual(frm.changes, [['custom_projected_equity', 10000]], 'Known forecasts still update');
    frm.doc.note = '0';
    context[setter](frm, 'note', null);
    assert.deepEqual(frm.changes.at(-1), ['note', null], 'Text zero is not an empty numeric forecast');
}
console.log('Loan draft save: numeric empty round trips stay clean; stale and known forecasts still update');
