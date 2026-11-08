const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../public/js/loan_application.js'), 'utf8');

function trial({packet, signed, sent, stale = false}) {
    const lookups = [], buttons = [], indicators = [];
    const frm = {doc: {name: 'AMENDMENT', docstatus: 1, home_build_request: 'HOME', signed_packet: packet},
        is_new: () => false, page: {set_indicator: (text) => indicators.push(text)},
        add_custom_button: (label) => buttons.push(label)};
    const context = {__: (x) => x, frappe: {ui: {form: {on() {}}}, db: {get_value: (...args) => lookups.push(args)}}};
    vm.createContext(context);
    vm.runInContext(source, context);
    context.refresh_flooring_signature(frm);
    if (stale) frm.doc.name = 'ANOTHER';
    for (let i = 0; i < lookups.length; i++) {
        const [doctype, filters, fields, done] = lookups[i];
        assert.equal(doctype, 'Signature Request');
        assert.equal(filters.reference_name, 'AMENDMENT');
        assert.equal(filters.reference_doctype, 'Loan Application');
        if (filters.status === 'Signed') {
            assert.equal(filters.signed_attachment, packet);
            done(signed ? {name: 'OWN-SIGNED'} : {});
        } else {
            assert.equal(filters.status, 'Sent');
            done(sent ? {name: 'OWN-SENT'} : {});
        }
    }
    return {frm, buttons, indicators};
}

const inherited = trial({packet: '/private/old.pdf', signed: false});
assert.deepEqual(inherited.buttons, ['Flooring Packet']);
assert.equal(inherited.frm.dcr_packet_signed, false);
assert(!inherited.indicators.includes('Signed'));
const owned = trial({packet: '/private/own.pdf', signed: true});
assert.deepEqual(owned.buttons, []);
assert.equal(owned.frm.dcr_packet_signed, true);
assert.deepEqual(owned.indicators, ['Signed']);
assert(trial({packet: null, sent: true}).indicators.includes('Awaiting Signature'));
assert.deepEqual(trial({packet: '/private/old.pdf', stale: true}).buttons, []);
console.log('Inherited files do not certify amendments or hide their packet action.');
