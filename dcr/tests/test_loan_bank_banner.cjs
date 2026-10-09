const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const calls = [];
const context = {
    __: (text, args = []) => text.replace(/\{(\d+)\}/g, (_, index) => args[index]),
    frappe: {
        ui: { form: { on() {} } },
        utils: { escape_html: value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;') },
        call: request => calls.push(request)
    }
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../public/js/loan.js'), 'utf8'), context);
function form() {
    return {
        doc: { name: 'Loan A', applicant: 'Dealer A' },
        headlines: [], bindings: [],
        dashboard: { clear_headline() {}, set_headline(text, color) { frm.headlines.push([text, color]); } },
        $wrapper: { find(selector) { return { on(event, callback) { frm.bindings.push({ selector, event, callback }); } }; } }
    };
}
let frm;
function response(message) {
    frm = form();
    context.show_autopay_indicator(frm);
    calls.pop().callback({ message });
    return frm.headlines.at(-1);
}
assert.deepEqual(response({ has_account: true, bank_name: 'Chase', account_last4: null }),
    ['Bank account: Chase (account number unavailable)', 'blue']);
for (const mask of [undefined, '', 'null', '123', '123456789', '<b>1234</b>']) {
    const [text] = response({ has_account: true, bank_name: 'Chase', account_last4: mask });
    assert.equal(text, 'Bank account: Chase (account number unavailable)');
}
assert.deepEqual(response({ has_account: true, bank_name: 'Chase', account_last4: '0123', status: 'Active' }),
    ['Bank account: Chase ending in 0123', 'blue']);
assert.equal(response({ has_account: true, bank_name: '<img src=x onerror=alert(1)>', account_last4: '1234' })[0],
    'Bank account: &lt;img src=x onerror=alert(1)&gt; ending in 1234');
assert.equal(response({ has_account: true, bank_name: '', account_last4: '1234' })[0], 'Bank account: Bank ending in 1234');
const [missing, color] = response({ has_account: false });
assert.match(missing, /Bank account: Not linked/);
assert.match(missing, /Resend Setup Email/);
assert.equal(color, 'orange');
assert.equal(frm.bindings.length, 1);
assert.equal(calls.length, 0, 'Opening the banner must not send an email');
frm = form();
context.show_autopay_indicator(frm);
const stale = calls.pop();
frm.doc.name = 'Loan B';
stale.callback({ message: { has_account: true, bank_name: 'Old Bank', account_last4: '1234' } });
assert.deepEqual(frm.headlines, [], 'Late responses must not label another loan');
console.log('Loan bank banner: missing/invalid masks, leading zeros, escaped bank names, linkage-only copy, no email on open and stale response passed');
