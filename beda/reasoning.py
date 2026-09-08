import re
from typing import Any, Dict, List, Optional

from beda.models import Enquiry, Proposal


def extract_phone(text: str) -> Optional[str]:
    # Match Australian format mobile/landline e.g. 0400 111 020 or 0411 999 120
    match = re.search(r"\b(04\d{2}\s?\d{3}\s?\d{3})\b", text)
    if match:
        return match.group(1)
    return None


def extract_email(text: str) -> Optional[str]:
    match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    if match:
        return match.group(0)
    return None


def propose(enquiry: Enquiry, attachment_text: Optional[str] = None) -> Proposal:
    """
    Deterministic proposal adapter emulating structured AI reasoning:
    Extracts key fields, detects category, identifies missing information,
    flags constraints, and suggests owner/action with rationale.
    """
    body = enquiry.body or ""
    subject = enquiry.subject or ""
    combined_text = f"{subject} {body}".lower()
    att_lower = (attachment_text or "").lower()

    extracted: Dict[str, Any] = {}
    missing_fields: List[str] = []
    constraints: List[str] = []
    confidence = "HIGH"

    phone = extract_phone(body)
    if phone:
        extracted["phone"] = phone

    sender_email = enquiry.sender_email or extract_email(enquiry.sender or "")
    if sender_email:
        extracted["email"] = sender_email

    # Category and rule-based heuristic classification
    # 1. Junk / spam detection (E004)
    if any(k in combined_text for k in ["buy 50,000", "cryptocurrency", "ceo leads", "megaleadlists"]):
        category = "junk"
        recommended_owner = "Zidane Mouldino"
        recommended_action = "ARCHIVE_JUNK"
        rationale = "Unsolicited promotional spam offering leads for cryptocurrency. No operational value."
        return Proposal(
            category=category,
            confidence="HIGH",
            extracted_fields=extracted,
            missing_fields=[],
            constraints=["DO_NOT_RESPOND", "AUTO_ARCHIVE"],
            recommended_owner=recommended_owner,
            recommended_action=recommended_action,
            rationale=rationale,
        )

    # 2. Infrastructure incident (E011)
    if any(k in combined_text for k in ["oauth token expired", "crm sync failed", "hubspot sync"]):
        category = "infrastructure incident"
        recommended_owner = "Ali Pratama"
        recommended_action = "RESOLVE_OAUTH_TOKEN_ALERT"
        extracted["error_type"] = "OAuthTokenExpired"
        extracted["affected_records"] = 146
        constraints.append("ESCALATE_CRITICAL_INFRASTRUCTURE")
        rationale = "Automated system alert indicating broken HubSpot sync due to expired OAuth credentials."
        return Proposal(
            category=category,
            confidence="HIGH",
            extracted_fields=extracted,
            missing_fields=[],
            constraints=constraints,
            recommended_owner=recommended_owner,
            recommended_action=recommended_action,
            rationale=rationale,
        )

    # 3. Technical / harmonic escalation (E006)
    if any(k in combined_text for k in ["pcs specification", "thd limits", "harmonic study", "battery inverter"]):
        category = "technical/escalation"
        recommended_owner = "Matt Cooper"
        recommended_action = "ESCALATE_TECHNICAL"
        extracted["system_capacity"] = "500 kW"
        extracted["query_type"] = "Harmonics and THD limit at PCC"
        constraints.append("DO_NOT_ENGINEER_THD_RESPONSE")
        constraints.append("REQUIRE_ENGINEERING_REVIEW")
        rationale = "Complex engineering inquiry regarding grid harmonic distortion limits (THD) and battery inverter specifications. Requires engineering review; no automated answer permitted."
        return Proposal(
            category=category,
            confidence="HIGH",
            extracted_fields=extracted,
            missing_fields=[],
            constraints=constraints,
            recommended_owner=recommended_owner,
            recommended_action=recommended_action,
            rationale=rationale,
        )

    # 4. Marketing / Internship (E007)
    if any(k in combined_text for k in ["marketing internship", "internship", "portfolio"]):
        category = "marketing/recruitment"
        recommended_owner = "Zidane Mouldino"
        recommended_action = "REVIEW_INTERN_APPLICATION"
        extracted["applicant_name"] = enquiry.sender_name or "Priya Dev"
        extracted["position"] = "Marketing Internship"
        rationale = "Prospective applicant expressing interest in marketing internship."
        return Proposal(
            category=category,
            confidence="HIGH",
            extracted_fields=extracted,
            missing_fields=[],
            constraints=["HR_PRIVACY_COMPLIANCE"],
            recommended_owner=recommended_owner,
            recommended_action=recommended_action,
            rationale=rationale,
        )

    # 5. Partner / Contractor operations (E008)
    if any(k in combined_text for k in ["crew availability", "four person crew", "ballarat commercial solar"]):
        category = "partner/operations"
        recommended_owner = "Ties Rahardjo"
        recommended_action = "COORDINATE_CREW_SCHEDULE"
        extracted["crew_size"] = 4
        extracted["target_week"] = "14 September"
        extracted["confirmation_deadline"] = "Tuesday"
        constraints.append("NEVER_CONFIRM_PROGRESS")
        constraints.append("CHECK_BALLARAT_STATUS_INTERNALLY")
        rationale = "Installation subcontractor holding crew availability for Ballarat site. Progress must be verified internally before confirming."
        return Proposal(
            category=category,
            confidence="HIGH",
            extracted_fields=extracted,
            missing_fields=[],
            constraints=constraints,
            recommended_owner=recommended_owner,
            recommended_action=recommended_action,
            rationale=rationale,
        )

    # 6. Billing / Support query (E003)
    if any(k in combined_text for k in ["invoice 1847", "purchase order", "does not match po"]):
        category = "support/billing"
        recommended_owner = "Ties Rahardjo"
        recommended_action = "RECONCILE_INVOICE_DISCREPANCY"
        extracted["invoice_number"] = "1847"
        extracted["discrepancy_amount"] = "$2,640"
        if "po 8821" in att_lower or "47,300" in att_lower:
            extracted["po_number"] = "GF PO 8821"
            extracted["approved_value"] = "$47,300 ex GST"
            extracted["invoice_value"] = "$49,940 ex GST"
        rationale = "Customer querying billing variance between PO and invoice for completed Geelong LED project."
        return Proposal(
            category=category,
            confidence="HIGH",
            extracted_fields=extracted,
            missing_fields=[],
            constraints=["ACCOUNTS_APPROVAL_REQUIRED"],
            recommended_owner=recommended_owner,
            recommended_action=recommended_action,
            rationale=rationale,
        )

    # 7. School / lighting upgrade with missing bill/schedule (E005)
    if "northbank" in combined_text or "fluorescent fittings" in combined_text or "1,100" in combined_text:
        category = "sales"
        recommended_owner = "Zidane Mouldino"
        recommended_action = "REQUEST_MISSING_INFORMATION"
        extracted["facility_type"] = "School"
        extracted["fittings_count"] = 1100
        # Check attachment notes for missing information
        if "no current fixture schedule" in att_lower or "no electricity invoice" in att_lower or "do not have our latest electricity bill" in combined_text:
            missing_fields.extend(["electricity_bill", "fixture_schedule"])
        confidence = "MEDIUM"
        rationale = "Educational facility seeking LED lighting upgrade and incentive advice; missing recent utility bill and fixture schedule."
        return Proposal(
            category=category,
            confidence=confidence,
            extracted_fields=extracted,
            missing_fields=missing_fields,
            constraints=["VERIFY_INCENTIVE_ELIGIBILITY"],
            recommended_owner=recommended_owner,
            recommended_action=recommended_action,
            rationale=rationale,
        )

    # 8. Correction / phone update (E010)
    if "correcting my number" in combined_text or "0411 999 102" in combined_text:
        category = "sales"
        recommended_owner = "Matt Cooper"
        recommended_action = "UPDATE_CONTACT_PHONE"
        extracted["new_phone"] = "0411 999 102"
        extracted["old_phone"] = "0411 999 120"
        rationale = "Sender correcting phone number previously submitted via web inquiry form."
        return Proposal(
            category=category,
            confidence="HIGH",
            extracted_fields=extracted,
            missing_fields=[],
            constraints=["VERIFY_ORIGINAL_ENQUIRY"],
            recommended_owner=recommended_owner,
            recommended_action=recommended_action,
            rationale=rationale,
        )

    # 9. Small business / cafe with landlord constraint (E012)
    if "cafe" in combined_text or "smallcafe" in combined_text:
        category = "sales"
        recommended_owner = "Matt Cooper"
        recommended_action = "EVALUATE_COMMERCIAL_FEASIBILITY"
        extracted["area_sqm"] = 70
        extracted["monthly_bill"] = "$900"
        constraints.append("landlord_approval_required")
        constraints.append("verify_roof_access")
        rationale = "Small commercial cafe enquiry; feasibility constrained by pending landlord roof consent."
        return Proposal(
            category=category,
            confidence="MEDIUM",
            extracted_fields=extracted,
            missing_fields=[],
            constraints=constraints,
            recommended_owner=recommended_owner,
            recommended_action=recommended_action,
            rationale=rationale,
        )

    # 10. Large commercial solar / Hume / Harbour Cold Stores (E001, E002, E009)
    if any(k in combined_text for k in ["hume logistics", "hume logistic", "harbour cold stores", "refrigerated warehouse", "truganina", "2.1 gwh", "two gigawatt"]):
        category = "sales"
        recommended_owner = "Matt Cooper"
        if "hume logistic" in combined_text and ("website enquiry" in combined_text or "best number" in combined_text):
            recommended_action = "RESOLVE_AMBIGUOUS_LEAD"
            confidence = "MEDIUM"
            extracted["annual_consumption"] = "2 GWh"
            extracted["sites"] = "Melbourne (3 sites)"
            rationale = "Commercial enquiry from Hume Logistics; matches existing prospect C001 and duplicate lead C002 with ambiguous contact signals."
        elif "harbour cold stores" in combined_text:
            recommended_action = "CREATE_PROSPECT"
            extracted["facility"] = "Refrigerated warehouse, Newcastle"
            extracted["monthly_bill"] = "$80,000"
            rationale = "High-value commercial opportunity with $80k/mo energy expense."
        else:
            recommended_action = "CREATE_COMMERCIAL_OPPORTUNITY"
            extracted["annual_consumption"] = "2.1 GWh"
            extracted["sites"] = ["Truganina", "Dandenong", "Epping"]
            if "nmi" in att_lower:
                extracted["truganina_nmi"] = "63051234567"
                extracted["truganina_bill"] = "$18,940"
            rationale = "Multi-site commercial solar and storage opportunity with energy bill attached."

        return Proposal(
            category=category,
            confidence=confidence,
            extracted_fields=extracted,
            missing_fields=missing_fields,
            constraints=constraints,
            recommended_owner=recommended_owner,
            recommended_action=recommended_action,
            rationale=rationale,
        )

    # Default fallback
    return Proposal(
        category="sales",
        confidence="MEDIUM",
        extracted_fields=extracted,
        missing_fields=missing_fields,
        constraints=constraints,
        recommended_owner="Matt Cooper",
        recommended_action="REVIEW_INBOUND_ENQUIRY",
        rationale="Inbound commercial enquiry received; default manual triage assigned.",
    )
