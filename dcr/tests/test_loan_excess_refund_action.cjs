const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

let handlers;
let allowed = true;
const opened = [];
const context = {
    __: text => text,
    dcr: { update_dated_loan_preview() {} },
    frappe: {
        ui: { form: { on(doctype, events) { handlers = events; } } },
        model: { can_create: doctype => doctype === 'Loan Refund' && allowed },
        db: { count: () => Promise.resolve(0) },
        call() {},
        new_doc: (doctype, values) => opened.push({ doctype, values })
    }
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../public/js/loan.js'), 'utf8'), context);

function refresh(changes = {}) {
    const buttons = [];
    const removed = [];
    const frm = {
        doc: {
            name: 'LOAN-DEMO', docstatus: 1, status: 'Disbursed',
            home_build_request: 'HBR-DEMO', original_financed_principal: 225000,
            excess_amount_paid: 100, total_payment: 333494.25, total_principal_paid: 220500,
            company: 'DCR', applicant_type: 'Customer', applicant: 'DEALER-DEMO',
            loan_product: 'Standard', payment_account: 'Trust Bank', ...changes
        },
        is_new: () => false,
        dashboard: { clear_headline() {} },
        add_custom_button: (label, callback, group) => buttons.push({ label, callback, group }),
        remove_custom_button: (label, group) => removed.push({ label, group })
    };
    handlers.refresh(frm);
    return { frm, removed, refund: buttons.find(button => button.label === 'Loan Refund') };
}

const current = refresh();
assert.ok(current.refund, 'Actual excess must offer a refund despite larger forecast totals');
assert.equal(current.refund.group, 'Create');
assert.ok(current.removed.some(button => button.label === 'Loan Refund' && button.group === 'Create'));
current.refund.callback();
assert.equal(opened[0].doctype, 'Loan Refund');
assert.equal(opened[0].values.loan, 'LOAN-DEMO');
assert.equal(opened[0].values.refund_amount, 100);
assert.equal(opened[0].values.is_excess_amount_refund, 1);
assert.equal(opened[0].values.refund_account, 'Trust Bank');
assert.equal(opened[0].values.value_date, undefined, 'Staff must choose the actual refund value date');

for (const excess_amount_paid of [0, -1, null, undefined, NaN, Infinity]) {
    assert.equal(refresh({ excess_amount_paid }).refund, undefined);
}
assert.ok(refresh({ status: 'Closed' }).refund, 'Cancelled refund may leave a closed loan with excess');
assert.equal(refresh({ docstatus: 0 }).refund, undefined);
assert.equal(refresh({ home_build_request: null }).refund, undefined);
assert.equal(refresh({ original_financed_principal: 0 }).refund, undefined);
allowed = false;
assert.equal(refresh().refund, undefined);
console.log('Loan excess refund action: real balance, native draft and scope/permission checks passed');
