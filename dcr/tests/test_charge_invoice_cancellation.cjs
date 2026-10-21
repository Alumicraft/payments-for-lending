const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
let refresh;
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../public/js/charge_invoice_cancellation.js'), 'utf8'), {
    frappe: {ui: {form: {on(doctype, handlers) {
        assert.equal(doctype, 'Sales Invoice');
        refresh = handlers.refresh;
    }}}}
});
const frm = {
    doc: {__onload: {dcr_cancel_charge_demands_with_invoice: true}},
    ignore_doctypes_on_cancel_all: ['GL Entry'],
    set_value() { throw new Error('Opening an invoice must not change it'); }
};
const original = JSON.stringify(frm.doc);
refresh(frm);
refresh(frm);
assert.deepEqual(Array.from(frm.ignore_doctypes_on_cancel_all), ['GL Entry', 'Loan Demand']);
assert.equal(JSON.stringify(frm.doc), original);
frm.doc = {};
refresh(frm);
assert.deepEqual(Array.from(frm.ignore_doctypes_on_cancel_all), ['GL Entry']);
const nativeIgnored = {doc: {__onload: {dcr_cancel_charge_demands_with_invoice: true}},
    ignore_doctypes_on_cancel_all: ['Loan Demand', 'Payment Entry']};
refresh(nativeIgnored);
nativeIgnored.doc = {};
refresh(nativeIgnored);
assert.deepEqual(nativeIgnored.ignore_doctypes_on_cancel_all, ['Loan Demand', 'Payment Entry']);
console.log('Charge invoice cancellation: owned demand handling, other links retained, no writes and record switching passed');
