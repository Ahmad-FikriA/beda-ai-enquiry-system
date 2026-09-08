# Model Outage Fallback Implementation Plan

**Goal:** Address Matt's verification request on top of Test 2 commit `0e269824358b0c13efb804b59832a9bc3d367d86`, without external dispatch or provider substitution.

**Architecture:** A SQLite work queue commits validated input before acknowledging HTTP intake. One local background worker uses the existing interpretation pipeline; a persisted outage flag diverts new/failed work to a human-review queue. Explicit retries reuse the work item and preserve pipeline run versions; no unbounded automatic retry loop.

**Tech stack:** Existing Python 3.14, SQLite, threading, standard-library HTTP server and vanilla JavaScript. No new runtime dependencies.

**Approved design:** This conversation: durable ingestion, deduplication, outage human-review fallback, controlled recovery, regression tests, local commit and reply draft. Do not push or send a reply.

## Implementation checklist

- [x] Add queue regression tests for durable acceptance, outage diversion, duplicate/conflicting delivery, explicit retry, manual review, restart recovery and completed-work reconciliation.
- [x] Implement `beda/work_queue.py` with durable transitions and an `enquiry(eid)` projection for saved but not yet interpreted input. One active item per enquiry; no credentials stored.
- [x] Add forced-offline setting. Also stop on research-model failure before drafting; previously research caught its model error and allowed another call.
- [x] Change intake/rerun to HTTP 202, start one worker, add same-origin retry/review endpoints, and block stale approvals while work is outstanding.
- [x] Add queued-state polling, Human review filter, retry/manual-review controls and saved draft notes during refresh. Preserve the existing interface style.
- [x] Verify 66 Python and 11 JavaScript tests; actual offline Chrome walkthrough used a temporary database and no Gemini requests.
- [x] Document baseline, outage command, recovery and limits. Handoff is a local-only commit on `codex/model-outage-fallback`; no push or email.

Independent review found and prompted regression fixes for a crash immediately after creating a run version, and changed legacy sender/attachment data. Recovery now requires completion evidence tied to the exact attempt; legacy duplicate checks compare the preserved source fields.

## Acceptance invariants

- Intake commits raw payload and queue/audit records before acknowledging acceptance; unavailable inference cannot block a second intake.
- Same source and content is idempotent; different content under the same ID is rejected, never silently discarded. Rerun request IDs are scoped and validated.
- Queued/running/failed work has no permission to execute consequential actions. Unavailable inference is visibly unclassified and human-owned.
- Outage status survives restart. Worker interruption is escalated for explicit review/retry, not silently replayed; already completed pipeline work is reconciled without duplicate actions.
- Manual review and retry are mutually exclusive transitions. Retry may repeat a provider call after interruption but must not duplicate the intake or local action.
