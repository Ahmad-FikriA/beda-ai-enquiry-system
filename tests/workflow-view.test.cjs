const {test}=require('node:test');
const assert=require('node:assert/strict');
const view=require('../beda/static/workflow-view.js');

test('quarantine events light Junk and Audit, not information or approval',()=>{
  const audit=[{event_type:'ROUTED',details:{}},{event_type:'JUNK_POLICY_CHECKED',details:{}},
    {event_type:'JUNK_QUARANTINED',details:{}},{event_type:'JUNK_AUDITED',details:{}}];
  assert.deepEqual(audit.map(e=>view.eventStage(e,audit)),['route','junk','junk','audit']);
});
test('restore and uncertain review preserve their real stages',()=>{
  assert.equal(view.eventStage({event_type:'JUNK_RESTORED',details:{}}),'junk');
  assert.equal(view.eventStage({event_type:'APPROVAL_REQUESTED',details:{}}),'approval');
  assert.equal(view.eventStage({event_type:'ATTACHMENT_SELECTED',details:{stage:'input'}}),'input');
});
test('folder list uses saved status and keeps uncertain or restored messages in Inbox',()=>{
  const rows=[{id:'E004'},{id:'custom'},{id:'restored'},{id:'uncertain'}];
  const saved=[{id:'E004',status:'JUNK'},{id:'custom',status:'JUNK'},
    {id:'restored',status:'PENDING_APPROVAL'},{id:'uncertain',status:'PENDING_APPROVAL'}];
  assert.deepEqual(view.folderRows(rows,saved,'junk').map(e=>e.id),['E004','custom']);
  assert.deepEqual(view.folderRows(rows,saved,'inbox').map(e=>e.id),['restored','uncertain']);
  assert.equal(view.folderRows([{id:'new'}],[],'inbox')[0].status,'READY');
});
test('clarification draft events map only to the branch actually executed',()=>{
  const event={event_type:'DRAFTED',details:{stage:'draft'}};
  assert.equal(view.eventStage(event,[{event_type:'STAGE_STARTED',details:{stage:'clarify'}}]),'clarify');
  assert.equal(view.eventStage(event,[]),'draft');
});
const reviewView = require('../beda/static/workflow-view.js');
require('node:test')('Human review filter contains only interpretation fallbacks',()=>{
  require('node:assert/strict').deepEqual(reviewView.folderRows([{id:'a'},{id:'b'}],
    [{id:'a',status:'NEEDS_HUMAN_REVIEW'},{id:'b',status:'QUEUED'}],'review').map(row=>row.id),['a']);
});
