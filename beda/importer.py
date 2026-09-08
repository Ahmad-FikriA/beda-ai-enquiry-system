import csv
from pathlib import Path
from typing import List, Union

from beda.models import CRMRecord
from beda.service import EnquiryService
from beda.storage import Database


def import_fixture_pack(service: EnquiryService, data_dir: Union[Path, str]) -> List[str]:
    """
    Imports CRM records and processes all fixture enquiries from CSV files
    and attachment documents in order.
    """
    path = Path(data_dir)

    # 1. Import CRM records
    crm_path = path / "crm.csv"
    if crm_path.exists():
        with open(crm_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rec = CRMRecord(**row)
                service.db.upsert_crm_record(rec)

    # 2. Build documents map
    docs_map = {}
    docs_csv = path / "documents.csv"
    if docs_csv.exists():
        with open(docs_csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                docs_map[row["enquiry_id"]] = row["filename"]

    # 3. Import and process enquiries
    enquiries_csv = path / "enquiries.csv"
    if not enquiries_csv.exists():
        raise FileNotFoundError(f"Missing {enquiries_csv}")

    processed_ids = []
    with open(enquiries_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            enquiry_id = row["id"]
            attachment_file = row.get("attachment") or docs_map.get(enquiry_id)
            attachment_text = None

            if attachment_file:
                doc_file = path / "documents" / attachment_file
                if doc_file.exists():
                    attachment_text = doc_file.read_text(encoding="utf-8")

            payload = {
                "id": enquiry_id,
                "from": row.get("from", ""),
                "subject": row.get("subject", ""),
                "body": row.get("body", ""),
                "attachment_filename": attachment_file,
                "attachment_content": attachment_text,
            }

            enquiry = service.process_input(payload)
            processed_ids.append(enquiry.id)

    return processed_ids


def cleanup_raw_content(database: Database, older_than_days: int) -> int:
    """
    Executes retention cleanup on database records older than specified days.
    """
    return database.cleanup_raw_content(older_than_days)
