// UI-only, loan-scoped hosted trial helpers. Evaluate in the tool orchestration runtime.
// All Frappe API calls are read-only. Save/Submit use visible native controls.
function createNativeDocumentTrial(tools, tabId){
 async function data(expression){
  const r=await tools.mcp__t3_code__preview_evaluate({tabId,expression});
  if(r.isError||!r.structuredContent||!("value" in r.structuredContent))throw new Error(JSON.stringify(r));
  return r.structuredContent.value;
 }
 async function act(args){const r=await tools.mcp__t3_code__preview_act({tabId,...args});if(r.isError)throw new Error(JSON.stringify(r));}
 async function state(){return data("({doctype:cur_frm.doctype,name:cur_frm.doc.name,docstatus:cur_frm.doc.docstatus,dirty:cur_frm.is_dirty(),loan:cur_frm.doc.loan,against_loan:cur_frm.doc.against_loan,posting_date:cur_frm.doc.posting_date,value_date:cur_frm.doc.value_date,dialogs:Array.from(document.querySelectorAll('.modal.show')).map(d=>d.innerText)})");}
 async function settle(condition,ms=10000){return data("(async()=>{const end=Date.now()+"+ms+";while(!("+condition+")&&Date.now()<end)await new Promise(r=>setTimeout(r,100));return {ready:!!("+condition+"),state:{doctype:cur_frm.doctype,name:cur_frm.doc.name,docstatus:cur_frm.doc.docstatus,dirty:cur_frm.is_dirty()},dialogs:Array.from(document.querySelectorAll('.modal.show')).map(d=>d.innerText)};})()");}
 async function persisted(){return data("(async()=>{const d=(await frappe.call({method:'frappe.client.get',args:{doctype:cur_frm.doctype,name:cur_frm.doc.name}})).message;return {doctype:d.doctype,name:d.name,docstatus:d.docstatus,loan:d.loan,against_loan:d.against_loan,loan_product:d.loan_product,loan_disbursement:d.loan_disbursement,posting_date:d.posting_date,value_date:d.value_date};})()");}
 function verify(d,expect){for(const [k,v] of Object.entries(expect))if((k==="posting_date"&&typeof v==="string"&&v.length===10?String(d[k]||"").slice(0,10):(d[k]||""))!==(v||""))throw new Error("Scope mismatch "+k+": "+JSON.stringify(d));}
 async function saveAndSubmit(doctype,expect){
  const before=await state();verify(before,{doctype,...Object.fromEntries(Object.entries(expect).filter(([k])=>k in before))});
  if(before.docstatus!==0)throw new Error("Expected unsent draft");
  if(before.name.startsWith("new-")||before.dirty){
   await act({action:"click",selector:'[id="page-'+doctype+'"] .primary-action[data-label="Save"]'});
   const saved=await settle("!cur_frm.doc.name.startsWith('new-')&&!cur_frm.is_dirty()");
   if(!saved.ready)throw new Error("Save not verified: "+JSON.stringify(saved));
  }
  const draft=await persisted();verify(draft,{doctype,docstatus:0,...expect});
  await act({action:"click",selector:'[id="page-'+doctype+'"] .primary-action[data-label="Submit"]'});
  const prompt=await data("(async()=>{const end=Date.now()+5000;while(!document.querySelector('.modal.show')&&cur_frm.doc.docstatus!==1&&Date.now()<end)await new Promise(r=>setTimeout(r,100));return {docstatus:cur_frm.doc.docstatus,text:document.querySelector('.modal.show')?.innerText};})()");
  if(prompt.docstatus!==1){
   if(!prompt.text?.includes("Permanently Submit "+draft.name+"?"))throw new Error("Unexpected submit prompt: "+JSON.stringify(prompt));
   await act({action:"click",selector:".modal.show .btn-modal-primary"});
  }
  const submitted=await settle("cur_frm.doc.docstatus===1");
  if(!submitted.ready)throw new Error("Submit not verified: "+JSON.stringify(submitted));
  const result=await persisted();verify(result,{doctype,docstatus:1,...expect});return result;
 }
 return {tabId,data,act,state,settle,persisted,verify,saveAndSubmit};
}

function createMonthlyTrial(tools, tabId, loan) {
 const ui=createNativeDocumentTrial(tools,tabId);
 const origin="https://backdesk.dealercapital.net";
 async function navigate(path){const r=await tools.mcp__t3_code__preview_navigate({tabId,url:origin+path});if(r.isError)throw Error(JSON.stringify(r));}
 async function field(doctype,name,value,expected){
  const selector='[id="page-'+doctype+'"] input[data-fieldname="'+name+'"]';
  for(let attempt=0;attempt<2;attempt++){
   await ui.act({action:"type",selector,clear:true,text:String(value)});
   await ui.act({action:"press",key:"Tab"});
   const ready=await ui.settle('String(cur_frm.doc['+JSON.stringify(name)+']??"")==='+JSON.stringify(String(expected)),1500);
   if(ready.ready)return;
  }
  throw Error("Field did not settle: "+doctype+"."+name);
 }
 async function process(doctype,date){
  const slug=doctype.toLowerCase().replaceAll(" ","-");
  await navigate("/desk/"+slug);
  await ui.act({action:"click",selector:'.primary-action[data-label="'+("Add "+doctype)+'"]'});
  const ready=await ui.settle("cur_frm?.doctype==="+JSON.stringify(doctype)+"&&cur_frm.doc.name.startsWith('new-')");
  if(!ready.ready)throw Error("New process form not ready");
  await field(doctype,"loan",loan,loan);
  const [y,m,d]=date.split("-");
  await field(doctype,"posting_date",m+"-"+d+"-"+y,date);
  return ui.saveAndSubmit(doctype,{loan,loan_product:"",loan_disbursement:"",posting_date:date});
 }
 async function receipt(row){
  await navigate("/desk/loan/"+loan);
  const ready=await ui.settle("cur_frm?.doctype==='Loan'&&cur_frm.doc.name==="+JSON.stringify(loan)+"&&!!document.querySelector('[id=\"page-Loan\"] a[data-label=\"Loan%20Repayment\"]')");
  if(!ready.ready)throw Error("Loan not ready");
  await ui.act({action:"click",selector:'[id="page-Loan"] .inner-group-button[data-label="Create"] > button'});
  await ui.act({action:"click",selector:'[id="page-Loan"] a[data-label="Loan%20Repayment"]'});
  const mapped=await ui.settle("cur_frm?.doctype==='Loan Repayment'&&cur_frm.doc.against_loan==="+JSON.stringify(loan)+"&&cur_frm.doc.value_date&&cur_frm.doc.pending_principal_amount!==undefined");
  if(!mapped.ready)throw Error("Mapped repayment not ready");
  const [y,m,d]=row.payment_date.split("-");
  await field("Loan Repayment","value_date",m+"-"+d+"-"+y+" 00:00:00",row.payment_date+" 00:00:00");
  const quoted=await ui.settle("Number(cur_frm.doc.interest_payable)==="+Number(row.interest)+"&&Number(cur_frm.doc.payable_amount)==="+Number(row.total));
  if(!quoted.ready)throw Error("Unexpected repayment quote: "+JSON.stringify(await ui.data("cur_frm.doc")));
  await field("Loan Repayment","amount_paid",row.total,Number(row.total));
  return ui.saveAndSubmit("Loan Repayment",{against_loan:loan,value_date:row.payment_date+" 00:00:00",posting_date:"2026-11-07"});
 }
 async function evidence(row,receiptName){
  return ui.data("(async()=>{"+
   "const get=async(doctype,name)=>(await frappe.call({method:'frappe.client.get',args:{doctype,name}})).message;"+
   "const list=async(doctype,filters,fields)=>(await frappe.call({method:'frappe.client.get_list',args:{doctype,filters,fields,limit_page_length:500}})).message;"+
   "return {receipt:await get('Loan Repayment',"+JSON.stringify(receiptName)+"),loan:await get('Loan',"+JSON.stringify(loan)+"),"+
   "accrual:await list('Loan Interest Accrual',{loan:"+JSON.stringify(loan)+",docstatus:1,posting_date:['between',["+JSON.stringify(row.period_start)+","+JSON.stringify(row.cutoff)+"]]},['name','posting_date','interest_amount','interest_type']),"+
   "demands:await list('Loan Demand',{loan:"+JSON.stringify(loan)+",docstatus:1,demand_date:"+JSON.stringify(row.payment_date)+"},['name','demand_date','demand_type','demand_subtype','demand_amount','paid_amount','outstanding_amount']),"+
   "gl:await list('GL Entry',{voucher_type:'Loan Repayment',voucher_no:"+JSON.stringify(receiptName)+",is_cancelled:0},['name','account','debit','credit','against_voucher_type','against_voucher','posting_date'])};})()");
 }
 function check(row,e){
  const fail=m=>{throw Error("Payment "+row.payment+": "+m);};
  const eq=(actual,expected,m)=>{if(Number(actual||0)!==Number(expected))fail(m+": "+actual+" != "+expected);};
  if(e.receipt.docstatus!==1||e.receipt.against_loan!==loan||e.receipt.value_date.slice(0,10)!==row.payment_date)fail("Wrong saved receipt");
  eq(e.receipt.amount_paid,row.total,"receipt amount");eq(e.receipt.total_interest_paid,row.interest,"receipt interest");eq(e.receipt.principal_amount_paid,row.principal,"receipt principal");
  eq(e.receipt.total_penalty_paid,0,"penalty");eq(e.receipt.total_charges_paid,0,"charges");
  eq(e.loan.loan_amount-e.loan.total_principal_paid,row.closing_principal,"closing principal");
  eq(e.accrual.reduce((s,x)=>s+x.interest_amount,0),row.interest,"accrual interest");
  eq(e.accrual.length,row.charged_days,"daily accrual count");
  eq(e.demands.reduce((s,x)=>s+x.paid_amount,0),row.total,"paid demands");
  eq(e.demands.reduce((s,x)=>s+x.outstanding_amount,0),0,"unpaid demands");
  eq(e.gl.reduce((s,x)=>s+x.debit,0),row.total,"voucher debit");eq(e.gl.reduce((s,x)=>s+x.credit,0),row.total,"voucher credit");
  if(e.gl.some(x=>x.against_voucher!==loan))fail("Voucher references another loan");
 }
 return {ui,field,navigate,process,receipt,evidence,check};
}
({createNativeDocumentTrial,createMonthlyTrial});

