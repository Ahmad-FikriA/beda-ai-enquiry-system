"""Live pipeline: model interprets; policy controls; humans approve local effects."""
import re
from beda.llm import Gemini, Analysis, Draft, ModelError
from beda.models import Enquiry, Proposal, Recommendation, Action
from beda.service import parse_sender
from beda.matching import find_candidates, normalize_phone
from beda.actions import compute_idempotency_key
from beda.runs import Runs
from beda.research import research
from beda.documents import Documents
from beda.junk import Junk

OWNERS = {"sales": "Matt Cooper", "billing": "Ties Rahardjo", "technical": "Matt Cooper",
          "recruitment": "Zidane Mouldino", "operations": "Ties Rahardjo", "infrastructure": "Ali Pratama",
          "junk": "Zidane Mouldino", "unknown": "Ties Rahardjo", "correction": "Ali Pratama"}


class LiveService:
    def __init__(self, db, model=None):
        self.db, self.model = db, model or Gemini()
        self.runs = Runs(db)
        self.documents = Documents(db)
        self.junk = Junk(db, self.runs)

    def process_input(self, payload, force=False, draft_only=False, request_id=None):
        eid = payload.get("id") or payload.get("source_message_id")
        if not isinstance(eid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", eid):
            raise ValueError("ID must contain 1–80 letters, digits, underscores or hyphens")
        for field in ("from", "subject", "body", "attachment_content"):
            if payload.get(field) is not None and not isinstance(payload[field], str):
                raise ValueError(f"{field} must be text")
        eq = self.db.get_enquiry(eid)
        if request_id and self.runs.seen(request_id):
            return eq
        if eq and eq.status != "MODEL_FAILED" and not force:
            return eq
        if draft_only and (not eq or not eq.proposal or not eq.recommendation):
            raise ValueError('A validated proposal is required before regenerating a draft')
        if draft_only and eq.proposal.category == 'junk':
            raise ValueError('Junk has no response draft. Restore it and use a new full run to reassess it.')
        previous_research = next((a.details for a in reversed(self.db.list_audit(eid)) if a.event_type=='RESEARCH_COMPLETED'), None) if draft_only else None
        version=self.runs.begin(eid,'draft' if draft_only else 'full',request_id)
        if not eq:
            name, email = parse_sender(payload.get("from", ""))
            eq = Enquiry(id=eid, source_message_id=eid, sender=payload.get("from", ""), sender_name=name,
                         sender_email=email, subject=payload.get("subject", "").strip(), body=payload.get("body", "").strip(),
                         attachment_content=payload.get("attachment_content"), attachment_filename=payload.get("attachment_filename"), raw_payload=payload)
            self.db.create_enquiry(eq)
            self.event(eq, "RECEIVED", {"source_message_id": eid})
            if payload.get("import_warning"):
                self.event(eq, "IMPORT_WARNING", payload["import_warning"])
        eq.status='PROCESSING'
        eq.draft_response=None
        if not draft_only:
            if force:
                eq.attachment_content=payload.get('attachment_content')
                eq.raw_payload=dict(payload)
            eq.proposal=None
            eq.recommendation=None
            eq.match_candidates=[]
            eq.related_enquiry_id=None
        self.db.update_enquiry(eq)
        self.db.save_match_candidates(eid,eq.match_candidates)
        self.event(eq,'RUN_STARTED',{'version':version,'mode':'draft' if draft_only else 'full',
            'message':f'Run v{version} started. Previous pending approvals are superseded.'})
        if not draft_only and payload.get('attachment_revision'):
            self.event(eq,'ATTACHMENT_SELECTED',{'stage':'input','filename':eq.attachment_filename,
                'revision':payload['attachment_revision'],'sha256':payload.get('attachment_sha256'),
                'message':f"Using {eq.attachment_filename}, document revision {payload['attachment_revision']}."})
        if draft_only:
            self.event(eq,'CONTEXT_REUSED',{'proposal':eq.proposal.model_dump(),'research':previous_research,
                'message':'Validated facts and saved research reused; generating a fresh draft with a new approval.'})
            try:
                self.finish(eq,previous_research)
            except ModelError as error:
                self.fail(eq,error)
            return eq
        self.event(eq, "NORMALIZED", {"subject": eq.subject, "body": eq.body})
        self.event(eq, "DEDUPLICATED", {"source_message_id": eid, "duplicate": False})
        log = lambda event, details: self.event(eq, event, details)
        try:
            self.event(eq, "STAGE_STARTED", {"stage": "extract", "message": "Asking Gemini to classify and extract supported facts."})
            analysis = self.model.generate(
                "You triage INCOMING messages addressed TO BEDA, an energy services business handling solar, batteries, "
                "LED lighting and electricity cost reduction. The sender is NOT BEDA. "
                "Classify from BEDA's perspective: sales means a prospective customer seeking BEDA services, "
                "not any message with a sales intent. Unsolicited unrelated advertising, bulk contact-list offers, "
                "scams and irrelevant promotions are junk, even if the sender is selling something. "
                "Relevant supplier/partner messages may be operations, not automatically junk. "
                "Existing customer questions may be billing or technical. Gibberish or unclear intent is unknown, "
                "not automatically junk. Preserve uncertainty; use LOW or MEDIUM confidence when unclear. "
                "For junk, extract supported evidence of the offer but do not request sales qualification details. "
                "Extract facts with exact evidence quotes from message or attachment. "
                "Use fact names phone, old_phone, new_phone, company, contact where applicable. "
                "For corrections extract both old and new values. Do not infer a company or person from an email domain. "
                "Identify missing information, constraints, and whether outside knowledge is needed. Billing is not sales.",
                {"sender": eq.sender, "subject": eq.subject, "message": eq.body, "attachment": eq.attachment_content,
                 "reviewer_marked_not_junk": self.junk.was_restored(eq.id)}, Analysis, log)
            self.event(eq, "CLASSIFIED", analysis.model_dump())
            source = " ".join((eq.sender or "", eq.subject, eq.body, eq.attachment_content or ""))
            fields, unsupported = {}, []
            normalized = lambda value: " ".join(value.casefold().split())
            for fact in analysis.facts:
                if fact.evidence.strip() and normalized(fact.evidence) in normalized(source) and normalized(fact.value) in normalized(fact.evidence):
                    fields[fact.name] = fact.value
                else:
                    unsupported.append(fact.name)
            fields["email"] = eq.sender_email or ""
            proposal = Proposal(category=analysis.category, confidence="LOW" if unsupported else analysis.confidence,
                extracted_fields=fields, missing_fields=analysis.missing_fields + [f"verify_{name}" for name in unsupported],
                constraints=analysis.constraints, rationale=analysis.rationale)
            eq.proposal = proposal
            self.event(eq, "VALIDATED", {"accepted_fields": fields, "unsupported_fields": unsupported})
            eq.match_candidates = find_candidates(eq, proposal, self.db.list_crm_records())
            self.event(eq, "CRM_MATCHED", {"candidates": [c.model_dump() for c in eq.match_candidates]})
            # Junk policy precedes sales-completeness checks. Even dubious junk gets no reply.
            if analysis.category == 'junk':
                checks={'high_confidence':proposal.confidence=='HIGH',
                        'supported_evidence':bool(analysis.facts) and not unsupported,
                        'no_crm_match':not eq.match_candidates,
                        'not_previously_restored':not self.junk.was_restored(eq.id)}
                automatic=all(checks.values())
                eq.recommendation=Recommendation(action='MOVE_TO_JUNK' if automatic else 'REVIEW_JUNK',
                    owner=OWNERS['junk'],confidence=proposal.confidence,requires_approval=not automatic,
                    explanation=analysis.rationale)
                self.event(eq,'ROUTED',eq.recommendation.model_dump())
                self.event(eq,'JUNK_POLICY_CHECKED',{'stage':'junk','checks':checks,'automatic':automatic,
                    'message':'Local quarantine permitted.' if automatic else 'Junk is uncertain, matched to CRM, or previously restored. Human review required.'})
                if automatic:
                    return self.junk.move(eq,version,automatic=True)
                self.finish(eq)
                return eq
            if analysis.category == "correction" and fields.get("old_phone"):
                old = normalize_phone(fields["old_phone"])
                matches = [p for p in self.db.list_enquiries() if p.id != eid and p.proposal and
                           normalize_phone(str(p.proposal.extracted_fields.get("phone", ""))) == old]
                if len(matches) == 1:
                    eq.related_enquiry_id = matches[0].id
            action = "REVIEW_ENQUIRY"
            if any(c.ambiguous for c in eq.match_candidates):
                action = "RESOLVE_AMBIGUOUS_LEAD"
            elif proposal.missing_fields:
                action = "REQUEST_MISSING_INFORMATION"
            elif analysis.category == "correction":
                action = "REVIEW_CONTACT_CORRECTION"
            elif analysis.category in ("technical", "infrastructure"):
                action = "ESCALATE_TO_EXPERT"
            eq.recommendation = Recommendation(action=action, owner=OWNERS[analysis.category], requires_approval=True,
                confidence=proposal.confidence, explanation=analysis.rationale,
                target_crm_id=eq.match_candidates[0].crm_id if eq.match_candidates and not eq.match_candidates[0].ambiguous else None)
            self.event(eq, "ROUTED", eq.recommendation.model_dump())
            self.event(eq, "INFORMATION_CHECKED", {"missing_fields": proposal.missing_fields})
            should_research=analysis.needs_research and not proposal.missing_fields and analysis.category not in ('junk','infrastructure')
            self.event(eq, "RESEARCH_CHECKED", {"needed": should_research,
                "status": "RESEARCH_REQUIRED" if should_research else "SKIPPED_MISSING_INFORMATION" if proposal.missing_fields else "NOT_NEEDED"})
            findings=research(self.model,eq,log) if should_research else None
            if findings and (findings['status']!='EVIDENCE_FOUND' or analysis.category=='technical'):
                eq.recommendation.action='ESCALATE_TO_EXPERT'
                self.event(eq,'RESEARCH_ESCALATED',{'stage':'expert','reason':'Unresolved evidence or technical sign-off requires a human.'})
            self.finish(eq,findings)
        except ModelError as error:
            self.fail(eq,error)
        return eq

    def finish(self,eq,findings=None):
        proposal=eq.proposal
        # Rejected evidence is retained in the audit, never forwarded to drafting.
        grounded_findings={key:findings[key] for key in ('status','citations','unresolved_questions') if key in findings} if findings else None
        if proposal.category not in ('junk','infrastructure'):
            stage='clarify' if proposal.missing_fields else 'draft'
            self.event(eq,'STAGE_STARTED',{'stage':stage,'message':'Drafting with validated facts and cited research evidence.'})
            draft=self.model.generate('Write ON BEHALF OF BEDA, replying TO the incoming sender. BEDA provides energy services, '
                'including solar, batteries, LED lighting and electricity cost reduction. Never impersonate the sender '
                'or adopt their advertised products, payment instructions or contact details as BEDA offerings. '
                'Draft a concise response for human review using only validated facts and supplied research quotes. '
                'Cite research source IDs when used. Ask about missing information and preserve unresolved questions. '
                'Never claim that approval, CRM updates, engineering sign-off, eligibility verification or external actions have occurred.',
                {'facts':proposal.extracted_fields,'missing':proposal.missing_fields,'constraints':proposal.constraints,
                 'category':proposal.category,'research':grounded_findings,'action':eq.recommendation.action,
                 'reply_to':eq.sender,'incoming_subject':eq.subject,'incoming_message':eq.body},Draft,
                lambda event,details:self.event(eq,event,details))
            eq.draft_response=draft.text
            self.event(eq,'DRAFTED',{'text':draft.text,'stage':stage})
        version=self.runs.current(eq.id)
        eq.status='PENDING_APPROVAL'
        self.db.update_enquiry(eq)
        self.db.create_action(Action(id=f'LIVE-{eq.id}-v{version}',enquiry_id=eq.id,action_type=eq.recommendation.action,
            idempotency_key=compute_idempotency_key(eq.id,eq.recommendation.action,f'live-v{version}'),
            payload={'owner':eq.recommendation.owner,'draft':eq.draft_response,'mode':'local_review_only','run_version':version}))
        self.event(eq,'APPROVAL_REQUESTED',{'action':eq.recommendation.action,'owner':eq.recommendation.owner})
        self.runs.save(eq)

    def fail(self,eq,error):
        eq.status='MODEL_FAILED'
        self.db.update_enquiry(eq)
        self.event(eq,'ESCALATED',{'error':str(error),'retry':'Retry starts a new preserved version'})
        self.runs.save(eq)

    def rerun(self,eid,mode,request_id):
        eq=self.db.get_enquiry(eid)
        if not eq or eq.status=='PROCESSING':
            raise ValueError('Select a finished or failed enquiry')
        if mode not in ('full','draft') or not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',request_id):
            raise ValueError('Valid mode and unique request_id required')
        payload=eq.raw_payload or {'id':eid,'from':eq.sender,'subject':eq.subject,'body':eq.body,'attachment_content':eq.attachment_content}
        if mode=='full':
            payload=self.documents.attach({**payload,'attachment_filename':eq.attachment_filename})
        return self.process_input(payload,force=True,draft_only=mode=='draft',request_id=request_id)

    def event(self, eq, event, details):
        self.db.add_audit(eq.id, event, "live_pipeline", {**details,'run_version':self.runs.current(eq.id)})

    def restore_junk(self, eid, version):
        return self.junk.restore(eid, version)

    def decide(self, eid, approve, version=None):
        current=self.runs.current(eid)
        if version is not None and version!=current:
            raise ValueError('This approval belongs to an older run. Review the latest version.')
        eq = self.db.get_enquiry(eid)
        if not eq or eq.status != "PENDING_APPROVAL":
            raise ValueError("Only pending enquiries can be reviewed")
        action = next((a for a in self.db.list_actions_for_enquiry(eid) if a.payload.get('run_version')==current),None)
        if action is None:
            raise ValueError('Create a new run before reviewing legacy results')
        if not action.id.startswith("LIVE-"):
            raise ValueError("Legacy simulation: use a fresh live run")
        if approve and action.action_type == 'REVIEW_JUNK':
            self.junk.move(eq,current,automatic=False,pending_action=action)
            return
        # One transaction records approval and the local effect. No external dispatch.
        with self.db._connection() as conn:
            status = "SUCCEEDED" if approve else "REJECTED"
            import json
            from beda.models import utc_now_iso
            changed = conn.execute("UPDATE actions SET status=?, attempt_count=?, result_json=? WHERE id=? AND status='PENDING_APPROVAL'",
                (status, int(approve), json.dumps({"mode": "local_review_only", "external_message_sent": False,
                    "crm_modified": False, "review_recorded": True}), action.id)).rowcount
            if not changed:
                raise ValueError("Already reviewed")
            conn.execute("UPDATE enquiries SET status=? WHERE id=?", ("COMPLETED" if approve else "REJECTED", eid))
            for event in (["APPROVED", "ACTION_STARTED", "ACTION_SUCCEEDED"] if approve else ["REJECTED"]):
                conn.execute("INSERT INTO audit_events(enquiry_id,event_type,actor,details_json,created_at) VALUES(?,?,?,?,?)",
                             (eid, event, "local_reviewer", json.dumps({"action_id": action.id, "mode": "local_review_only",'run_version':current}), utc_now_iso()))
        self.runs.save(self.db.get_enquiry(eid))
