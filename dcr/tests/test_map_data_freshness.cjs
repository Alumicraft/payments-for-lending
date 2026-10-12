const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../public/js/map_block.js'), 'utf8');
const adapter = source.match(/    function callMapData\(method, callback\) \{[\s\S]*?\n    \}/);
assert.ok(adapter, 'map data adapter exists');
const methods = ['dcr.api.map.get_map_settings', 'dcr.api.map.get_heatmap_data',
    'dcr.api.map.get_factory_locations'];
let revision = 2;
const calls = [];
const context = {
    window: {_dcrMapPrefetch: Object.fromEntries(methods.map(method => [method, {message: {revision: 1}}]))},
    frappe: {call: ({method, callback}) => { calls.push(method); callback({message: {revision}}); }},
    setTimeout: callback => callback(),
};
vm.runInNewContext(adapter[0], context);
for (const current of [2, 3]) {
    revision = current;
    for (const method of methods) {
        let response;
        context.callMapData(method, value => { response = value; });
        assert.equal(response.message.revision, current,
            'map must see changes saved after Desk boot and after a previous map visit');
    }
}
assert.equal(calls.length, 6);
console.log('Map reads current settings, homes and factories on each load');
