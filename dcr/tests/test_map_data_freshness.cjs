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

function sourceFunction(name) {
    const match = source.match(new RegExp('    function ' + name + '\\([^)]*\\) \\{[\\s\\S]*?\\n    \\}'));
    assert.ok(match, name + ' exists');
    return match[0];
}
const refreshed = [];
const existingMap = {
    getSource: name => ({setData: value => refreshed.push({name, value})}),
    addSource: () => { throw new Error('must update an existing source instead of adding it again'); },
};
let homes = [{latitude:37.38, longitude:-122.04, address:'125 North Mary Avenue',
    space_number:'UPDATED', homes:[{name:'HBR-36', status:'Pending'}]}];
const refreshContext = {
    window: {},
    _searchDataLoaded: {},
    callMapData: (method, callback) => callback({message: homes}),
    buildSearchIndex: () => {},
    buildLegend: () => {},
};
vm.runInNewContext(sourceFunction('loadData'), refreshContext);
refreshContext.loadData(existingMap);
assert.equal(refreshed[0].value.features[0].properties.space_number, 'UPDATED');
homes = [];
refreshContext.loadData(existingMap);
assert.equal(refreshed[1].value.features.length, 0, 'empty results must clear old map pins');
console.log('Existing map sources refresh saved details and clear removed results');

let factoryRows = [{name:'FACTORY', latitude:37.4, longitude:-122, pending_count:2}];
refreshContext.callMapData = (method, callback) => callback({message:factoryRows});
refreshContext.geocodeFactoryRows = (rows, callback) => callback(rows);
refreshContext.hasFactoryCoords = () => true;
vm.runInNewContext(sourceFunction('loadFactories'), refreshContext);
refreshContext.loadFactories(existingMap);
assert.equal(refreshed[2].value.features[0].properties.pending_count, 2);
factoryRows = [];
refreshContext.loadFactories(existingMap);
assert.equal(refreshed[3].value.features.length, 0);

let route = ['home-build-request', 'HBR-36'];
let routeChanged;
const returned = [];
const routeContext = {
    frappe: {router: {on:(event, callback) => { assert.equal(event, 'change'); routeChanged = callback; }},
        get_route: () => route},
    container: {isConnected:true, getBoundingClientRect:() => ({height:600})},
    setTimeout:callback => callback(),
    _activePopup:null,
    loadData:map => returned.push('homes'),
    loadFactories:map => returned.push('factories'),
};
vm.runInNewContext(sourceFunction('bindMapReturn'), routeContext);
routeContext.bindMapReturn(existingMap);
routeChanged();
route = ['map-settings', 'Map Settings']; routeChanged();
assert.equal(returned.length, 0, 'unrelated routes must not refetch map data');
route = ['Workspaces', 'Map']; routeChanged();
route = ['map']; routeChanged();
assert.deepEqual(returned, ['homes', 'factories', 'homes', 'factories']);
routeContext.container.isConnected = false; routeChanged();
assert.equal(returned.length, 4, 'discarded map instances must not reload');
console.log('Returning to either Map route refreshes home and factory data without duplicate layers');
