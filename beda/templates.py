import html
import json
from typing import List, Optional

from beda.models import Action, AuditEvent, Enquiry


def base_layout(title: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)} - BEDA Enquiry System</title>
    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-hover: #334155;
            --border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #38bdf8;
            --primary-hover: #0284c7;
            --success: #4ade80;
            --warning: #facc15;
            --danger: #f87171;
            --tag-bg: #1e1b4b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            line-height: 1.5;
            padding: 24px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        h1 {{ font-size: 24px; font-weight: 700; color: var(--primary); }}
        h2 {{ font-size: 18px; font-weight: 600; margin-bottom: 12px; color: #e2e8f0; }}
        a {{ color: var(--primary); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .btn {{
            display: inline-block;
            background-color: var(--primary);
            color: #0f172a;
            padding: 8px 16px;
            font-weight: 600;
            border-radius: 6px;
            border: none;
            cursor: pointer;
            text-decoration: none;
        }}
        .btn:hover {{ background-color: var(--primary-hover); text-decoration: none; }}
        .btn-success {{ background-color: var(--success); color: #0f172a; }}
        .btn-success:hover {{ background-color: #22c55e; }}
        .card {{
            background-color: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }}
        th, td {{
            padding: 12px;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            background-color: rgba(0,0,0,0.2);
            color: var(--text-muted);
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        tr:hover td {{ background-color: rgba(255,255,255,0.02); }}
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge-pending {{ background-color: #854d0e; color: #fef08a; }}
        .badge-success {{ background-color: #14532d; color: #bbf7d0; }}
        .badge-warning {{ background-color: #713f12; color: #fef08a; }}
        .badge-danger {{ background-color: #7f1d1d; color: #fecaca; }}
        .badge-info {{ background-color: #1e3a8a; color: #bfdbfe; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        @media (max-width: 768px) {{ .grid {{ grid-template-columns: 1fr; }} }}
        pre {{
            background-color: #090d16;
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 12px;
            overflow-x: auto;
            font-size: 13px;
            color: #cbd5e1;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .field-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; }}
        .field-val {{ margin-bottom: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>⚡ BEDA Controlled Enquiry Pipeline</h1>
            <div>
                <a href="/" class="btn">All Enquiries</a>
            </div>
        </header>
        <main>
            {body_html}
        </main>
    </div>
</body>
</html>"""


def render_index(enquiries: List[Enquiry]) -> str:
    rows = []
    for eq in enquiries:
        status_class = "badge-info"
        if eq.status == "PENDING_APPROVAL":
            status_class = "badge-pending"
        elif eq.status in ("COMPLETED", "SUCCEEDED"):
            status_class = "badge-success"

        owner = eq.recommendation.owner if eq.recommendation else "Unassigned"
        category = eq.proposal.category if eq.proposal else "Unknown"
        confidence = eq.proposal.confidence if eq.proposal else "-"

        rows.append(f"""
        <tr>
            <td><strong><a href="/enquiries/{html.escape(eq.id)}">{html.escape(eq.id)}</a></strong></td>
            <td>{html.escape(eq.sender or '')}</td>
            <td>{html.escape(eq.subject or '')}</td>
            <td><span class="badge badge-info">{html.escape(category)}</span></td>
            <td>{html.escape(owner)}</td>
            <td>{html.escape(confidence)}</td>
            <td><span class="badge {status_class}">{html.escape(eq.status)}</span></td>
            <td><a href="/enquiries/{html.escape(eq.id)}">Inspect &rarr;</a></td>
        </tr>
        """)

    table_body = "".join(rows) if rows else "<tr><td colspan='8' style='text-align:center;'>No enquiries processed yet.</td></tr>"

    content = f"""
    <div class="card">
        <h2>Inbound Enquiries ({len(enquiries)})</h2>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>From</th>
                    <th>Subject</th>
                    <th>Category</th>
                    <th>Assigned Owner</th>
                    <th>Confidence</th>
                    <th>Status</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
                {table_body}
            </tbody>
        </table>
    </div>
    """
    return base_layout("Enquiries List", content)


def render_detail(enquiry: Enquiry, actions: List[Action], audit_events: List[AuditEvent]) -> str:
    # 1. Status badge
    status_class = "badge-info"
    if enquiry.status == "PENDING_APPROVAL":
        status_class = "badge-pending"
    elif enquiry.status in ("COMPLETED", "SUCCEEDED"):
        status_class = "badge-success"

    # 2. CRM Candidates Table
    crm_rows = []
    for c in enquiry.match_candidates:
        ambiguous_badge = '<span class="badge badge-warning">AMBIGUOUS</span>' if c.ambiguous else '<span class="badge badge-success">CLEAR</span>'
        reasons = "<br>".join(html.escape(r) for r in c.match_reasons)
        crm_rows.append(f"""
        <tr>
            <td><strong>{html.escape(c.crm_id)}</strong></td>
            <td>{html.escape(c.company)}</td>
            <td>{html.escape(c.contact)}</td>
            <td>{c.score:.2f}</td>
            <td>{ambiguous_badge}</td>
            <td><small>{reasons}</small></td>
        </tr>
        """)
    crm_table = "".join(crm_rows) if crm_rows else "<tr><td colspan='6'>No CRM records matched.</td></tr>"

    # 3. Actions & Approvals
    action_html = []
    primary_action = actions[0] if actions else None
    if primary_action:
        act_status_class = "badge-pending" if primary_action.status == "PENDING_APPROVAL" else ("badge-success" if primary_action.status == "SUCCEEDED" else "badge-danger")
        action_html.append(f"""
        <div class="field-label">Action Type & Status</div>
        <div class="field-val">
            <strong>{html.escape(primary_action.action_type)}</strong> &nbsp;
            <span class="badge {act_status_class}">{html.escape(primary_action.status)}</span>
        </div>
        <div class="field-label">Idempotency Key</div>
        <div class="field-val"><code>{html.escape(primary_action.idempotency_key)}</code></div>
        <div class="field-label">Attempt Count</div>
        <div class="field-val">{primary_action.attempt_count} / {primary_action.max_attempts}</div>
        """)

        if primary_action.last_error:
            action_html.append(f"""
            <div class="field-label" style="color: var(--danger);">Last Error</div>
            <pre style="color: var(--danger);">{html.escape(primary_action.last_error)}</pre>
            """)

        if primary_action.result:
            action_html.append(f"""
            <div class="field-label">Execution Result</div>
            <pre>{html.escape(json.dumps(primary_action.result, indent=2))}</pre>
            """)

        if primary_action.status == "PENDING_APPROVAL":
            action_html.append(f"""
            <form method="POST" action="/enquiries/{html.escape(enquiry.id)}/approve" style="margin-top: 16px;">
                <button type="submit" class="btn btn-success">Approve & Execute Action</button>
            </form>
            """)
    else:
        action_html.append("<div>No actions defined.</div>")

    # 4. Audit Log Table
    audit_rows = []
    for ev in audit_events:
        audit_rows.append(f"""
        <tr>
            <td><small>{html.escape(ev.created_at)}</small></td>
            <td><strong>{html.escape(ev.event_type)}</strong></td>
            <td>{html.escape(ev.actor)}</td>
            <td><pre style="margin:0; padding:4px 8px; font-size:11px;">{html.escape(json.dumps(ev.details))}</pre></td>
        </tr>
        """)
    audit_table = "".join(audit_rows) if audit_rows else "<tr><td colspan='4'>No audit events recorded.</td></tr>"

    # Proposal details
    prop = enquiry.proposal
    missing_fields_str = ", ".join(prop.missing_fields) if prop and prop.missing_fields else "None"
    constraints_str = ", ".join(prop.constraints) if prop and prop.constraints else "None"
    extracted_json = json.dumps(prop.extracted_fields, indent=2) if prop else "{}"

    rec = enquiry.recommendation

    content = f"""
    <div style="margin-bottom: 20px;">
        <h2>Enquiry {html.escape(enquiry.id)}: {html.escape(enquiry.subject or '')}</h2>
        <span class="badge {status_class}">{html.escape(enquiry.status)}</span>
        {f'<span style="margin-left: 10px; color: var(--text-muted); font-size: 13px;">Related to: <a href="/enquiries/{html.escape(enquiry.related_enquiry_id)}">{html.escape(enquiry.related_enquiry_id)}</a></span>' if enquiry.related_enquiry_id else ''}
    </div>

    <div class="grid">
        <!-- Raw Input & Attachment -->
        <div class="card">
            <h2>Raw Input & Attachment</h2>
            <div class="field-label">From</div>
            <div class="field-val">{html.escape(enquiry.sender or '')}</div>
            <div class="field-label">Subject</div>
            <div class="field-val">{html.escape(enquiry.subject or '')}</div>
            <div class="field-label">Message Body</div>
            <pre>{html.escape(enquiry.body or '')}</pre>
            {f'<div class="field-label" style="margin-top:12px;">Attachment ({html.escape(enquiry.attachment_filename or "")})</div><pre>{html.escape(enquiry.attachment_content or "")}</pre>' if enquiry.attachment_content else ''}
        </div>

        <!-- Proposal & Extracted Fields -->
        <div class="card">
            <h2>Structured Proposal & Rationale</h2>
            <div class="field-label">Category & Confidence</div>
            <div class="field-val">
                <span class="badge badge-info">{html.escape(prop.category if prop else "")}</span> &nbsp;
                Confidence: <strong>{html.escape(prop.confidence if prop else "")}</strong>
            </div>
            <div class="field-label">Missing Fields</div>
            <div class="field-val" style="color: {'var(--warning)' if prop and prop.missing_fields else 'var(--text)'};">
                {html.escape(missing_fields_str)}
            </div>
            <div class="field-label">Constraints & Guardrails</div>
            <div class="field-val">{html.escape(constraints_str)}</div>
            <div class="field-label">Rationale</div>
            <div class="field-val">{html.escape(prop.rationale if prop else "")}</div>
            <div class="field-label">Extracted Signals</div>
            <pre>{html.escape(extracted_json)}</pre>
        </div>
    </div>

    <div class="grid">
        <!-- CRM Matches -->
        <div class="card">
            <h2>CRM Match Candidates</h2>
            <table>
                <thead>
                    <tr>
                        <th>CRM ID</th>
                        <th>Company</th>
                        <th>Contact</th>
                        <th>Score</th>
                        <th>Ambiguity</th>
                        <th>Signals</th>
                    </tr>
                </thead>
                <tbody>
                    {crm_table}
                </tbody>
            </table>
        </div>

        <!-- Recommendation & Approval -->
        <div class="card">
            <h2>Recommendation & Action Control</h2>
            <div class="field-label">Recommended Action & Owner</div>
            <div class="field-val">
                <strong>{html.escape(rec.action if rec else '')}</strong> &rarr; {html.escape(rec.owner if rec else '')}
            </div>
            <div class="field-label">Requires Approval</div>
            <div class="field-val">{str(rec.requires_approval if rec else False)}</div>
            <hr style="border: 0; border-top: 1px solid var(--border); margin: 16px 0;">
            {''.join(action_html)}
        </div>
    </div>

    <!-- Draft Response -->
    <div class="card">
        <h2>Generated Response Draft</h2>
        {f'<pre>{html.escape(enquiry.draft_response)}</pre>' if enquiry.draft_response else '<p style="color: var(--text-muted);">No draft response generated (Archived or Escalated directly).</p>'}
    </div>

    <!-- Audit Timeline -->
    <div class="card">
        <h2>Chronological Audit Trail</h2>
        <table>
            <thead>
                <tr>
                    <th>Timestamp (UTC)</th>
                    <th>Event</th>
                    <th>Actor</th>
                    <th>Details</th>
                </tr>
            </thead>
            <tbody>
                {audit_table}
            </tbody>
        </table>
    </div>
    """
    return base_layout(f"Enquiry {enquiry.id}", content)
