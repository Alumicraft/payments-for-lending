const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const handlers = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../public/js/flooring_loan_display.js'), 'utf8'), {
    frappe: { ui: { form: { on: (doctype, callbacks) => { handlers[doctype] = callbacks; } } } }
});
const forecasts = ['total_payable_interest', 'total_interest_payable', 'total_payable_amount', 'total_payment'];
function form(doctype, status = 1) {
    const fields = forecasts.concat(['loan_amount', 'qualifying_amount', 'rate_of_interest',
        'monthly_repayment_amount', 'total_amount_paid', 'total_principal_paid']);
    return {
        doc: { doctype, docstatus: status, home_build_request: 'HBR A', total_interest_payable: 12000, total_payment: 112000 },
        fields_dict: Object.fromEntries(fields.map(name => [name, { df: {
            fieldtype: 'Currency', read_only: 1, hidden: 0, depends_on: 'is_term_loan'
        } }])),
        set_df_property(name, property, value) { this.fields_dict[name].df[property] = value; },
        set_value() { throw new Error('Visibility must not write financial values'); },
        dirty() { throw new Error('Opening a saved document must stay clean'); },
        layout: { refresh_dependency() {} }
    };
}
for (const doctype of ['Loan', 'Loan Application']) {
    for (const status of [0, 1, 2]) {
        const frm = form(doctype, status);
        const before = JSON.stringify(frm.doc);
        handlers[doctype].refresh(frm);
        handlers[doctype].refresh(frm);
        for (const name of forecasts) {
            assert.equal(frm.fields_dict[name].df.hidden, 1);
            assert.equal(frm.fields_dict[name].df.depends_on, 'eval:false');
        }
        for (const name of ['loan_amount', 'rate_of_interest', 'monthly_repayment_amount', 'total_amount_paid', 'total_principal_paid']) {
            assert.equal(frm.fields_dict[name].df.hidden, 0);
        }
        assert.equal(JSON.stringify(frm.doc), before);
        frm.doc.home_build_request = null;
        handlers[doctype].home_build_request(frm);
        for (const name of forecasts) {
            assert.equal(frm.fields_dict[name].df.hidden, 0);
            assert.equal(frm.fields_dict[name].df.depends_on, 'is_term_loan');
        }
    }
    for (const change of [{reqd: 1}, {mandatory_depends_on: 'eval:doc.needs_forecast'}, {read_only: 0}, {fieldtype: 'Data'}]) {
        const frm = form(doctype);
        Object.assign(frm.fields_dict.total_payment.df, change);
        handlers[doctype].refresh(frm);
        assert.equal(frm.fields_dict.total_payment.df.hidden, 0, 'Required or editable site fields remain usable');
    }
    const nativeHidden = form(doctype);
    nativeHidden.fields_dict.total_payment.df.hidden = 1;
    handlers[doctype].refresh(nativeHidden);
    nativeHidden.doc.home_build_request = null;
    handlers[doctype].home_build_request(nativeHidden);
    assert.equal(nativeHidden.fields_dict.total_payment.df.hidden, 1);
    const unlinked = form(doctype); delete unlinked.doc.home_build_request;
    handlers[doctype].refresh(unlinked);
    assert.equal(unlinked.fields_dict.total_payment.df.hidden, 0);
}
const application = fs.readFileSync(path.join(__dirname, '../public/js/loan_application.js'), 'utf8');
const forcedFields = application.slice(application.indexOf('// Force-show'), application.indexOf('// Submitted applications'));
assert.doesNotMatch(forcedFields, /total_payable_amount|total_payable_interest/, 'Refresh must not force hidden forecasts visible again');
console.log('Home-financing display: draft/submitted/cancelled, required/editable fields, non-home restoration, native-hidden state and no data writes passed');
