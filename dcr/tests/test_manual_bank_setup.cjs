const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

let currentDialog;
let request;
let resolveRequest;
let rejectRequest;
const context = {
    __: text => text,
    frappe: {
        ui: {
            form: { on() {} },
            Dialog: class {
                constructor(options) {
                    Object.assign(this, options);
                    this.disabled = false;
                    this.cleared = [];
                    this.fields_dict = { account_number: { $input: { attr() {} } } };
                    currentDialog = this;
                }
                show() { this.visible = true; }
                hide() { this.visible = false; this.onhide(); }
                set_value(field, value) { this.cleared.push([field, value]); }
                get_primary_btn() { return { prop: (name, value) => { this.disabled = value; } }; }
            }
        },
        call(args) {
            request = args;
            return new Promise((resolve, reject) => { resolveRequest = resolve; rejectRequest = reject; });
        },
        show_alert() {}
    }
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../public/js/customer.js'), 'utf8'), context);

(async () => {
    let reloads = 0;
    const frm = { doc: { name: 'Synthetic Dealer' }, reload_doc: async () => { reloads++; } };
    const values = { bank_name: 'DCR Sandbox Test Bank', routing_number: '021000021', account_number: '123456789',
        account_type: 'Checking', check_type: 'Business', is_default: 0 };
    context.verify_dealer_bank_account(frm);
    const dialog = currentDialog;
    assert.equal(dialog.fields.find(field => field.fieldname === 'bank_name').reqd, 1);
    const pending = dialog.primary_action(values);
    assert.equal(dialog.disabled, true, 'Verification blocks duplicate clicks while the provider is pending');
    assert.equal(request.method, 'dcr.api.achq_integration.setup_bank_account');
    assert.equal(request.args.customer, 'Synthetic Dealer');
    assert.equal(request.args.bank_name, 'DCR Sandbox Test Bank');
    assert.equal(request.args.is_default, 0, 'Verification need not replace the default account');
    resolveRequest({ message: { success: true } });
    await pending;
    assert.equal(dialog.visible, false);
    assert.equal(dialog.disabled, false);
    assert.equal(reloads, 1);
    assert.deepEqual(dialog.cleared, [['account_number', ''], ['routing_number', '']]);

    context.verify_dealer_bank_account(frm);
    const failed = currentDialog;
    const retry = failed.primary_action(values);
    rejectRequest(new Error('Verification refused'));
    await assert.rejects(retry, /Verification refused/);
    assert.equal(failed.visible, true, 'A provider error keeps the form open for correction');
    assert.equal(failed.disabled, false);
    assert.deepEqual(failed.cleared, []);
    assert.equal(reloads, 1);
    failed.hide();
    assert.deepEqual(failed.cleared, [['account_number', ''], ['routing_number', '']]);
})();
