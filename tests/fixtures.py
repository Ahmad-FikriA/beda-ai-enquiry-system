import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from beda.models import CRMRecord, Enquiry, Proposal

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class FixtureLoader:
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or DATA_DIR
        self._enquiries_cache: Optional[Dict[str, Dict[str, str]]] = None
        self._crm_cache: Optional[List[CRMRecord]] = None
        self._docs_map: Optional[Dict[str, str]] = None

    def _load_enquiries_csv(self) -> Dict[str, Dict[str, str]]:
        if self._enquiries_cache is None:
            self._enquiries_cache = {}
            with open(self.data_dir / "enquiries.csv", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self._enquiries_cache[row["id"]] = row
        return self._enquiries_cache

    def _load_crm(self) -> List[CRMRecord]:
        if self._crm_cache is None:
            self._crm_cache = []
            with open(self.data_dir / "crm.csv", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self._crm_cache.append(CRMRecord(**row))
        return self._crm_cache

    def _load_docs_map(self) -> Dict[str, str]:
        if self._docs_map is None:
            self._docs_map = {}
            docs_csv = self.data_dir / "documents.csv"
            if docs_csv.exists():
                with open(docs_csv, encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self._docs_map[row["enquiry_id"]] = row["filename"]
        return self._docs_map

    @property
    def crm(self) -> List[CRMRecord]:
        return self._load_crm()

    def enquiry_row(self, enquiry_id: str) -> Dict[str, str]:
        rows = self._load_enquiries_csv()
        if enquiry_id not in rows:
            raise KeyError(f"Enquiry {enquiry_id} not found in fixtures")
        return rows[enquiry_id]

    def attachment(self, enquiry_id: str) -> Optional[str]:
        row = self.enquiry_row(enquiry_id)
        filename = row.get("attachment")
        if not filename:
            docs_map = self._load_docs_map()
            filename = docs_map.get(enquiry_id)
        if not filename:
            return None
        doc_path = self.data_dir / "documents" / filename
        if doc_path.exists():
            return doc_path.read_text(encoding="utf-8")
        return None

    def enquiry(self, enquiry_id: str) -> Enquiry:
        row = self.enquiry_row(enquiry_id)
        # Parse sender
        raw_from = row.get("from", "")
        sender_email = None
        sender_name = None
        if "<" in raw_from and ">" in raw_from:
            sender_name = raw_from.split("<")[0].strip()
            sender_email = raw_from.split("<")[1].split(">")[0].strip()
        elif " " in raw_from:
            parts = raw_from.rsplit(" ", 1)
            if "@" in parts[1]:
                sender_name = parts[0].strip()
                sender_email = parts[1].strip()
            else:
                sender_name = raw_from.strip()
        elif "@" in raw_from:
            sender_email = raw_from.strip()
            sender_name = raw_from.split("@")[0].capitalize()

        att_text = self.attachment(enquiry_id)
        att_file = row.get("attachment") or self._load_docs_map().get(enquiry_id)

        return Enquiry(
            id=row["id"],
            source_message_id=row["id"],
            sender=raw_from,
            sender_email=sender_email,
            sender_name=sender_name,
            subject=row.get("subject", ""),
            body=row.get("body", ""),
            attachment_filename=att_file,
            attachment_content=att_text,
            raw_payload={"id": row["id"], "from": raw_from, "subject": row.get("subject", ""), "body": row.get("body", ""), "attachment": att_file},
        )

    def payload(self, enquiry_id: str) -> Dict[str, Any]:
        row = self.enquiry_row(enquiry_id)
        att_file = row.get("attachment") or self._load_docs_map().get(enquiry_id)
        att_text = self.attachment(enquiry_id)
        return {
            "id": row["id"],
            "from": row["from"],
            "subject": row.get("subject", ""),
            "body": row.get("body", ""),
            "attachment_filename": att_file,
            "attachment_content": att_text,
        }

    def proposal(self, enquiry_id: str) -> Proposal:
        # Import dynamically so test failures happen appropriately if reasoning isn't ready
        from beda.reasoning import propose
        return propose(self.enquiry(enquiry_id), self.attachment(enquiry_id))


fixtures = FixtureLoader()
