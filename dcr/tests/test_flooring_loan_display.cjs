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
const nativePaymentRule = 'eval: doc.is_term_loan && doc.repayment_schedule_type != "Line of Credit"';
const paymentForm = form('Loan');
paymentForm.fields_dict.monthly_repayment_amount.df.depends_on = nativePaymentRule;
handlers.Loan.refresh(paymentForm);
assert.equal(paymentForm.fields_dict.monthly_repayment_amount.df.depends_on, 'eval:true');
paymentForm.doc.home_build_request = null;
handlers.Loan.home_build_request(paymentForm);
assert.equal(paymentForm.fields_dict.monthly_repayment_amount.df.depends_on, nativePaymentRule);
const customPayment = form('Loan');
customPayment.fields_dict.monthly_repayment_amount.df.depends_on = 'eval:doc.custom_approval';
handlers.Loan.refresh(customPayment);
assert.equal(customPayment.fields_dict.monthly_repayment_amount.df.depends_on, 'eval:doc.custom_approval');
const hiddenPayment = form('Loan');
hiddenPayment.fields_dict.monthly_repayment_amount.df.hidden = 1;
hiddenPayment.fields_dict.monthly_repayment_amount.df.depends_on = nativePaymentRule;
handlers.Loan.refresh(hiddenPayment);
assert.equal(hiddenPayment.fields_dict.monthly_repayment_amount.df.depends_on, nativePaymentRule);
function columnForm(extra = [], heading = '') {
    const frm = form('Loan');
    const parent = {};
    const column = { df: { hidden: 0, label: heading }, form: { get: () => parent }, refreshes: 0,
        refresh() { this.refreshes++; } };
    const contents = ['total_interest_payable', 'total_payment'].map(name => {
        const field = frm.fields_dict[name]; field.df.fieldname = name; field.parent = parent; return field;
    });
    frm.layout.sections_dict = { totals: { columns: [column], fields_list: contents.concat(extra.map(name => ({
        df: { fieldname: name }, parent
    }))) } };
    return { frm, column };
}
const collapsed = columnForm();
handlers.Loan.refresh(collapsed.frm);
assert.equal(collapsed.column.df.hidden, 1);
assert.equal(collapsed.column.refreshes, 1);
handlers.Loan.refresh(collapsed.frm);
assert.equal(collapsed.column.refreshes, 1);
collapsed.frm.fields_dict.total_payment.df.reqd = 1;
handlers.Loan.refresh(collapsed.frm);
assert.equal(collapsed.column.df.hidden, 0, 'A required field restores its column');
const restored = columnForm();
handlers.Loan.refresh(restored.frm);
restored.frm.doc.home_build_request = null;
handlers.Loan.home_build_request(restored.frm);
assert.equal(restored.column.df.hidden, 0);
for (const fixture of [columnForm(['custom_note']), columnForm([], 'Important figures')]) {
    handlers.Loan.refresh(fixture.frm);
    assert.equal(fixture.column.df.hidden, 0, 'Custom controls and headings retain column space');
}
