// Source-only client regression; no real Frappe, browser, uploads or providers.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = [];
class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.disabled = false; nodes.push(this); }
    setAttribute(name, value) { this[name] = value; }
    getAttribute(name) { return this[name] || null; }
    append(...items) { this.children.push(...items); }
    before(item) { this.beforeNode = item; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    insertAdjacentHTML() {}
    set innerHTML(value) {
        this.html = value; this.children = [];
        if (this.tag === 'tr') { this.lastElementChild = new Element('td'); this.selected = new Element('span'); }
        if (this.tag === 'table') this.tbody = new Element('tbody');
    }
    get innerHTML() { return this.html; }
    querySelector(selector) { return selector === 'tbody' ? this.tbody : this.selected; }
}
const footer = new Element('footer');
const saveButton = new Element('button');
const form = {doc:{home_type:'Spec'}, is_new:true, in_edit_mode:true, validate:()=>true,
    get_value:()=> 'Spec', on:()=>{}, make_form_dirty:()=>{}};
let refreshCount = 0;
let chosenUrl, savedUrl;
const sentTypes = [];
const document = {
    createElement:tag=>new Element(tag), createTextNode:text=>({text}),
    querySelector:()=>footer,
    addEventListener:()=>{},
    querySelectorAll:selector=>selector.includes('footer') ? [saveButton] : selector.includes('data-fieldname') || selector.includes('frappe-control') ? [] : nodes.filter(n=>n.tag === 'input')
};
class FormData { constructor() { this.values = {}; } append(k,v) { this.values[k]=v; } }
const context = {document, FormData, URLSearchParams, setTimeout, MutationObserver:class {observe() {}},
    window:{addEventListener:()=>{},history:{replaceState:(_s,_t,url)=>{savedUrl=url;}},location:{assign:url=>{chosenUrl=url;}}},
    frappe:{web_form:form, csrf_token:'TEST-CSRF', ready:fn=>fn(), throw:message=>{throw Error(message);},
        call:async ({method})=>{
            if (method.endsWith('get_required_docs')) {
                if (refreshCount === 1) throw Error('offline checklist');
                return {message:['Factory Quote','Plot Plan']};
            }
            if (refreshCount++ === 0) throw Error('readback temporarily unavailable');
            return {message:{modified:'LATEST-MODIFIED',editable:{home_type:process.argv.includes('--concurrent-edit')?'Inventory':'Spec'},documents:{items:[{document_type:'Factory Quote',uploaded:true}]}}};
        }},
    fetch:async (_url,{body})=>{
        sentTypes.push(body.values.document_type);
        const ok = sentTypes.length !== 2;
        return {ok,json:async()=>({message:{uploaded:ok}})};
    }
};
vm.runInNewContext(fs.readFileSync(require.resolve('../dcr/web_form/dealer_home_build_request/dealer_home_build_request.js'),'utf8'),context);
const settle = async()=>{await new Promise(resolve=>setImmediate(resolve));};
(async()=>{
    await settle();
    const inputs = nodes.filter(n=>n.tag === 'input');
    assert.equal(inputs.length,2);
    for (const input of inputs) {
        input.files=[{name:'demo.pdf',size:100}]; input.listeners.change();
    }
    const firstSave=form.handle_success({name:'HBR-SAVED'});
    assert.equal(form.validate(),false,'save is blocked during uploads');
    assert.equal(saveButton.disabled,true);
    let prevented=false, stopped=false;
    footer.listeners.submit({preventDefault:()=>{prevented=true;},stopImmediatePropagation:()=>{stopped=true;}});
    assert.equal(prevented && stopped,true,'implicit submit cannot reload and discard files during upload');
    await firstSave;
    assert.equal(form.doc.name,'HBR-SAVED');
    assert.equal(form.is_new,false);
    assert.equal(savedUrl,'/dealer-home-request/HBR-SAVED/edit','reload retains saved identity');
    assert.equal(chosenUrl,undefined,'partial failure does not silently navigate away');
    assert(footer.beforeNode.children.some(n=>n.role==='status' && /Refresh the saved request/.test(n.textContent)),'offline checklist retains the recovery message');
    assert.equal(saveButton.disabled,true,'stale save uses an explicit refresh action');
    assert.throws(()=>form.validate(),/latest version needs to refresh/,'stale save stays blocked with a truthful message');
    await settle();
    if (process.argv.includes('--concurrent-edit')) {
        assert.equal(form.doc.modified,undefined,'concurrent field edit cannot silently advance modification stamp');
        assert.equal(saveButton.disabled,true);
        assert(footer.beforeNode.children.some(n=>n.role==='status' && /changed or is now locked/.test(n.textContent)));
        console.log('Concurrent saved-field change stays blocked without overwriting (mocked client)');
        return;
    }
    assert.equal(form.doc.modified,'LATEST-MODIFIED');
    assert.equal(form.validate(),true);
    await form.handle_success({name:'HBR-SAVED'});
    assert.deepEqual(sentTypes,['Factory Quote','Plot Plan','Plot Plan'],'only failed files retry');
    assert.equal(chosenUrl,'/portal?request=HBR-SAVED');
    console.log('Native form identity, upload lock and partial retry regression passed (mocked client)');
})().catch(error=>{console.error(error);process.exitCode=1;});
