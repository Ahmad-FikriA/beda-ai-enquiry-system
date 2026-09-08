/* Presentation only: preserve exact source data in the collapsed technical view. */
(function (root) {
  const labels = {
    from:'Sender', body:'Message', text:'Response draft', category:'Enquiry type',
    confidence:'Confidence', facts:'Extracted facts', extracted_fields:'Extracted information',
    accepted_fields:'Verified information', unsupported_fields:'Information needing verification',
    missing_fields:'Missing information', evidence:'Supporting quote', rationale:'Reason',
    requires_approval:'Human approval required', action:'Recommended next step', owner:'Assigned reviewer',
    target_crm_id:'Suggested CRM record', crm_id:'CRM record', crm_modified:'CRM changed',
    external_message_sent:'External message sent', needs_research:'Research needed',
    ambiguous:'Needs match review', candidates:'Possible record matches', constraints:'Important limits',
    citations:'Supporting sources', unresolved_questions:'Questions still unanswered',
    attachment:'Supporting document', attachment_content:'Supporting document',
    run_version:'Run version', source_message_id:'Message reference', mode:'Execution mode',
    status:'Status', quote:'Source quote', source_id:'Source reference', sha256:'Document fingerprint'
  };
  const values = {
    JUNK:'In recoverable Junk folder', MOVE_TO_JUNK:'Move to recoverable Junk folder',
    REVIEW_RESTORED_ENQUIRY:'Review restored enquiry', local_quarantine:'Recoverable local quarantine',
    PENDING_APPROVAL:'Awaiting human approval', COMPLETED:'Completed', MODEL_FAILED:'Model request failed',
    PROCESSING:'Processing', SUPERSEDED:'Replaced by a newer run', REJECTED:'Rejected', SUCCEEDED:'Succeeded',
    REVIEW_ENQUIRY:'Review enquiry', REQUEST_MISSING_INFORMATION:'Request missing information',
    RESOLVE_AMBIGUOUS_LEAD:'Review possible record matches', REVIEW_CONTACT_CORRECTION:'Review contact correction',
    REVIEW_JUNK:'Review suspected junk', ESCALATE_TO_EXPERT:'Ask a specialist to review',
    EVIDENCE_FOUND:'Supporting evidence found', NOT_NEEDED:'Not needed', RESEARCH_REQUIRED:'Research required',
    SKIPPED_MISSING_INFORMATION:'Waiting for missing information', local_review_only:'Local review only',
    HIGH:'High', MEDIUM:'Medium', LOW:'Low'
  };
  const escape = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const label = key => Object.hasOwn(labels,key)?labels[key]:String(key).replace(/_/g,' ').replace(/^./, char=>char.toUpperCase());
  function highlightJson(value) {
    const json=JSON.stringify(value,null,2) ?? 'null';
    const pattern=/"(?:\\.|[^"\\])*"\s*:|"(?:\\.|[^"\\])*"|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
    let html='', end=0;
    for(const match of json.matchAll(pattern)) {
      html+=escape(json.slice(end,match.index));
      const token=match[0], kind=token.endsWith(':')?'key':token.startsWith('"')?'string':'literal';
      html+='<span class="json-'+kind+'">'+escape(token)+'</span>';end=match.index+token.length;
    }
    return html+escape(json.slice(end));
  }
  function renderValue(value, key='') {
    if(value==null||value==='')return '<span class="result-empty">Not provided</span>';
    if(Array.isArray(value))return value.length?'<ul class="result-list">'+value.map(item=>'<li>'+renderValue(item,key)+'</li>').join('')+'</ul>':'<span class="result-empty">None recorded</span>';
    if(typeof value==='object')return Object.keys(value).length?'<dl class="result-fields">'+Object.entries(value).map(([name,item])=>'<div class="result-field"><dt>'+escape(label(name))+'</dt><dd>'+renderValue(item,name)+'</dd></div>').join('')+'</dl>':'<span class="result-empty">None recorded</span>';
    if(typeof value==='boolean')return '<span class="result-boolean">'+(value?'Yes':'No')+'</span>';
    const enumField=['status','action','action_type','confidence','mode'].includes(key);
    const display=enumField&&Object.hasOwn(values,value)?values[value]:(['missing_fields','unsupported_fields'].includes(key)?label(value):String(value));
    return '<span class="result-text">'+escape(display)+'</span>';
  }
  function renderSection(title,value) {
    const technical=value!==null&&typeof value==='object'?'<details class="technical-details"><summary>Technical details · JSON</summary><pre>'+highlightJson(value)+'</pre></details>':'';
    return '<section class="result-section"><h3>'+escape(title)+'</h3><div class="result-card">'+renderValue(value,title==='Current state'?'status':'')+'</div>'+technical+'</section>';
  }
  const api={renderSection,renderValue,highlightJson};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.InspectorView=api;
})(globalThis);
