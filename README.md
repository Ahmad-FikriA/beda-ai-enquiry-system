# BEDA Enquiry Studio — Test 2

A local workflow canvas following the Test 1 architecture. **Gemini proposes. Deterministic code validates and routes. Humans approve consequential actions; eligible junk can be set aside locally and restored.** All supplied data is synthetic.

## Start here — for reviewers

Follow the [Setup & User Guide](SETUP.md) for first-time installation, Gemini key setup, a demonstration walkthrough, troubleshooting and starting a clean session. No knowledge of JSON is needed to use the interface.

This prototype processes the supplied examples and messages you enter manually. It does **not** connect to a real mailbox, website form, messaging account or external CRM. The guide explains exactly which actions are real and which are local demonstrations.

- [First-time setup](SETUP.md#1-first-time-setup)
- [Try the demonstration](SETUP.md#2-your-first-demonstration)
- [Start a clean session](SETUP.md#5-start-a-clean-demonstration)
- [Troubleshooting](SETUP.md#6-troubleshooting)
- [Test 1 proposal](Test%201.md)

## Start the live workspace

After installing `uv` and creating your own `.env` from `.env.example` as explained in the [setup guide](SETUP.md):

```sh
uv sync --locked
uv run --env-file .env python main.py serve --port 8000
```

Open **http://127.0.0.1:8000**. Put `GEMINI_API_KEY` in your local `.env` before starting; restart after changing it. `.env.example` lists the variable names. The command above explicitly loads `.env`; if you export environment variables directly, omit `--env-file .env`. Use a Gemini Developer API project with an eligible free tier and check its current quota in AI Studio. This application cannot guarantee free usage or infer whether billing is enabled on your project.

Select an enquiry and click **Run enquiry**. Two real model calls normally run: structured extraction, then drafting from validated facts. Junk and infrastructure cases skip the customer draft. Junk is handled before checking missing sales information. The application does not silently fall back to heuristic answers when an API call fails.

The default database is `beda-live.db`. The older `beda.db` and `main.py demo` belong to the legacy heuristic simulation. They are retained for comparison and must not be presented as evidence of live model execution. Test 1 documentation is in [Test 1.md](Test%201.md).

## UI and architecture

The wider stage inspector presents results as labelled cards with orange accents. Raw JSON is collapsed under **Technical details** and colour-highlighted when opened; source values remain available unchanged. **Custom enquiry** includes fictional examples, required-field labels and plain-language guidance. Use a new message reference for each new test. These presentation changes do not alter processing or approval rules.

The locally bundled Cytoscape.js 3.30.4 canvas supports pan, zoom, node dragging, fitting the graph, and stage selection. The inspector also has a keyboard-accessible stage selector. A live activity feed polls committed audit events every 650 ms during processing. Click any log entry to inspect its stage; disable **Follow latest** to read older entries. Active model stages pulse (unless reduced motion is enabled), completed nodes highlight, and amber marks pending approval. Fast code stages can arrive together; the UI does not insert fake processing delays or automatically approve actions.

Gemini stages include a collapsible **Prompt preview** with the exact prepared system instruction, input, JSON schema and model settings. The preview appears when a stage starts, including before a missing-key failure. It is a request preview, not hidden model reasoning or proof that a request succeeded. Credentials and transport headers are excluded. Prompts contain source data and are persisted in the local audit; the legacy retention cleanup does not redact these new prompt records.

1. Ingest a supplied CSV row or custom synthetic enquiry; check shape, size and source ID.
2. Normalize text and prevent repeated processing of a completed source ID.
3. Call Gemini for classification, facts with evidence, missing fields, constraints and research needs.
4. Validate JSON with Pydantic. Discard a fact unless its evidence occurs in the supplied source and its value occurs in that evidence. Unsupported facts lower confidence and request review.
5. Deterministically score CRM candidates using contact signals and preserve ambiguity.
6. Route by category using a fixed owner mapping in `beda/live.py`. Changes to `staff.csv` do not currently update that mapping automatically. The model cannot select executable tools or grant approval.
7. Handle junk first: eligible messages move to recoverable local Junk; uncertain cases request human review without drafting or research. For other enquiries, check missing information. Missing inputs lead directly to clarification. Otherwise, if research is needed, Gemini plans up to three queries, deterministic code retrieves at most five excerpts from approved local documents and the enquiry attachment, and Gemini selects evidence and unresolved questions. Source IDs and exact quotations are validated before evidence reaches drafting. No matching sources, invalid citations, or research failure result in explicit uncertainty and human escalation.
8. Generate a clarification or response draft from validated facts. Junk and infrastructure inputs have no customer draft.
9. Present consequential-action recommendations and drafts for approval or rejection. Eligible recoverable Junk moves have a separate, limited automatic policy.
10. Atomically record the decision, local action result and audit events in SQLite.

The source diagram is [diagram_enquiry.png](diagram_enquiry.png). The research branch now executes before the response draft: **Need research → Research agent + approved sources → Citation validation → Draft → Human approval**. Engineering sign-off remains human even when research succeeds. Additional routing categories cover recruitment, operations, infrastructure and contact corrections.

## Document library

Open **Documents · 3** in the workspace header (or `/documents`) to inspect the Hume energy bill, Northbank site notes and Greenfields invoice query as readable documents, not JSON. Each document links to its enquiry.

Use **Edit working copy**, enter a change note, and **Save new revision**. Edits are stored in the `document_revisions` SQLite table; the supplied text files and CSV data are unchanged. Revision history preserves previous content and change notes. Concurrent edits with an outdated revision are rejected.

A **New full run** uses the latest working copy and records its filename, revision and hash in the audit. **Regenerate draft** keeps the existing run's source evidence. Editing a document alone does not rewrite old run snapshots or decisions; start a full run to reassess the updated evidence and request fresh approval. Document revisions contain source data and are not covered by the legacy retention cleanup.

## Recoverable Junk demonstration

Use **E004 → New full run** if it already has a saved result. Old runs are not rewritten by prompt updates. Classification is from BEDA's perspective: a customer seeking energy services is a sales enquiry; an unrelated incoming advertisement is not a BEDA sales opportunity. Relevant suppliers and unclear messages should not automatically become junk. Drafts explicitly reply on behalf of BEDA, not the incoming sender.

- **Automatic local quarantine:** requires a `junk` classification, HIGH validated confidence, at least one supported fact with no rejected facts, no CRM candidate match, and no earlier reviewer restoration. These checks are conservative safeguards, not calibrated proof that the message is spam.
- **Uncertain junk:** stays in Inbox for human review. **Move to Junk** approves a recoverable move; **Reject** leaves it in Inbox. Neither path asks the sender for sales details or generates a response.
- **Junk folder:** shows quarantined messages, their original input, the classification reason, policy checks and audit. The canvas follows the actual Junk branch and skips information checking, research and drafting.
- **Not junk / Restore to Inbox:** creates a new review version without a model call, keeps the previous run snapshot and original AI classification, and prevents later automatic quarantine for that enquiry. Start a new full run to reassess the content. A human may still explicitly move it to Junk later.
- Quarantine and restore commit the local status, action, audit and snapshot changes together. Stale restore/review requests are rejected. Duplicate source IDs reuse their saved outcome.

There is **no permanent deletion**, mailbox deletion, external message sending or CRM mutation in this feature. Junk is a recoverable status on the SQLite enquiry, not a destructive file operation. Original supplied files and CSVs remain unchanged. This policy is not a claim that model confidence is sufficient for deleting real business email.

## Versioned reruns and research

- **New full run** repeats classification, matching, research (when needed), and drafting for the same enquiry. It creates v2, v3, and so on; it does not create another contact or enquiry.
- **Regenerate draft** reuses the validated proposal and saved research, calls Gemini only for a fresh draft, and requests new approval. It does not refresh source documents; choose a full run for that.
- **Run history** opens read-only snapshots with that version's prompt previews, events and actions. Pending approvals from older versions become `SUPERSEDED`. Completed decisions remain in history. The review endpoint rejects stale version numbers.
- Failed model retries also create a new version. Repeated requests with the same rerun request ID are idempotent. The UI generates a new request ID for each deliberate rerun.
- The `runs` SQLite table stores immutable historical snapshots alongside the current enquiry projection. Existing legacy records are archived as v1 on their first rerun.

The approved local research corpus is `data/knowledge/*.txt`. Add only reviewed source documents there. Search is read-only, skips symlinks, caps documents at 20 and 40 KB each, and returns up to five 3 KB excerpts. The agent has no arbitrary filesystem access, shell tool, web browser, CRM write tool or message-sending tool. Each research pass has up to two model calls (query planning and evidence selection), each using the existing bounded retry policy. Retrieved excerpts, source hashes, accepted/rejected citations, unresolved questions and prompts appear in the research node and audit.

The bundled review policy is explicitly synthetic process guidance. It supplies no numeric engineering limits or government eligibility rules. It demonstrates actual retrieval and model-based evidence selection; it cannot establish real technical compliance. No live web research is performed. Prompt previews and run snapshots contain synthetic source data and are not covered by the legacy raw-content cleanup.

| File | Responsibility |
| --- | --- |
| `beda/workspace.py` | Local HTTP workspace and fixture ingestion |
| `beda/static/` | Canvas, inspector, local library and styling |
| `beda/llm.py` | Gemini transport, typed schemas, bounded retries |
| `beda/live.py` | Validation, routing, approval and audit orchestration |
| `beda/research.py` | Bounded local research and citation validation |
| `beda/runs.py` | Version creation and historical snapshots |
| `beda/documents.py` | Supplied attachment library and versioned working copies |
| `beda/junk.py` | Atomic recoverable quarantine and reviewer restoration |
| `beda/matching.py` | Explainable CRM candidate scoring |
| `beda/storage.py` | SQLite records |

## Permissions, reliability and cost

The server binds to loopback. Browser mutations require the local origin and a custom header; cross-origin writes are rejected. This is a local demonstration boundary, not multi-user authentication.

The Gemini credential exists only in the server environment and transport header. Prompts contain no credentials. The model receives no tools. External communication is limited to the configured Gemini model endpoint; the graph library loads locally. Use synthetic data because free-tier provider data-handling terms may differ from paid services.

Gemini HTTP 429, selected 5xx errors, timeouts and invalid structured output retry at most three attempts, with 2- and 4-second delays. Authentication and other non-retryable HTTP errors stop immediately. Failures and attempts are persisted; a model failure creates no executable action and can be retried from the UI. A completed source ID returns the stored run without calling the model again. Audit usage includes the actual model identifier and provider token metadata.

Approval requires a pending action for the current run version. The action key is stable per enquiry, action and run version. The local review decision and its outcome commit in one SQLite transaction; repeated, superseded or rejected reviews cannot execute again.

**Execution scope:** ordinary approval records a local review result; approval of a junk review moves the message into the recoverable local Junk folder. Neither sends email, creates external tickets, modifies CRM contacts, confirms a project, or reconciles invoices. E009/E010 can demonstrate correction linking and a recommendation for human verification, but not an implemented CRM mutation. This limit is shown in the UI and action result.

## Demonstration

1. E001: inspect source attachment, extracted evidence, matching and draft.
2. E002: inspect conflicting CRM candidates and the ambiguity recommendation.
3. E005: inspect missing information and clarification branch.
4. E009 then E010: inspect old/new phone facts, related enquiry and correction recommendation. Identity still requires human verification.
5. E011: inspect Ali's routing and infrastructure escalation without a customer response.
6. Approve or reject one pending action; inspect the persistent audit. Open the saved run again to demonstrate source-ID idempotency.
7. Use **Custom enquiry** with a new ID and changed numbers/names to demonstrate that the live adapter is not keyed to case IDs.

E004 contains an unquoted comma in the supplied CSV subject. The importer combines surplus subject cells, preserves the original cells in an `IMPORT_WARNING`, and leaves the source file unchanged. Review that assumption in the audit.

## Verification

```sh
uv run python -m unittest discover -v
node --test tests/inspector-view.test.cjs
node --test tests/workflow-view.test.cjs
```

Legacy tests exercise the original deterministic adapter. `tests/test_live.py` separately checks grounded fact filtering, source idempotency, approval/rejection, missing-key behavior and durable model failure/retry, using a clearly identified model test double. Passing offline tests does not establish Gemini quality or account/model availability. A live run with your key is required for that evidence.

Optional provider smoke check: `uv run --env-file .env python -m tests.check_live_junk`. It makes real Gemini requests for E004, a new advertising example and a normal solar enquiry, using a temporary database. It consumes provider quota and does not modify the working database. On 8 September 2026, all three checks passed: both advertising inputs were quarantined without drafts, while the solar enquiry produced a BEDA clarification draft. This is a small smoke test, not an accuracy benchmark.

## Known weaknesses and another day

- Real Gemini integration is implemented, but live provider output requires a locally configured API key. Model availability and free quotas may change.
- Evidence substring checks are conservative and are not proof of semantic truth. Drafts remain untrusted and require human review. Confidence labels are not calibrated probabilities.
- Reads run concurrently so the activity feed stays responsive. A process-local lock serializes mutations and rejects overlapping writes with HTTP 409. This is suitable for one local server, not a distributed worker system.
- A crash outside the final approval transaction can leave incomplete processing. Recovery for interrupted non-model stages and distributed side effects is not implemented.
- CRM mutation, external dispatch, manual draft editing, and live web research are not implemented. Draft regeneration and approved local research are implemented.
- Raw-content cleanup from the legacy CLI is partial: extracted facts, drafts and audit details can still contain personal information. It is not complete privacy erasure. Do not claim de-identified audit retention.
- The graph is an execution inspector, not an editable workflow programming engine. Dragging nodes changes only their visual position.

With another day: evaluate live outputs across all twelve cases plus paraphrases; implement approved CRM upserts and correction diffs with transactional recovery; add draft editing; move long calls to a worker; implement complete retention/redaction across snapshots; and expand the approved research corpus with authoritative sources.

## Models and tools

Gemini Developer API for interpretation and drafting; Python/Pydantic/SQLite for controls; Cytoscape.js for the canvas. Codex assisted implementation and testing; the earlier scaffold uses heuristics. No agent framework is required.

References: [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [Cytoscape.js](https://js.cytoscape.org/). The bundled Cytoscape license is in `beda/static/vendor/`.
