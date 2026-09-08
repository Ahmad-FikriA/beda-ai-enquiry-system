/* Shared, testable mapping from saved events to visible workflow stages. */
(function(root){
  const eventStages={RESEARCH_RETRIEVED:'expert',RESEARCH_COMPLETED:'expert',RESEARCH_ESCALATED:'expert',RUN_STARTED:'input',CONTEXT_REUSED:'input',RECEIVED:'input',IMPORT_WARNING:'input',NORMALIZED:'normalize',DEDUPLICATED:'normalize',CLASSIFIED:'extract',VALIDATED:'validate',CRM_MATCHED:'match',ROUTED:'route',INFORMATION_CHECKED:'complete',RESEARCH_CHECKED:'research',DRAFTED:'draft',APPROVAL_REQUESTED:'approval',APPROVED:'approval',REJECTED:'approval',ACTION_STARTED:'execute',ACTION_SUCCEEDED:'execute',ESCALATED:'failure',JUNK_POLICY_CHECKED:'junk',JUNK_QUARANTINED:'junk',JUNK_RESTORED:'junk',JUNK_AUDITED:'audit'};
  function eventStage(event,audit=[]){
    let id=event.details.stage||eventStages[event.event_type]||'extract';
    if(id==='draft'&&audit.some(e=>e.event_type==='STAGE_STARTED'&&e.details.stage==='clarify'))id='clarify';
    return id;
  }
  function folderRows(rows,enquiries,folder){
    const saved=new Map(enquiries.map(e=>[e.id,e]));
    return rows.map(row=>({...row,status:saved.get(row.id)?.status||'READY'}))
      .filter(row=>folder==='review'?row.status==='NEEDS_HUMAN_REVIEW':(row.status==='JUNK')===(folder==='junk'));
  }
  const api={eventStage,folderRows};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.WorkflowView=api;
})(globalThis);
