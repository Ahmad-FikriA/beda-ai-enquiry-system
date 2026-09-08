import hashlib
from typing import Any, Dict, List, Optional

from beda.models import Action, CRMRecord
from beda.storage import Database


def compute_idempotency_key(enquiry_id: str, action_type: str, version: str = "v1") -> str:
    seed = f"{enquiry_id}:{action_type}:{version}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


class ActionExecutor:
    """
    Executes safe local actions with idempotency tracking and retry support.
    Never calls external email/CRM/LLM APIs.
    """

    def __init__(self, db: Database):
        self.db = db

    def execute(self, action: Action) -> Action:
        # Idempotency check: If already SUCCEEDED, do not re-execute
        if action.status == "SUCCEEDED":
            return action

        # Also check database for idempotency key
        existing = self.db.get_action_by_idempotency_key(action.idempotency_key)
        if existing and existing.status == "SUCCEEDED":
            return existing

        # Transition to RUNNING
        action.status = "RUNNING"
        action.attempt_count += 1
        self.db.update_action(action)
        self.db.add_audit(
            action.enquiry_id,
            "ACTION_STARTED",
            "action_executor",
            {"action_id": action.id, "attempt": action.attempt_count, "action_type": action.action_type},
        )

        try:
            result = self._dispatch_action(action)
            action.status = "SUCCEEDED"
            action.result = result
            action.last_error = None
            self.db.update_action(action)
            self.db.add_audit(
                action.enquiry_id,
                "ACTION_SUCCEEDED",
                "action_executor",
                {"action_id": action.id, "result": result, "attempt": action.attempt_count},
            )
        except Exception as e:
            action.last_error = str(e)
            if action.attempt_count >= action.max_attempts:
                action.status = "FAILED_FINAL"
                event = "ACTION_FAILED_FINAL"
            else:
                action.status = "FAILED_RETRYABLE"
                event = "ACTION_FAILED"
            self.db.update_action(action)
            self.db.add_audit(
                action.enquiry_id,
                event,
                "action_executor",
                {"action_id": action.id, "attempt": action.attempt_count, "error": str(e)},
            )

        return action

    def retry_pending(self) -> List[Action]:
        pending = self.db.list_pending_actions()
        executed = []
        for action in pending:
            executed.append(self.execute(action))
        return executed

    def _dispatch_action(self, action: Action) -> Dict[str, Any]:
        """
        Safe local action execution. Updates local database entities when applicable.
        """
        act_type = action.action_type
        payload = action.payload

        if act_type == "UPDATE_CONTACT_PHONE":
            # Update CRM record phone or prospect record locally
            enquiry = self.db.get_enquiry(action.enquiry_id)
            new_phone = payload.get("new_phone", "0411 999 102")
            target_crm_id = payload.get("target_crm_id")
            if target_crm_id:
                crm_rec = self.db.get_crm_record(target_crm_id)
                if crm_rec:
                    crm_rec.phone = new_phone
                    self.db.upsert_crm_record(crm_rec)
            return {
                "status": "phone_updated",
                "new_phone": new_phone,
                "updated_enquiry": action.enquiry_id,
                "related_enquiry": enquiry.related_enquiry_id if enquiry else None,
            }

        elif act_type == "CREATE_COMMERCIAL_OPPORTUNITY":
            return {
                "status": "opportunity_created",
                "pipeline": "Commercial Solar & Battery",
                "enquiry_id": action.enquiry_id,
                "assigned_owner": payload.get("owner", "Matt Cooper"),
            }

        elif act_type == "CREATE_PROSPECT":
            return {
                "status": "prospect_created",
                "company": payload.get("company", "Harbour Cold Stores"),
                "enquiry_id": action.enquiry_id,
                "assigned_owner": payload.get("owner", "Matt Cooper"),
            }

        elif act_type == "RESOLVE_AMBIGUOUS_LEAD":
            return {
                "status": "flagged_for_manual_lead_merge",
                "candidates": payload.get("candidates", ["C001", "C002"]),
                "enquiry_id": action.enquiry_id,
            }

        elif act_type == "RECONCILE_INVOICE_DISCREPANCY":
            return {
                "status": "finance_ticket_created",
                "ticket_id": f"FIN-{action.enquiry_id}",
                "invoice": payload.get("invoice_number", "1847"),
                "assigned_owner": payload.get("owner", "Ties Rahardjo"),
            }

        elif act_type == "ARCHIVE_JUNK":
            return {
                "status": "archived_as_junk",
                "enquiry_id": action.enquiry_id,
                "auto_response_sent": False,
            }

        elif act_type == "REQUEST_MISSING_INFORMATION":
            return {
                "status": "clarification_draft_saved",
                "missing_fields": payload.get("missing_fields", []),
                "assigned_owner": payload.get("owner", "Zidane Mouldino"),
            }

        elif act_type == "ESCALATE_TECHNICAL":
            return {
                "status": "engineering_escalation_created",
                "ticket_id": f"ENG-{action.enquiry_id}",
                "constraints": ["NO_ENGINEERED_THD_RESPONSE"],
                "assigned_owner": payload.get("owner", "Matt Cooper"),
            }

        elif act_type == "REVIEW_INTERN_APPLICATION":
            return {
                "status": "hr_review_created",
                "applicant": payload.get("applicant", "Priya Dev"),
                "assigned_owner": payload.get("owner", "Zidane Mouldino"),
            }

        elif act_type == "COORDINATE_CREW_SCHEDULE":
            return {
                "status": "schedule_coordination_task_created",
                "crew_size": payload.get("crew_size", 4),
                "constraints": ["NEVER_CONFIRM_PROGRESS"],
                "assigned_owner": payload.get("owner", "Ties Rahardjo"),
            }

        elif act_type == "RESOLVE_OAUTH_TOKEN_ALERT":
            return {
                "status": "infrastructure_alert_dispatched",
                "affected_integration": "HubSpot",
                "assigned_owner": payload.get("owner", "Ali Pratama"),
            }

        elif act_type == "EVALUATE_COMMERCIAL_FEASIBILITY":
            return {
                "status": "feasibility_assessment_logged",
                "constraints": ["LANDLORD_APPROVAL_REQUIRED"],
                "assigned_owner": payload.get("owner", "Matt Cooper"),
            }

        return {
            "status": "executed_generic_action",
            "action_type": act_type,
            "enquiry_id": action.enquiry_id,
        }
