const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require('node:path').join(__dirname, '../public/js/loan.js'), 'utf8');
const calls = [];
let prompt;
const context = {
  __: (text) => text,
  frappe: {
    ui: { form: { on() {} } },
    datetime: { get_today: () => '2026-11-07' },
    prompt: (fields, done) => { prompt = { fields, done }; },
    confirm: (message, done) => done(),
    call: (request) => calls.push(request),
  },
};
vm.createContext(context);
vm.runInContext(source, context);
context.send_payoff({ doc: { name: 'LOAN', applicant: 'DEALER' } }, 'Flooring');
assert.equal(calls.length, 0, 'Sending waits for a selected quote date');
assert.equal(prompt.fields[0].default, '2026-11-07');
prompt.done({ quote_date: '2028-01-15' });
assert.equal(calls[0].args.quote_date, '2028-01-15');
assert.equal(calls[0].args.loan, 'LOAN');
context.send_payoff({ doc: { name: 'LOAN', applicant: 'DEALER', payoff_date: '2028-02-15' } }, 'Flooring');
assert.equal(prompt.fields[0].default, '2028-02-15');
context.send_payoff({ doc: { name: 'CASH', applicant: 'DEALER' } }, 'COD');
assert.equal(calls[1].args.payoff_type, 'COD');
assert.equal(calls[1].args.quote_date, undefined);
console.log('Payoff action preserves the selected date and COD behavior.');
