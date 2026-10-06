// Meaningful native-client boundary checks. Source simulation, not hosted acceptance.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require.resolve('../dcr/web_form/dealer_home_build_request/dealer_home_build_request.js'), 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));
function harness() {
    const nodes = [], windowEvents = {}, documentEvents = {}, warnings = [], navigations = [], notices = [];
    class Element {
        constructor(tag) { this.tag=tag; this.children=[]; this.attributes={}; this.listeners={}; this.value=''; this.textContent=''; this.classList={contains:()=>false}; nodes.push(this); }
        setAttribute(key,value) { this.attributes[key]=value; }
        getAttribute(key) { return this.attributes[key] ?? null; }
        addEventListener(name,fn) { this.listeners[name]=fn; }
        append(...items) { this.children.push(...items); }
        after(item) { this.afterNode=item; }
        before(item) { this.beforeNode=item; }
        insertAdjacentHTML() {}
        set innerHTML(value) { this.html=value; this.children=[]; if(this.tag==='table')this.tbody=new Element('tbody'); if(this.tag==='tr'){this.lastElementChild=new Element('td');this.selected=new Element('span');} }
        get innerHTML() { return this.html; }
        querySelector(selector) { return selector==='tbody'?this.tbody:this.selected; }
    }
    const footer=new Element('footer'), native=new Element('form'), heading=new Element('h1'), save=new Element('button');
    const field=new Element('input'); field.value='Spec'; field.type='text'; field.setAttribute('data-fieldname','home_type');
    const label=new Element('label'); label.classList={contains:name=>name==='reqd'}; label.textContent='Home type';
    const help=new Element('p'); help.textContent='Choose the type of home';
    const wrapper=new Element('div'); wrapper.querySelector=s=>s==='.control-label'?label:s==='.help-box'?help:null; wrapper.querySelectorAll=()=>[field];
    const form={doc:{home_type:'Spec'},is_new:true,in_edit_mode:true,fields_dict:{home_type:{df:{label:'Home type',reqd:1}}},get_value:()=>field.value,on:()=>{},make_form_dirty:()=>{frappe.form_dirty=true;},validate:()=>true};
    const document={createElement:tag=>new Element(tag),createTextNode:text=>({text}),
        addEventListener:(name,fn)=>documentEvents[name]=fn,
        querySelector:s=>s==='.web-form-footer'?footer:s==='.web-form-title h1'?heading:s==='.web-form'?native:null,
        querySelectorAll:s=>s.includes('footer')?[save]:s.includes('frappe-control')?[wrapper]:s.includes('data-fieldname')?[field]:[field,...nodes.filter(n=>n.tag==='input'&&n.type==='file')]
    };
    const frappe={web_form:form,ready:fn=>fn(),warn:(title,message,fn)=>{const dialog={};warnings.push({title,message,confirm:fn,dialog});return dialog;},
        msgprint:text=>notices.push(text),throw:text=>{throw Error(text);},form_dirty:false,csrf_token:'TEST',
        call:async({method})=>method.endsWith('get_required_docs')?{message:['Factory Quote']}:{message:{modified:'NEW',editable:{home_type:'Spec'},documents:{items:[]}}}};
    const window={addEventListener:(name,fn)=>windowEvents[name]=fn,location:{assign:url=>navigations.push(url)},history:{replaceState:()=>{}},saving:false};
    vm.runInNewContext(source,{document,window,frappe,URLSearchParams,MutationObserver:class{observe(){}},FormData:class{append(){}},fetch:async()=>({ok:true,json:async()=>({message:{uploaded:true}})})});
    const clickHeader=()=>{let prevented=false;documentEvents.click({target:{closest:()=>({href:'/portal'})},button:0,preventDefault:()=>prevented=true});assert(prevented);};
    const unload=()=>{let prevented=false;const event={preventDefault:()=>prevented=true};windowEvents.beforeunload(event);return{prevented,returnValue:event.returnValue};};
    return{nodes,form,field,label,help,window,frappe,warnings,navigations,notices,clickHeader,unload};
}
(async()=>{
    let h=harness(); await settle();
    assert.equal(h.field.id,'dcr-field-home_type-0');
    assert.equal(h.label.getAttribute('for'),h.field.id);
    assert.equal(h.field.getAttribute('aria-labelledby'),h.label.id);
    assert.equal(h.field.getAttribute('aria-describedby'),h.help.id);
    assert.equal(h.field.getAttribute('aria-required'),'true');
    assert.equal(h.unload().prevented,false);h.clickHeader();assert.deepEqual(h.navigations,['/portal']);assert.equal(h.warnings.length,0);

    h=harness();await settle();h.field.value='Inventory';
    assert.equal(h.unload().prevented,true,'changed native field protects reload/back');
    h.clickHeader();assert.equal(h.warnings.length,1);assert.equal(h.navigations.length,0);
    h.warnings[0].dialog.onhide();assert.equal(h.field.value,'Inventory','cancel retains unsaved input');
    h.clickHeader();assert.equal(h.warnings.length,2);h.warnings[1].confirm();
    assert.deepEqual(h.navigations,['/portal']);assert.equal(h.unload().prevented,false,'confirmed discard avoids a second browser warning');

    h=harness();await settle();const file=h.nodes.find(n=>n.tag==='input'&&n.type==='file');
    file.files=[{name:'fictional.pdf',size:100}];file.listeners.change();
    assert.equal(h.unload().prevented,true,'pending files protect leave even without field edits');
    h.form.discard_form();assert.equal(h.warnings.length,1,'native Discard shares the guard');
    assert.equal(h.navigations.length,0);
    await h.form.handle_success({name:'HBR-A'});
    assert.deepEqual(h.navigations,['/portal?request=HBR-A']);assert.equal(h.unload().prevented,false,'successful save/uploads leave cleanly');

    h=harness();await settle();h.window.saving=true;h.clickHeader();
    assert.equal(h.navigations.length,0);assert.equal(h.warnings.length,0);
    assert.match(h.notices[0],/finish saving/);assert.equal(h.unload().prevented,true,'in-flight save stays guarded');
    console.log('Native labels, clean/dirty/pending leave, cancel/confirm, saving lock and successful save passed (mocked client)');
})().catch(error=>{console.error(error);process.exitCode=1;});
