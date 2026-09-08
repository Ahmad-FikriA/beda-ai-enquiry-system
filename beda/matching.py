import re
from typing import List, Optional

from beda.models import CRMRecord, Enquiry, MatchCandidate, Proposal


def normalize_phone(phone: Optional[str]) -> str:
    if not phone:
        return ""
    return re.sub(r"[^\d+]", "", phone)


def clean_company_name(name: Optional[str]) -> str:
    if not name:
        return ""
    cleaned = name.lower()
    for suffix in ["pty ltd", "pty. ltd.", "pty", "ltd", "inc", "co"]:
        cleaned = re.sub(rf"\b{suffix}\b", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def company_matches(record_company: str, text: str) -> bool:
    rec_clean = clean_company_name(record_company)
    if not rec_clean:
        return False
    if rec_clean in text:
        return True
    # Token-level / stem comparison (e.g. "logistic" vs "logistics")
    rec_tokens = [re.sub(r"s$", "", t) for t in rec_clean.split() if len(t) > 2]
    text_tokens = [re.sub(r"s$", "", t) for t in re.findall(r"\b\w+\b", text.lower())]
    if rec_tokens and all(tok in text_tokens for tok in rec_tokens):
        return True
    return False


def find_candidates(
    enquiry: Enquiry,
    proposal: Proposal,
    crm_records: List[CRMRecord],
    prior_enquiries: Optional[List[Enquiry]] = None,
) -> List[MatchCandidate]:
    """
    Evaluates CRM records against enquiry signals:
    - Exact email match
    - Phone number match (from body or extracted fields)
    - Company name similarity
    - Contact name similarity
    Identifies ambiguity when multiple strong candidates exist.
    """
    candidates: List[MatchCandidate] = []
    sender_email = (enquiry.sender_email or "").strip().lower()
    extracted_email = (proposal.extracted_fields.get("email") or "").strip().lower()
    extracted_phone = normalize_phone(proposal.extracted_fields.get("phone") or "")

    combined_text = f"{enquiry.subject} {enquiry.body} {enquiry.sender}".lower()

    for record in crm_records:
        score = 0.0
        reasons: List[str] = []
        rec_email = record.email.strip().lower() if record.email else ""
        rec_phone = normalize_phone(record.phone)
        rec_company = record.company.strip()
        rec_contact = record.contact.strip()

        # 1. Email check
        has_email_match = False
        if rec_email and (rec_email == sender_email or rec_email == extracted_email):
            score += 0.50
            has_email_match = True
            reasons.append(f"Exact email match: {rec_email}")

        # 2. Phone check
        has_phone_match = False
        if rec_phone and extracted_phone and (rec_phone == extracted_phone or rec_phone.endswith(extracted_phone[-8:])):
            score += 0.45
            has_phone_match = True
            reasons.append(f"Phone match: {record.phone}")

        # 3. Company match check
        if company_matches(rec_company, combined_text):
            score += 0.35
            reasons.append(f"Company mention: {rec_company}")

        # 4. Contact match check
        if rec_contact:
            contact_parts = rec_contact.lower().split()
            first_name = contact_parts[0] if contact_parts else ""
            if rec_contact.lower() in combined_text:
                score += 0.20
                reasons.append(f"Full contact match: {rec_contact}")
            elif first_name and len(first_name) > 2 and re.search(rf"\b{re.escape(first_name)}\b", combined_text):
                score += 0.10
                reasons.append(f"First name match: {first_name}")

        # Cap score at 1.0
        final_score = min(1.0, round(score, 2))

        if final_score >= 0.30:
            candidates.append(
                MatchCandidate(
                    crm_id=record.id,
                    company=record.company,
                    contact=record.contact,
                    email=record.email,
                    phone=record.phone,
                    score=final_score,
                    match_reasons=reasons,
                    ambiguous=False,
                )
            )

    # Sort descending by score
    candidates.sort(key=lambda c: c.score, reverse=True)

    # Check for ambiguity:
    # If the top candidates are materially close in score (e.g. <= 0.15 diff)
    # or if different candidates have conflicting primary signals (email vs phone)
    if len(candidates) >= 2:
        top_diff = abs(candidates[0].score - candidates[1].score)
        c0_has_email = any("email" in r.lower() for r in candidates[0].match_reasons)
        c1_has_phone = any("phone" in r.lower() for r in candidates[1].match_reasons)
        c0_has_phone = any("phone" in r.lower() for r in candidates[0].match_reasons)
        c1_has_email = any("email" in r.lower() for r in candidates[1].match_reasons)

        conflicting_signals = (c0_has_email and c1_has_phone) or (c0_has_phone and c1_has_email)

        if (top_diff <= 0.15 and candidates[1].score >= 0.50) or (conflicting_signals and candidates[1].score >= 0.50):
            for c in candidates:
                if c.score >= (candidates[0].score - 0.25):
                    c.ambiguous = True

    return candidates
