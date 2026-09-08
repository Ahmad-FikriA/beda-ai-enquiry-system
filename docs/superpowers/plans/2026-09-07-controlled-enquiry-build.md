# Controlled Enquiry Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Test 1 simulation with a local persistent application that processes the supplied Test 2 data under deterministic controls and exposes its evidence in a simple browser UI.

**Architecture:** A standard-library HTTP server calls a service layer backed by SQLite. A local typed proposal adapter is read-only and isolated from persistence and actions. Storage creates durable enquiries, matches, recommendations, drafts, actions, and append-only audit events; actions run only after explicit approval.

**Tech Stack:** Python 3.14, Pydantic 2, SQLite (`sqlite3`), standard-library HTTP server, unittest.

**Spec:** `docs/superpowers/specs/2026-09-07-controlled-enquiry-build-design.md`

## Global Constraints

- Do not modify `data/*.csv` or attachment fixture files.
- Do not call external services or expose credentials.
- Treat incoming content as untrusted and never grant it permissions.
- Consequential actions require approval and must have a stable idempotency key.
- Tests use the supplied CSV fixtures and isolated temporary SQLite databases.

---

### Task 1: Domain models and persistent storage

**Files:**
- Create: `beda/models.py`
- Create: `beda/storage.py`
- Create: `tests/test_storage.py`

**Interfaces:**
- Produces `Enquiry`, `Proposal`, `MatchCandidate`, `Recommendation`, `Action`, and `AuditEvent` Pydantic models.
- Produces `Database(path: str)` with `initialize()`, `add_audit()`, `get_enquiry()`, and `find_by_source_id()`.

- [x] **Step 1: Write the failing test**

```python
def test_database_persists_enquiry_and_audit(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.create_enquiry(Enquiry(id="E001", source_message_id="E001", subject="Solar"))
    db.add_audit("E001", "RECEIVED", "system", {"source": "fixture"})
    assert db.get_enquiry("E001").subject == "Solar"
    assert db.list_audit("E001")[0].event_type == "RECEIVED"
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_storage -v`

- [x] **Step 3: Write minimal implementation**

Implement SQLite schema creation with foreign-keyed tables and JSON detail columns. Store timestamps in UTC ISO-8601 strings. `add_audit` inserts and commits an immutable event.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_storage -v`

### Task 2: Deterministic normalisation, proposal adapter, and matching

**Files:**
- Create: `beda/reasoning.py`
- Create: `beda/matching.py`
- Create: `tests/test_reasoning.py`
- Create: `tests/test_matching.py`

**Interfaces:**
- Produces `propose(enquiry, attachment_text) -> Proposal`.
- Produces `find_candidates(enquiry, proposal, crm_records, prior_enquiries) -> list[MatchCandidate]`.

- [x] **Step 1: Write failing tests**

```python
def test_e005_keeps_missing_bill_and_fixture_schedule(fixtures):
    proposal = propose(fixtures.enquiry("E005"), fixtures.attachment("E005"))
    assert {"electricity_bill", "fixture_schedule"} <= set(proposal.missing_fields)

def test_e002_returns_ambiguous_hume_candidates(fixtures):
    candidates = find_candidates(fixtures.enquiry("E002"), fixtures.proposal("E002"), fixtures.crm, [])
    assert {"C001", "C002"} <= {candidate.crm_id for candidate in candidates}
    assert any(candidate.ambiguous for candidate in candidates)
```

- [x] **Step 2: Run tests to verify failure**

Run: `uv run python -m unittest tests.test_reasoning tests.test_matching -v`

- [x] **Step 3: Write minimal implementation**

Use carefully bounded keyword and field extraction, attachment facts, and explicit category rules for the supplied cases. Assign uncertainty and explanations. Match exact email/phone first, then normalised company/contact/context. Never emit a definitive match if the leading scores are materially close.

- [x] **Step 4: Run tests to verify passing**

Run: `uv run python -m unittest tests.test_reasoning tests.test_matching -v`

### Task 3: Controlled orchestration, approval, retries, and recovery

**Files:**
- Create: `beda/service.py`
- Create: `beda/actions.py`
- Create: `tests/test_service.py`

**Interfaces:**
- Produces `EnquiryService.process_input(payload) -> Enquiry` and `approve_and_execute(enquiry_id, approver) -> Action`.
- Produces `ActionExecutor.execute(action) -> Action` and `retry_pending() -> list[Action]`.

- [x] **Step 1: Write failing tests**

```python
def test_e010_updates_e009_prospect_without_creating_second_record(service, fixtures):
    service.process_input(fixtures.payload("E009"))
    correction = service.process_input(fixtures.payload("E010"))
    assert correction.related_enquiry_id == "E009"
    assert correction.recommendation.action == "UPDATE_CONTACT_PHONE"

def test_consequential_action_needs_approval_and_is_idempotent(service, fixtures):
    enquiry = service.process_input(fixtures.payload("E001"))
    assert service.actions_for(enquiry.id)[0].status == "PENDING_APPROVAL"
    first = service.approve_and_execute(enquiry.id, "reviewer")
    second = service.approve_and_execute(enquiry.id, "reviewer")
    assert first.idempotency_key == second.idempotency_key
    assert second.attempt_count == 1
```

- [x] **Step 2: Run tests to verify failure**

Run: `uv run python -m unittest tests.test_service -v`

- [x] **Step 3: Write minimal implementation**

Persist `RECEIVED` through `ACTION_SUCCEEDED` events. Create actions before execution. Allow only safe local actions; never send messages. Enforce three retryable attempts, persist `FAILED_RETRYABLE`, and write reconciliation events. Route E011 to Ali, E007 to Zidane, E008 to Ties, and major commercial sales to Matt.

- [x] **Step 4: Run tests to verify passing**

Run: `uv run python -m unittest tests.test_service -v`

### Task 4: Local inspection UI and secured ingestion endpoint

**Files:**
- Create: `beda/web.py`
- Create: `beda/templates.py`
- Create: `tests/test_web.py`
- Modify: `main.py`

**Interfaces:**
- Produces `run_server(database_path, api_key, port)` and `POST /api/enquiries`.
- Produces `GET /`, `GET /enquiries/{id}`, and `POST /enquiries/{id}/approve`.

- [x] **Step 1: Write failing test**

```python
def test_ingestion_rejects_missing_api_key(client, fixtures):
    response = client.post("/api/enquiries", json=fixtures.payload("E001"))
    assert response.status_code == 401
```

- [x] **Step 2: Run test to verify failure**

Run: `uv run python -m unittest tests.test_web -v`

- [x] **Step 3: Write minimal implementation**

Validate JSON object shape and compare an optional configured API key with `hmac.compare_digest`. Render plain, escaped HTML with input, proposal, uncertainty, CRM candidates, recommendation, draft, approval/action status, and audit events.

- [x] **Step 4: Run test to verify passing**

Run: `uv run python -m unittest tests.test_web -v`

### Task 5: Data import, retention cleanup, and Test 2 documentation

**Files:**
- Create: `beda/importer.py`
- Modify: `main.py`
- Modify: `README.md`
- Create: `tests/test_importer.py`

**Interfaces:**
- Produces `import_fixture_pack(service, data_dir) -> list[str]` and `cleanup_raw_content(database, older_than_days) -> int`.
- Provides `python main.py demo`, `python main.py serve`, and `python main.py cleanup` commands.

- [x] **Step 1: Write failing test**

```python
def test_import_processes_all_twelve_fixture_enquiries(service, data_dir):
    ids = import_fixture_pack(service, data_dir)
    assert ids == [f"E{i:03}" for i in range(1, 13)]
```

- [x] **Step 2: Run test to verify failure**

Run: `uv run python -m unittest tests.test_importer -v`

- [x] **Step 3: Write minimal implementation and README**

Load CSV rows and attachments without altering fixtures. Document quick start, architecture, model/tool boundary, API-key ingress boundary, retention policy, known weaknesses, another-day improvements, and a five-case recording script.

- [x] **Step 4: Run full verification**

Run: `uv run python -m unittest discover -v && uv run python main.py demo`

