# BEDA Enquiry Studio — Setup & User Guide

This guide is for someone reviewing the internship demonstration. You do not need to understand programming or JSON to inspect the results. Initial setup uses a terminal: an application where you paste and run commands.

## Model outage verification

Use a separate database filename to preserve your existing demonstration. In `.env`, set `BEDA_MODEL_OFFLINE=1`, then start:

```sh
uv run --env-file .env python main.py serve --db beda-outage-demo.db --port 8020
```

Open `http://127.0.0.1:8020`. This switch deliberately prevents Gemini requests; no valid API key is needed for the outage test.

1. Submit an enquiry. It is saved first, then appears as **NEEDS HUMAN REVIEW** when model interpretation is unavailable.
2. Submit another fictional enquiry using a different ID. Intake still works; it goes directly to human review without more model calls. Resubmitting identical input with the same ID does not create duplicate work; conflicting content is rejected.
3. Open **Human review**, then **Alert human / retry**. Inspect the original source through the Input node. You can record a meaningful manual review note without using the model. This does not send a reply or update CRM.
4. For an item not manually closed, stop the server with Ctrl+C. Set `BEDA_MODEL_OFFLINE=0`, configure a working Gemini key, and restart with the **same database**. Saved items and the outage pause remain.
5. Select **Retry saved work**. This is a deliberate recovery probe, not a new enquiry. On success, inspect the new run version and approve only if appropriate. If the provider is still unavailable, it returns to human review. Other diverted items are not automatically replayed.

Transient provider failures already receive at most three attempts per model operation, with 2- and 4-second backoff and a 35-second timeout per request. Authentication failures stop immediately. After those attempts are exhausted, the saved queue prevents an endless retry loop. Changing environment settings requires a server restart.

Developer checks (temporary databases, fake model responses, no paid API calls):

```sh
uv run python -m unittest discover -s tests -q
node --test tests/*.test.cjs
```

Keep database files private: they contain source messages, queue snapshots and audit history. This is not a multi-worker service or a production authentication system.

The app accepts the supplied enquiries or a fictional message you enter, uses Gemini to analyse it, and lets you inspect the recommendation, supporting information and response draft. The workflow diagram shows the steps that actually ran.

> This is a local assessment prototype, not a connected email or CRM service. Use fictional data only. Gemini receives the information needed for model processing. No customer messages are sent, and external CRM records are not changed. Junk is recoverable, never permanently deleted by this app.

## 1. First-time setup

### What you need

- The complete project folder, extracted from the supplied ZIP or downloaded from the project repository.
- A desktop browser and an internet connection for installation and Gemini requests.
- `uv`, the tool used to install and run the project.
- Your own Gemini API key with access to the configured model.

The project requires **Python 3.14 or newer** and requests 3.14 through `.python-version`. You do not need Node.js, React, Docker or a separate database server to run the app. Node.js is only needed for optional JavaScript developer tests.

### A. Install uv

If `uv --version` already works in your terminal, skip this step.

On **Windows**, open PowerShell and run:

```powershell
winget install --id=astral-sh.uv -e
```

On **macOS**, if you already use Homebrew:

```sh
brew install uv
```

For **Linux**, or if those package managers are unavailable, follow the installer for your operating system in the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/). Only install from a source you trust. Close and reopen the terminal after installation, then run:

```sh
uv --version
```

### B. Open the project folder in a terminal

Open the folder containing `main.py`, `pyproject.toml`, `uv.lock` and `data`. If using an editor, open that folder and use its integrated terminal.

Alternatively, type `cd ` followed by the location of your extracted project folder. This example works when the folder is in your terminal's current directory:

```sh
cd beda-ai-enquiry-system
```

Run all remaining commands from this project folder. Do not run them from inside `data` or `.venv`.

### C. Install Python and the project dependencies

Run these commands one at a time:

```sh
uv python install 3.14
uv sync --locked
```

This creates a project-specific `.venv` environment. You do not need to activate it manually. `--locked` uses the dependency versions recorded with the submission; do not upgrade packages just to run the demo.

### D. Configure your Gemini key

1. Open [Google AI Studio](https://aistudio.google.com/) and sign in with your own account.
2. Open its API Keys page and create a key for a project you are allowed to use. Current Google guidance says new AI Studio keys are **auth keys**, with migration required for older Standard keys. See [Google's API key instructions](https://ai.google.dev/gemini-api/docs/api-key) if an old key fails.
3. In the project folder, make a copy of `.env.example` and name the copy **`.env`**. Do not replace an existing `.env`; edit it instead. Use a plain-text editor and ensure the filename is not `.env.txt`.
4. Edit the copy so it contains these two lines, replacing the placeholder with your own key:

```dotenv
GEMINI_API_KEY=replace_with_your_own_key
GEMINI_MODEL=gemini-2.5-flash
```

The model above is the application's configured default, not a guarantee of future availability. Your key must have access to it. This application reads **`GEMINI_API_KEY`**, not `GOOGLE_API_KEY`.

Keep the key only in your local `.env` or server environment. Do not paste it into Custom Enquiry, screenshots, source files or your assessment submission. The repository ignores `.env`, but creating a ZIP manually can still include it.

Free-tier eligibility and limits depend on the model, account and project. Check [Google's current pricing](https://ai.google.dev/gemini-api/docs/pricing) and your project quota before running. This app does not enforce a spending limit or guarantee free usage.

### E. Start the app

```sh
uv run --env-file .env python main.py serve --port 8000
```

Leave the terminal open. It should print a line beginning with:

```text
Workflow workspace: http://127.0.0.1:8000
```

Open [BEDA Enquiry Studio](http://127.0.0.1:8000) in your browser. Use **127.0.0.1**, not `localhost`: browser write permissions are checked against the exact local address.

The page should show the sample enquiries and a model indicator. **Key configured** means a key was loaded; it does not prove Google accepts it. The first successful enquiry run verifies that connection.

To stop the app, return to the terminal and press **Ctrl+C**. To reopen it later, run the same start command from the project folder. Your saved results remain available.

## 2. Your first demonstration

### Understand the screen

| Area | How to use it |
| --- | --- |
| Inbox / Junk, on the left | Choose an enquiry. Junk contains recoverable messages; uncertain junk stays in Inbox for review. |
| Workflow, in the centre | Click a stage to inspect it. Drag to move around; use **Fit workflow** to see the full diagram. |
| Execution activity | Read what happened in order. Click an entry to inspect its stage. |
| Stage inspector, on the right | Read labelled results, reasons, missing information and drafts. Orange highlights help identify fields. |
| Technical details / Prompt preview | Optional. Inspect exact structured data or the prepared model request; these are not hidden model reasoning. |
| Run history | Compare earlier read-only versions with the latest result. |

### A. Process a normal enquiry

1. Select **E001 — Solar and battery across our three Victorian sites**.
2. Click **Run enquiry**. If it has already been processed, click **New full run** to use the latest code and prompts.
3. Watch the activity feed. Model requests can take some time; do not repeatedly click while a run is in progress.
4. Inspect **Classify + extract**, the CRM matches and the recommendation.
5. Open **Alert + human approval**. Read the draft before choosing **Approve local action** or **Reject**.

Ordinary approval records a local review result. It does not actually email the customer, update CRM contacts or alert an external staff account. The assigned reviewer and pending state are visible inside this app.

### B. Demonstrate missing information

Run **E005 — Government school lighting upgrade**. Inspect the missing information and any clarification draft. The intended behaviour is to ask for necessary information instead of inventing it. Model outputs can vary: review the actual evidence and result.

### C. Demonstrate junk and recovery

1. Run **E004 — Buy 50,000 Australian CEO leads today**.
2. If Gemini identifies it as junk and the local safeguards pass, it moves to **Junk**. The canvas takes the Junk branch, without researching, asking for sales details or drafting a reply.
3. Open the **Junk** folder and inspect the classification reason and recorded outcome.
4. Click **Not junk / Restore to Inbox** to demonstrate recovery. The message returns for review in a new version; the older run remains in history.

If the classification is uncertain, evidence is unsupported, a CRM candidate matches, or a reviewer previously restored it, it stays in Inbox for review. For pending junk reviews, **Move to Junk** performs a recoverable local move; **Reject** keeps it in Inbox. Restoring prevents later automatic quarantine of that enquiry, although a reviewer can explicitly approve a move later.

A junk decision is not guaranteed for every model run. Inspect the result rather than assuming the demonstration passed. If E004 displays an old sales response, use **New full run**, not **View saved run**.

### D. Try your own fictional message

Click **＋ Custom enquiry**. You can enter:

| Field | Example |
| --- | --- |
| Message reference | `DEMO-001` |
| Sender name and email | `Alex Morgan <alex@example.com>` |
| Subject | `Solar enquiry for our warehouse` |
| Customer message | `Hi BEDA, our Melbourne warehouse has rising electricity costs. Could you assess rooftop solar and tell us what site information you need? Thanks, Alex.` |

Click **Analyse enquiry**. Use a new reference for each new example, such as `DEMO-002`. Reusing a successfully processed reference opens its saved result rather than creating another enquiry. Random words test unclear intent, not necessarily junk.

## 3. Inspect and update the three documents

Open **Documents · 3** in the header:

- Hume energy bill — linked to E001.
- Northbank site notes — linked to E005.
- Greenfields invoice query — linked to E003.

Choose a document, click **Edit working copy**, make a fictional change, add a change note and choose **Save new revision**. Open its linked enquiry and select **New full run** to analyse the updated document.

Edits are saved in the local database, not the original text file. Old document revisions and enquiry runs remain available. **Regenerate draft** uses the existing run's evidence; it does not pick up document edits.

## 4. Saved results, reruns and safety

- **View saved run:** inspect an existing result; no new model request.
- **New full run:** repeat analysis and applicable research/drafting in a new version. Earlier pending approvals are replaced; completed decisions remain in history.
- **Regenerate draft:** generate a new draft using existing validated information. It requires a new review and is unavailable for junk.
- **Research:** searches approved local documents and the relevant attachment. It does not browse the web or guarantee engineering compliance.

By default, results, approvals, audit records and edited document copies are stored in **`beda-live.db`** in the project folder. SQLite is built into Python; there is no separate database service to install. Original CSV and document files are unchanged by the live workspace.

The model interprets the message; application rules validate evidence, match records, route work and enforce approval. Some labels and routing rules are intentionally fixed code. The older **`main.py demo`** command uses a heuristic simulation and is **not** the real-Gemini demonstration described here.

The server is intended for one reviewer on their own computer. Do not expose it publicly or load sensitive customer information: saved prompts, drafts and history can contain the supplied content, and complete privacy erasure is not implemented.

## 5. Start a clean demonstration

You do not need to delete your database. Stop the server with **Ctrl+C**, then choose a database filename that does not already exist:

```sh
uv run --env-file .env python main.py serve --port 8000 --db reviewer-session-01.db
```

Refresh the browser. The new session has the original fixtures and documents, with no saved enquiry runs or edits. Use another new name for another fresh session. An existing filename reopens its existing data; it does not clear it.

To continue this session later, use the same `--db reviewer-session-01.db` option. To return to the default saved data, stop the server and restart without `--db`.

For a backup, stop the server before copying the database file. Do not delete or move database files while the app is running.

## 6. Troubleshooting

| What you see | What to do |
| --- | --- |
| `uv` is not recognised / command not found | Install uv, close and reopen the terminal, then try `uv --version`. |
| `main.py` or `pyproject.toml` cannot be found | Open the terminal in the extracted project folder. |
| Missing Python or unsupported Python version | Run `uv python install 3.14`, then `uv sync --locked`. This project currently requires Python 3.14+. |
| `.env` not found | Create it from `.env.example` alongside `main.py`. Check that it is not named `.env.txt`. |
| The page says **API key needed** | Add `GEMINI_API_KEY` to `.env`. Stop the server and restart with `--env-file .env`. |
| **Key configured**, but the model request fails | The indicator only confirms a value was loaded. Inspect the failure event for the HTTP status, then check your key, project permissions and quota. |
| Gemini HTTP 400, 401 or 403 | Check the key and its model/API access in AI Studio. For older Standard or blocked keys, follow Google's linked auth-key migration guidance. Restart after updating `.env`; do not remove security restrictions indiscriminately. |
| Gemini HTTP 404 | Check whether `GEMINI_MODEL` names a model available to your project and compatible with structured output. Restart after changing it. |
| Gemini HTTP 429 | Your project may have reached a rate or quota limit. Check AI Studio, wait as appropriate, then retry. Repeated clicking will not increase quota. |
| Timeout, HTTP 5xx or invalid model output | The app retries eligible failures up to three attempts. If it still fails, inspect the audit and retry later. No canned answer replaces a failed request. |
| Port 8000 is already in use | Stop your previous server, or start with `--port 8001` and open `http://127.0.0.1:8001`. Keep your existing `--db` option if applicable. |
| Browser says to use the local workspace | Open the exact `http://127.0.0.1:<port>` address printed by the server, not `localhost` or a remote address. |
| Results look unchanged after editing a document or updating code | Restart the server after code changes, refresh the page, then choose **New full run**. Old results are intentionally preserved. |
| Approve / Restore reports an old version | Select **Latest** in Run history, refresh, and review the current result. Historical versions cannot be acted on. |
| An enquiry is missing from Inbox | Check **Junk**. If misclassified, use **Not junk / Restore to Inbox**. |
| Another action is running | Retry shortly with the same message reference. Intake and review writes are briefly serialized; model processing runs separately. |

If asking for help, share the enquiry reference, stage and error text—not your API key or `.env` contents.

## 7. Sharing the assessment

Include the project source, `data/`, locally bundled `beda/static/` assets, `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, this guide and the README. Do not include your `.env`, `.venv`, local database files or caches. Git ignore rules do not automatically protect files in a manually created ZIP.

Tell the reviewer to open **SETUP.md** first and use their own Gemini key. An example handover message:

> Please follow SETUP.md to start the local demonstration. Try E001 for a normal enquiry, E005 for missing information, and E004 for recoverable junk handling. You can also create a fictional enquiry and edit the three supplied document copies. The app uses real Gemini requests, but does not send customer messages or change an external CRM.

For technical architecture, limitations and optional tests, see [README.md](README.md). For the original reasoning assessment, see [Test 1.md](Test%201.md).
