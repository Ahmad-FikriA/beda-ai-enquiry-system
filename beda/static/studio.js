const $ = id => document.getElementById(id);
const stages = [
 ['input','Incoming enquiry','SOURCE',0,180,'RECEIVED'],['normalize','Normalize input','CODE',230,180,'NORMALIZED'],
 ['extract','Classify + extract','GEMINI',460,180,'CLASSIFIED'],['validate','Validate JSON + evidence','CODE',690,180,'VALIDATED'],
 ['match','CRM match + deduplicate','CODE',920,180,'CRM_MATCHED'],['route','Route enquiry','DECISION',1150,180,'ROUTED'],
 ['junk','Junk / restore','DECISION',1380,-20,'JUNK_POLICY_CHECKED'],['complete','Information complete?','DECISION',1380,180,'INFORMATION_CHECKED'],
 ['clarify','Draft clarification','GEMINI',1610,0,'DRAFTED'],['research','Need research?','DECISION',1610,240,'RESEARCH_CHECKED'],
 ['expert','Research agent + sources','GEMINI',1840,420,''],['draft','Draft response','GEMINI',1840,180,'DRAFTED'],
 ['approval','Alert + human approval','HUMAN',2070,180,'APPROVAL_REQUESTED'],['execute','Record permitted action','CODE',2300,180,'ACTION_SUCCEEDED'],
 ['audit','Activity + decision log','RECORD',2530,180,''],['failure','Alert human / retry','HUMAN',690,420,'ESCALATED']];
const links = [['input','normalize',''],['normalize','extract',''],['extract','validate',''],['validate','extract','Retry'],['validate','failure','Failure'],['validate','match','Valid'],['match','route','Candidates / no match'],['route','junk','Junk'],['route','complete','Sales / support / other'],['complete','clarify','Missing'],['complete','research','Complete'],['research','expert','Required'],['research','draft','No'],['expert','draft','Holding reply'],['clarify','approval',''],['draft','approval',''],['junk','approval','Uncertain / restored'],['junk','audit','Recoverable quarantine'],['approval','execute','Approve'],['approval','audit','Reject'],['execute','audit',''],['failure','audit','']];
const colors = {SOURCE:'#74c8b8',CODE:'#74c8b8',GEMINI:'#acb4f3',DECISION:'#d5ed93',HUMAN:'#f0bd7c',RECORD:'#94a39a'};
links.push(['approval','junk','Move to Junk']);
const positions={input:[0,0],normalize:[240,0],extract:[480,0],validate:[480,160],match:[240,160],route:[0,160],junk:[0,330],complete:[240,330],failure:[480,330],clarify:[0,500],research:[240,500],expert:[480,500],draft:[240,670],approval:[0,670],execute:[0,840],audit:[240,840]};
stages.forEach(s=>{[s[3],s[4]]=positions[s[0]]});
let viewingVersion=null, folder=null;
let selected=new URLSearchParams(location.search).get('enquiry')||'E001', snapshot={enquiry:null,audit:[],actions:[]}, workspace, busy=false;
const cy = cytoscape({container:$('canvas'),elements:[...stages.map(([id,name,kind,x,y])=>({data:{id,label:name+'\n'+kind,color:colors[kind]},position:{x,y}})),...links.map(([source,target,label],i)=>({data:{id:'edge'+i,source,target,label}}))],layout:{name:'preset'},minZoom:.18,maxZoom:2,wheelSensitivity:.15,
 style:[{selector:'node',style:{'shape':'round-rectangle','width':178,'height':76,'background-color':'#22282a','border-color':'data(color)','border-width':1.5,'label':'data(label)','text-wrap':'wrap','text-valign':'center','color':'#e1e8e5','font-size':12,'font-family':'Helvetica Neue','line-height':1.7}},
 {selector:'edge',style:{'width':1.3,'line-color':'#515b60','target-arrow-color':'#515b60','target-arrow-shape':'triangle','curve-style':'bezier','label':'data(label)','font-size':10,'color':'#a2ada9','text-background-color':'#151719','text-background-opacity':1,'text-background-padding':4}},
 {selector:'.visited',style:{'background-color':'#2a3730','border-width':3}}, {selector:'.waiting',style:{'background-color':'#473627','border-color':'#f0bd7c','border-width':3}},
 {selector:'.running',style:{'background-color':'#383d59','border-color':'#c5ceff','border-width':4,'underlay-color':'#acb4f3','underlay-opacity':.12,'underlay-padding':10}},
 {selector:'edge.traversed',style:{'line-color':'#74c8b8','target-arrow-color':'#74c8b8','width':2.5}},
 {selector:':selected',style:{'border-color':'#fff','border-width':3}}]});
cy.zoom(.85);cy.pan({x:cy.width()/2-240*.85,y:65});
stages.forEach(([id,name])=>{const o=document.createElement('option');o.value=id;o.textContent=name;$('stage').append(o)});
cy.on('tap','node',e=>inspect(e.target.id()));$('stage').onchange=()=>inspect($('stage').value);
$('fit').onclick=()=>cy.fit(undefined,45);$('zoom-in').onclick=()=>cy.zoom(cy.zoom()*1.3);$('zoom-out').onclick=()=>cy.zoom(cy.zoom()/1.3);
function notice(text){$('notice').textContent=text;$('notice').style.display='block';setTimeout(()=>$('notice').style.display='none',7000)}
async function api(path,data){const response=await fetch(path,data?{method:'POST',headers:{'Content-Type':'application/json','X-BEDA-Workspace':'1'},body:JSON.stringify(data)}:{});const result=await response.json();if(!response.ok)throw Error(result.error||'Request failed');return result}
function section(title,value){const wrapper=document.createElement('div');wrapper.innerHTML=InspectorView.renderSection(title,value);$('details').append(wrapper)}
function restoreControl(eq){
 if(snapshot.version!==snapshot.current_version||busy||!(eq.status==='JUNK'||(eq.status==='PENDING_APPROVAL'&&eq.recommendation?.action==='REVIEW_JUNK')))return;
 const button=document.createElement('button');button.className='restore-button';button.textContent='Not junk / Restore to Inbox';
 button.onclick=async()=>{button.disabled=true;try{await api('/api/junk/restore',{id:eq.id,version:snapshot.version});folder='inbox';viewingVersion=null;await refresh();inspect('approval');notice('Restored to Inbox for review. Previous history is preserved.')}catch(e){notice(e.message);button.disabled=false}};
 $('details').append(button);
}
function inspect(id){const changed=$('stage').value!==id;const wasOpen=!changed&&Boolean($('details').querySelector('.prompt-preview[open]'));$('stage').value=id;cy.nodes().unselect();cy.$id(id).select();if(changed){cy.stop();cy.animate({center:{eles:cy.$id(id)},zoom:Math.max(cy.zoom(),.75)},{duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:250})}$('details').replaceChildren();const eq=snapshot.enquiry;const fixture=workspace?.fixtures.find(f=>f.id===selected);const stage=stages.find(s=>s[0]===id);
 section(stage[1],stage[2]==='GEMINI'?'Real Gemini API · structured output':stage[2]==='HUMAN'?'Human decision required':'Deterministic application stage');
 if(['extract','draft','clarify','expert'].includes(id)){renderPrompt(id);if(wasOpen)$('details').querySelector('.prompt-preview')?.setAttribute('open','')}
 if(id==='input'){section('Input',eq?{from:eq.sender,subject:eq.subject,body:eq.body,attachment:eq.attachment_content}:fixture||'No input');return}
 if(id==='audit'){snapshot.audit.forEach(e=>{const d=document.createElement('div');d.className='event';const t=document.createElement('strong');t.textContent=e.event_type;const s=document.createElement('small');s.textContent=e.created_at+' · '+e.actor;d.append(t,s);$('details').append(d)});return}
 if(!eq){section('Waiting','Run this enquiry to inspect its actual output.');return}
 if(id==='junk'){
   if(!snapshot.audit.some(e=>e.event_type.startsWith('JUNK_'))){section('Branch','The junk branch was not taken in this run.');return}
   section('Current state',eq.status);section('AI classification reason',eq.proposal?.rationale);
   restoreControl(eq);
   if(snapshot.audit.some(e=>e.event_type==='JUNK_RESTORED'))section('Human correction','Marked not junk. The original AI classification is retained for transparency; automatic quarantine is disabled for this enquiry.');
   const move=snapshot.audit.find(e=>e.event_type==='JUNK_QUARANTINED');if(move)section('Recorded outcome',move.details.automatic?'Automatically moved to recoverable Junk under the local policy.':'A reviewer approved moving this message to recoverable Junk.');
   const policy=snapshot.audit.find(e=>e.event_type==='JUNK_POLICY_CHECKED');if(policy)section('Quarantine checks',policy.details);
   section('What happens here','Junk is kept in the local database, not deleted. No reply is drafted, no research is run and no CRM record is changed. Uncertain cases require human review.');
   if(eq.status==='PENDING_APPROVAL'&&eq.recommendation?.action==='REVIEW_JUNK'){const b=document.createElement('button');b.textContent='Open human review';b.onclick=()=>inspect('approval');$('details').append(b)}
   return;
 }
 if(id==='expert'){section('Approved local search',snapshot.audit.filter(e=>e.event_type==='RESEARCH_RETRIEVED').map(e=>e.details));section('Validated research',snapshot.audit.filter(e=>e.event_type==='RESEARCH_COMPLETED').map(e=>e.details));section('Boundary','At most three queries and five local source chunks. Quotes are validated. Engineering sign-off remains human.');return}
 if(id==='execute'){section('Action result',snapshot.actions);return}
 if(id==='approval'){section('Recommendation',eq.recommendation);section('Draft for review',eq.draft_response||'No customer response drafted.');section('Current state',eq.status);const junkReview=eq.recommendation?.action==='REVIEW_JUNK';if(eq.status==='PENDING_APPROVAL'&&snapshot.version===snapshot.current_version&&snapshot.actions[0]?.id.startsWith('LIVE-')){const wrap=document.createElement('div');wrap.className='buttons';for(const [label,approve] of [[junkReview?'Move to Junk':'Approve local action',true],['Reject',false]]){const b=document.createElement('button');b.textContent=label;b.disabled=busy;b.onclick=async()=>{b.disabled=true;try{await api('/api/decide',{id:selected,approve,version:snapshot.version});if(junkReview&&approve)folder='junk';await refresh();inspect(junkReview&&approve?'junk':'approval')}catch(e){notice(e.message);b.disabled=false}};wrap.append(b)}$('details').append(wrap)}restoreControl(eq);section('Execution scope',junkReview?'Move to Junk sets this message aside locally and can be undone. Reject keeps it in Inbox. No external message, CRM change or permanent deletion.':'Approval records a local review action. It does not send a message or modify CRM records.');return}
 const events=snapshot.audit.filter(e=>e.event_type===stage[5]);
 if((id==='clarify'&&!eq.proposal?.missing_fields.length)||(id==='draft'&&eq.proposal?.missing_fields.length))section('Branch','Not taken for this enquiry.');
 else if(events.length)section('Recorded output',events.at(-1).details);else section('State','Not executed or no event recorded for this stage.');
 if(id==='extract'){section('Model calls',snapshot.audit.filter(e=>['LLM_ATTEMPT','LLM_FAILURE','LLM_USAGE'].includes(e.event_type)&&(!e.details.stage||e.details.stage==='extract')).map(e=>e.details))}
}
async function refresh(){workspace=await api('/api/workspace');$('model').textContent=workspace.model+' · '+(workspace.configured?'Key configured':'API key needed');$('cases').replaceChildren();
 const all=[...workspace.fixtures,...workspace.enquiries.filter(e=>!workspace.fixtures.some(f=>f.id===e.id))];
 if(folder===null)folder=workspace.enquiries.find(e=>e.id===selected)?.status==='JUNK'?'junk':'inbox';
 const visible=WorkflowView.folderRows(all,workspace.enquiries,folder);
 if(!visible.some(e=>e.id===selected)){selected=visible[0]?.id||'';viewingVersion=null}
 for(const name of ['inbox','junk']){$('folder-'+name).textContent=(name==='junk'?'Junk':'Inbox')+' · '+WorkflowView.folderRows(all,workspace.enquiries,name).length;$('folder-'+name).setAttribute('aria-pressed',String(folder===name));$('folder-'+name).disabled=busy}
 $('folder-help').textContent=folder==='junk'?'Recoverable local copies. Nothing is permanently deleted.':'Suspected junk needing a decision stays here for review.';
 if(!visible.length){const p=document.createElement('p');p.className='muted';p.textContent='No messages in this folder.';$('cases').append(p)}
 for(const row of visible){const b=document.createElement('button');b.className='case'+(row.id===selected?' selected':'');const small=document.createElement('small');small.textContent=row.id+' · '+(row.status==='JUNK'?'In Junk':row.status);const title=document.createElement('span');title.textContent=row.subject;b.append(small,title);b.onclick=async()=>{if(busy)return;selected=row.id;viewingVersion=null;await refresh();if(folder==='junk')inspect('junk')};$('cases').append(b)}
 snapshot=selected?await api('/api/run/'+encodeURIComponent(selected)+(viewingVersion?'?version='+viewingVersion:'')):{enquiry:null,audit:[],actions:[],versions:[],version:0,current_version:0};updateVersions();$('title').textContent=selected?selected+' / '+(all.find(e=>e.id===selected)?.subject||'Custom enquiry'):'This folder is empty';$('status').textContent=snapshot.enquiry?.status||'Ready to run';
 cy.nodes().removeClass('visited waiting');for(const s of stages){if(s[5]&&snapshot.audit.some(e=>e.event_type===s[5]))cy.$id(s[0]).addClass('visited')}
 if(snapshot.enquiry?.status==='PENDING_APPROVAL')cy.$id('approval').addClass('waiting');
 if(snapshot.enquiry?.proposal?.missing_fields.length)cy.$id('draft').removeClass('visited');else cy.$id('clarify').removeClass('visited');
 $('run').textContent=snapshot.enquiry?.status==='MODEL_FAILED'?'↻ Retry enquiry':snapshot.enquiry?'View saved run':'▶ Run enquiry';paintProgress();renderActivity();inspect($('stage').value||'input');}
async function run(payload,endpoint='/api/process'){
 if(busy)return;
 if(snapshot.enquiry&&snapshot.enquiry.status!=='MODEL_FAILED'&&payload.fixture){inspect('audit');return}
 viewingVersion=null;selected=payload.fixture||payload.id;busy=true;$('run').disabled=true;$('new').disabled=true;updateVersions();
 $('status').textContent='Starting…';$('activity-state').textContent='● Live';
 let polling=true;
 const poll=async()=>{if(!polling)return;try{const next=await api('/api/run/'+encodeURIComponent(selected));if(!polling)return;
   const changed=next.audit.at(-1)?.id!==snapshot.audit.at(-1)?.id;
   snapshot=next;paintProgress();renderActivity();if(changed)inspect($('stage').value||'input');
 }catch(e){$('activity-state').textContent='Reconnecting…'}finally{if(polling)setTimeout(poll,650)}};
 poll();
 try{const result=await api(endpoint,payload);selected=result.id;
   folder=result.status==='JUNK'?'junk':'inbox';
   if(result.status==='JUNK')notice('Moved to recoverable Junk. No reply or CRM change. Use Not junk / Restore if needed.');
   if(result.status==='PENDING_APPROVAL')notice('Processing finished. Review the recommendation in the human approval node.');
 }catch(e){notice(e.message)}finally{polling=false;busy=false;$('run').disabled=false;$('new').disabled=false;await refresh();if(snapshot.enquiry?.status==='JUNK')inspect('junk')}
}
$('run').onclick=()=>run({fixture:selected});$('new').onclick=()=>$('compose').showModal();$('cancel').onclick=()=>$('compose').close();$('custom').onsubmit=e=>{e.preventDefault();const payload=Object.fromEntries(new FormData(e.target));$('compose').close();run(payload)};
const eventCopy={RESEARCH_RETRIEVED:'Approved documents retrieved. Inspect search queries and source excerpts.',RESEARCH_COMPLETED:'Research finished and citations validated.',RESEARCH_ESCALATED:'Evidence gaps or technical sign-off need human review.',RECEIVED:'Input received and saved.',NORMALIZED:'Message normalized for processing.',DEDUPLICATED:'Source ID checked for duplicates.',CLASSIFIED:'Gemini returned a structured classification.',VALIDATED:'Schema and source evidence checked.',CRM_MATCHED:'CRM candidates scored; ambiguity preserved.',ROUTED:'Owner and next action selected by application policy.',INFORMATION_CHECKED:'Checked required and missing information.',RESEARCH_CHECKED:'Checked whether approved research or human expertise is needed.',DRAFTED:'Response draft saved for review.',APPROVAL_REQUESTED:'Paused for your review. No action has been approved.',APPROVED:'You approved the local review action.',REJECTED:'You rejected the action. Execution stopped.',ACTION_STARTED:'Recording the permitted local action.',ACTION_SUCCEEDED:'Local action recorded. No external message sent.',PROMPT_PREVIEW:'Prompt prepared. Select this entry to inspect it.',LLM_USAGE:'Model response received; usage recorded.',IMPORT_WARNING:'Input format needs attention; import assumption recorded.'};
function eventStage(event){return WorkflowView.eventStage(event,snapshot.audit)}
let feedSignature='';
function renderActivity(){const signature=selected+':'+snapshot.version+':'+snapshot.audit.at(-1)?.id;
 $('activity-state').textContent=busy?'● Live':snapshot.enquiry?.status==='PENDING_APPROVAL'?'Awaiting your decision':'Saved events';
 if(signature===feedSignature)return;feedSignature=signature;
 const feed=$('activity-feed');feed.replaceChildren();
 if(!snapshot.audit.length){const p=document.createElement('p');p.className='muted';p.textContent='Run this enquiry to see real stage events, model calls and decisions.';feed.append(p)}
 for(const event of snapshot.audit){const row=document.createElement('button');row.className='activity-row';row.dataset.eventId=event.id;
 const badge=document.createElement('span');badge.className='activity-icon';badge.textContent=['LLM_FAILURE','ESCALATED'].includes(event.event_type)?'!':event.event_type==='APPROVAL_REQUESTED'?'Ⅱ':'›';
 const content=document.createElement('span');const label=document.createElement('strong');label.textContent=stages.find(s=>s[0]===eventStage(event))?.[1]||'Pipeline';
 const text=document.createElement('span');text.textContent=event.details.message||eventCopy[event.event_type]||
  (event.event_type==='LLM_ATTEMPT'?`Gemini request · attempt ${event.details.attempt} · ${event.details.model}`:
   event.event_type==='RETRYING'?`Retry scheduled in ${event.details.delay_seconds}s.`:event.details.error||event.event_type);
 const time=document.createElement('time');time.textContent=new Date(event.created_at).toLocaleTimeString();content.append(label,text);row.append(badge,content,time);
 row.onclick=()=>{inspect(eventStage(event));if(event.event_type==='PROMPT_PREVIEW')$('details').querySelector('.prompt-preview')?.setAttribute('open','')};feed.append(row)}
 if($('follow').checked)feed.scrollTop=feed.scrollHeight;
}
function paintProgress(){cy.nodes().removeClass('visited waiting running');cy.edges().removeClass('traversed');
 for(const event of snapshot.audit){const id=eventStage(event);if(!['PROMPT_PREVIEW','STAGE_STARTED','LLM_ATTEMPT','LLM_FAILURE','RETRYING'].includes(event.event_type))cy.$id(id).addClass('visited')}
 let active=null;
 for(const event of snapshot.audit){if(event.event_type==='STAGE_STARTED')active=event.details.stage;
 if(['CLASSIFIED','DRAFTED','RESEARCH_COMPLETED','ESCALATED','APPROVAL_REQUESTED'].includes(event.event_type))active=null}
 if(active&&busy){cy.$id(active).addClass('running');$('status').textContent=stages.find(s=>s[0]===active)[1]+'…'}
 else $('status').textContent=snapshot.enquiry?.status||'Ready to run';
 if(snapshot.enquiry?.status==='PENDING_APPROVAL')cy.$id('approval').removeClass('visited').addClass('waiting');
 for(const edge of cy.edges()){
   if(edge.source().id()==='approval'&&edge.target().id()==='audit'&&!snapshot.audit.some(e=>e.event_type==='REJECTED'))continue;
   if(edge.source().id()==='approval'&&edge.target().id()==='junk'&&!snapshot.audit.some(e=>e.event_type==='JUNK_QUARANTINED'&&e.details.automatic===false))continue;
   if(edge.source().hasClass('visited')&&(edge.target().hasClass('visited')||edge.target().hasClass('running')))edge.addClass('traversed');
 }
}
function renderPrompt(id){const stage=id==='clarify'?'draft':id;const event=snapshot.audit.filter(e=>e.event_type==='PROMPT_PREVIEW'&&e.details.stage===stage).at(-1);
 const box=document.createElement('details');box.className='prompt-preview';const summary=document.createElement('summary');summary.textContent='Prompt preview · '+(event?'prepared request':'not prepared yet');box.append(summary);
 if(event){for(const [label,value] of [['System instruction',event.details.system_instruction],['Input sent to model',event.details.input],['Output schema',event.details.schema],['Model settings',{model:event.details.model,...event.details.settings}]]){const h=document.createElement('h3');h.textContent=label;const p=document.createElement('pre');if(typeof value==='string')p.textContent=value;else p.innerHTML=InspectorView.highlightJson(value);box.append(h,p)}}
 else{const p=document.createElement('p');p.textContent='The exact prompt appears when this model stage starts. API keys and transport headers are excluded.';box.append(p)}$('details').append(box)}
const reduceMotion=matchMedia('(prefers-reduced-motion: reduce)');let pulse=false;
setInterval(()=>{if(reduceMotion.matches)return;pulse=!pulse;cy.nodes('.running').style('underlay-opacity',pulse?.22:.07)},700);

function updateVersions(){
 $('version').replaceChildren();const latest=document.createElement('option');latest.value='';latest.textContent='Latest · v'+(snapshot.current_version||1);$('version').append(latest);
 for(const run of snapshot.versions||[]){const option=document.createElement('option');option.value=run.version;option.textContent='v'+run.version+' · '+run.mode;$('version').append(option)}
 $('version').value=viewingVersion||'';
 const historic=snapshot.version!==snapshot.current_version;
 $('run').disabled=busy||historic||!selected;
 $('version-note').textContent=historic?'Historical snapshot · read only':snapshot.enquiry?.proposal?.category==='junk'?'Local Junk moves are recoverable':'New versions require new approval';
 $('rerun').disabled=busy||!snapshot.enquiry||historic;
 $('redraft').disabled=busy||!snapshot.enquiry?.proposal||historic||['junk','infrastructure'].includes(snapshot.enquiry?.proposal?.category);
 $('version').disabled=busy;
}
$('version').onchange=async()=>{viewingVersion=$('version').value?Number($('version').value):null;await refresh()};
$('rerun').onclick=()=>run({id:selected,mode:'full',request_id:crypto.randomUUID()},'/api/rerun');
$('redraft').onclick=()=>run({id:selected,mode:'draft',request_id:crypto.randomUUID()},'/api/rerun');
for(const name of ['inbox','junk'])$('folder-'+name).onclick=async()=>{if(busy)return;folder=name;viewingVersion=null;await refresh();inspect(name==='junk'?'junk':'input')};
refresh().then(()=>{if(folder==='junk')inspect('junk')}).catch(e=>notice(e.message));
