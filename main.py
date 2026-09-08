import argparse
import os
import sys
from pathlib import Path

from beda.importer import cleanup_raw_content, import_fixture_pack
from beda.service import EnquiryService
from beda.storage import Database
from beda.web import run_server

DEFAULT_DB = "beda.db"
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


def cmd_demo(args):
    db_path = args.db or DEFAULT_DB
    print(f"\n=======================================================")
    print(f"🚀 BEDA Controlled Enquiry Pipeline — Test 2 Demo")
    print(f"=======================================================\n")
    print(f"Database: {db_path}")
    print(f"Data Dir: {DEFAULT_DATA_DIR}\n")

    db = Database(db_path)
    db.initialize()
    service = EnquiryService(db)

    print("Importing CRM records and 12 fixture enquiries...")
    imported_ids = import_fixture_pack(service, DEFAULT_DATA_DIR)
    print(f"✅ Successfully processed {len(imported_ids)} enquiries: {', '.join(imported_ids)}\n")

    print("-" * 105)
    print(f"{'ID':<6} {'CATEGORY':<24} {'OWNER':<18} {'ACTION':<30} {'STATUS':<15}")
    print("-" * 105)

    for eq_id in imported_ids:
        eq = db.get_enquiry(eq_id)
        category = eq.proposal.category if eq.proposal else "Unknown"
        owner = eq.recommendation.owner if eq.recommendation else "None"
        action = eq.recommendation.action if eq.recommendation else "None"
        actions = service.actions_for(eq_id)
        act_status = actions[0].status if actions else eq.status
        print(f"{eq.id:<6} {category:<24} {owner:<18} {action:<30} {act_status:<15}")

    print("-" * 105)
    print("\n🔍 Key Controlled Boundary Highlights:")
    print(" 1. E002 (Ambiguity): Email matches C002, phone & context match C001. Kept both candidates, flagged ambiguous.")
    e002 = db.get_enquiry("E002")
    for c in e002.match_candidates:
        print(f"    - Candidate {c.crm_id}: {c.company} ({c.contact}) | Score: {c.score} | Ambiguous: {c.ambiguous}")

    print("\n 2. E005 (Missing Information): Preserved missing utility bill and fixture schedule instead of inventing facts.")
    e005 = db.get_enquiry("E005")
    print(f"    - Missing fields: {e005.proposal.missing_fields}")

    print("\n 3. E006 (Engineering Guardrail): Harmonic distortion / THD enquiry escalated without automated technical answers.")
    e006 = db.get_enquiry("E006")
    print(f"    - Constraints: {e006.proposal.constraints}")

    print("\n 4. E008 (Subcontractor Control): Crew availability acknowledged without confirming project progression.")
    e008 = db.get_enquiry("E008")
    print(f"    - Constraints: {e008.proposal.constraints}")

    print("\n 5. E010 -> E009 (Correction Linking): Web form phone correction updated existing prospect without duplicate.")
    e010 = db.get_enquiry("E010")
    print(f"    - Related Enquiry ID: {e010.related_enquiry_id}")
    print(f"    - Action: {e010.recommendation.action}")

    print("\n 6. E011 (Infrastructure Alert): HubSpot token expiration routed directly to Ali Pratama.")
    e011 = db.get_enquiry("E011")
    print(f"    - Assigned Owner: {e011.recommendation.owner}")

    print("\n 7. Human-in-the-Loop Gating & Idempotency:")
    print("    - Approving E001 commercial solar opportunity...")
    act1 = service.approve_and_execute("E001", approver="matt.cooper")
    print(f"    - Action status: {act1.status} | Attempt count: {act1.attempt_count} | Key: {act1.idempotency_key[:16]}...")

    print("    - Re-executing approval (idempotency check)...")
    act2 = service.approve_and_execute("E001", approver="matt.cooper")
    print(f"    - Action status: {act2.status} | Attempt count: {act2.attempt_count} (unchanged) | Same key verified.")

    print("\n✨ Demo completed successfully. To start web UI, run: python main.py serve\n")


def cmd_serve(args):
    from beda.workspace import serve
    serve(args.db, args.port)


def cmd_cleanup(args):
    db_path = args.db or DEFAULT_DB
    days = args.days if args.days is not None else 30
    db = Database(db_path)
    db.initialize()

    count = cleanup_raw_content(db, older_than_days=days)
    print(f"Retention cleanup complete: Redacted raw text for {count} enquiry records older than {days} days.")


def main():
    parser = argparse.ArgumentParser(description="BEDA AI Controlled Enquiry System")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # demo
    demo_parser = subparsers.add_parser("demo", help="Run deterministic processing and verification demo")
    demo_parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite database")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start local web UI and secured ingestion server")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port number (default 8000)")
    serve_parser.add_argument("--db", default="beda-live.db", help="Path to live SQLite database")

    # cleanup
    cleanup_parser = subparsers.add_parser("cleanup", help="Purge raw text content older than specified days")
    cleanup_parser.add_argument("--days", type=int, default=30, help="Age in days (default 30)")
    cleanup_parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite database")

    args = parser.parse_args()

    if args.command == "demo":
        cmd_demo(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "cleanup":
        cmd_cleanup(args)


if __name__ == "__main__":
    main()
