# Controlled Enquiry Build — Design

## Purpose

Build a local, inspectable Test 2 prototype that processes the supplied synthetic enquiries without external service calls. It demonstrates a controlled boundary: AI-style reasoning proposes structured information; deterministic application code validates, records, and controls all actions; a person approves consequential actions.

## Scope and constraints

- Keep the supplied CSV data unchanged and use it as the input fixture set.
- Use Python, Pydantic, SQLite, and the standard-library HTTP server; avoid a frontend framework and external CRM, email, or model calls.
- Treat every input field and attached document as untrusted data. No content can change routing permissions or invoke arbitrary tools.
- Preserve missing and ambiguous information rather than creating facts or silently merging records.
- Require an optional local API key at HTTP ingress and reject malformed input.
- Store persistent audit events, action state, retry attempts, and deterministic idempotency keys.

## Architecture

`app.py` will expose a small local HTTP interface and a JSON ingestion endpoint. `service.py` will orchestrate ingestion and never perform an external side effect. `storage.py` will own SQLite schema and persistence. `reasoning.py` will contain a deliberately isolated local proposal adapter: deterministic heuristics that emulate the shape and uncertainty of an LLM response, with no credentials or tools. `matching.py` will create CRM candidates from stable signals, score them, and flag ambiguity. `actions.py` will model safe, local action execution and recovery.

The pipeline is:

```
CSV / POST input → request validation + ingress check → normalisation + document load
→ source-ID idempotency check → proposal adapter → Pydantic validation
→ CRM candidate matching → deterministic recommendation → persisted draft
→ approval queue → local action executor → append-only audit timeline
```

## Data and decision model

SQLite tables store enquiries, CRM records, match candidates, recommendations, drafts, actions, and audit events. Raw content is stored only for the demonstration; the cleanup command applies a configurable raw-content retention period while preserving de-identified audit metadata. Each action has a stable `sha256(enquiry_id + action_type + payload_version)` idempotency key, a state (`PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED_RETRYABLE`, `FAILED_FINAL`), and an attempt count.

CRM matching uses source email, stated contact/company, phone numbers, and the relationship to previously processed enquiries. A high-confidence exact candidate can be recommended, but E002 must retain both C001 and C002 as candidates because its email matches C002 while its shared phone and context point to C001. It must not create a new CRM record. E010 is linked to E009 by the correction text and prior phone number, so it is a correction to the same prospect, not a new lead.

## Reasoning and controls

The proposal adapter returns a typed `Proposal` containing category, confidence, extracted fields, missing fields, constraints, recommended owner, recommended action, and rationale. It does not write storage or execute tools. Application code validates the object, sets confidence states (`HIGH`, `MEDIUM`, `LOW`), determines whether a CRM change or outgoing response is consequential, and creates an approval request.

Known categories include sales, support/billing, technical/escalation, partner/operations, marketing/recruitment, infrastructure incident, insufficient information, and junk. E006 does not receive an engineered THD answer; it is escalated. E008 never confirms project progress. E012 retains the landlord-approval constraint. E004 is archived with no draft.

## Failure handling

Only local simulated actions are executed. A retryable failure changes state to `FAILED_RETRYABLE`, records an `ACTION_FAILED` event including attempt and error class, and can be retried up to three times. A final failure is escalated. Successful side effects are recorded by idempotency key; a retry/reconciliation pass sees that key and never performs the same action twice. Database writes use transactions, and action state is persisted before and after every attempt so an interrupted process is never reported as successful.

## Inspection UI

The index page lists processed enquiries and their status. A detail page shows the original input, extracted data and uncertainty, attachments, CRM candidates, recommended owner/action, draft, approval controls, action result, and chronological audit trail. The UI is intentionally plain and local.

## Verification

Tests cover input idempotency, ambiguous CRM matching for E002, E005 missing information, E009/E010 correction linking, E011 escalation, approval gating, retry/idempotency action recovery, and ingress rejection. A CLI command imports and processes the complete data pack for recording the requested demo.

## Known limitations

The proposal adapter is a transparent local heuristic, not an evaluated production LLM. CRM matching is explainable but not probabilistically calibrated. The local server's API key is a demonstration ingress boundary, not production authentication. Retention cleanup is local and does not implement legal hold or deletion verification across external systems.
