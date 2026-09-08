"""Local workflow workspace, with same-origin review controls."""
import csv
import json
import mimetypes
import os
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import Lock
from urllib.parse import urlparse, parse_qs
from beda.storage import Database
from beda.models import CRMRecord
from beda.live import LiveService
from beda.work_queue import WorkQueue

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "beda" / "static"


def fixtures():
    with (ROOT / "data/enquiries.csv").open() as file:
        reader = csv.reader(file)
        header = next(reader)
        records = []
        for cells in reader:
            warning = None
            if len(cells) > len(header):
                # This pack has an unquoted comma in a subject. Preserve the source
                # cells and expose the import assumption; never edit the fixture.
                warning = {"reason": "Extra CSV cells interpreted as subject commas", "source_cells": cells}
                cells = cells[:2] + [",".join(cells[2:-2])] + cells[-2:]
            if len(cells) != len(header):
                raise ValueError("Malformed fixture row: expected five columns")
            row = dict(zip(header, cells))
            if warning:
                row["import_warning"] = warning
            records.append(row)
        return records


class Handler(BaseHTTPRequestHandler):
    def respond(self, code, data, content_type="application/json"):
        body = json.dumps(data).encode() if content_type == "application/json" else data
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/workspace":
            ids = dict.fromkeys([e.id for e in self.server.db.list_enquiries()] + [j['enquiry_id'] for j in self.server.queue.items()])
            self.respond(200, {"fixtures": fixtures(), "enquiries": [self.server.queue.enquiry(eid).model_dump() for eid in ids],
                'queue': self.server.queue.health(),
                "model": self.server.service.model.model, "configured": bool(self.server.service.model.key)})
        elif path == '/api/documents':
            self.respond(200,{'documents':self.server.service.documents.list()})
        elif path.startswith("/api/run/"):
            eid = path.removeprefix("/api/run/")
            eq = self.server.queue.enquiry(eid)
            job = self.server.queue.latest(eid)
            current=self.server.service.runs.current(eid)
            try:
                version=int(parse_qs(urlparse(self.path).query).get('version',[current])[0])
            except ValueError:
                self.respond(400,{'error':'Invalid version'});return
            saved=self.server.service.runs.snapshot(eid,version) if version!=current else (eq.model_dump() if eq else None)
            self.respond(200, {"enquiry": saved, 'version':version,'current_version':current,
                'work_item': {k:v for k,v in job.items() if k!='payload_json'} if job and version==current else None,
                'versions':self.server.service.runs.list(eid),
                "audit": [a.model_dump() for a in self.server.db.list_audit(eid) if
                    (a.details.get('run_version')==(version or 1)) or
                    (version==current and job and a.details.get('queue_job_id')==job['id'])],
                "actions": [a.model_dump() for a in self.server.db.list_actions_for_enquiry(eid) if a.payload.get('run_version',1)==(version or 1)]})
        else:
            file = STATIC / ("index.html" if path == "/" else 'documents.html' if path == '/documents' else path.removeprefix("/static/"))
            if not file.resolve().is_relative_to(STATIC.resolve()) or not file.is_file():
                self.respond(404, {"error": "Not found"})
                return
            self.respond(200, file.read_bytes(), mimetypes.guess_type(str(file))[0] or "application/octet-stream")

    def do_POST(self):
        # Writes remain serial, while GET polling can read committed audit events.
        lock = getattr(self.server, "write_lock", None)
        if lock is not None and not lock.acquire(blocking=False):
            self.respond(409, {"error": "Another action is running. Wait for it to finish."})
            return
        try:
            self.handle_post()
        finally:
            if lock is not None:
                lock.release()

    def handle_post(self):
        # Browser mutations require the actual local origin and a non-simple custom header.
        expected = f"http://127.0.0.1:{self.server.server_port}"
        if self.headers.get("Origin") != expected or self.headers.get("X-BEDA-Workspace") != "1":
            self.respond(403, {"error": "Use the local workflow workspace"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0 or size > 100000:
                raise ValueError("Request exceeds 100 KB")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Expected JSON object")
            if self.path == "/api/process":
                row = next((r for r in fixtures() if r["id"] == payload.get("fixture")), None)
                if row:
                    payload = dict(row)
                    filename = row.get("attachment")
                    if filename:
                        payload=self.server.service.documents.attach(payload)
                self.respond(202, self.server.queue.submit(payload))
            elif self.path == '/api/rerun':
                self.respond(202, self.server.queue.submit({'id':payload['id']},payload['mode'],payload['request_id']))
            elif self.path == '/api/queue/retry':
                self.respond(202, self.server.queue.retry(payload['id']))
            elif self.path == '/api/queue/review':
                self.respond(200, self.server.queue.review(payload['id'],payload['note']))
            elif self.path == '/api/documents/save':
                document=self.server.service.documents.save(payload['filename'],payload['content'],payload['note'],payload['revision'])
                self.respond(200,{'document':document})
            elif self.path == '/api/junk/restore':
                self.check_queue(payload['id'])
                result=self.server.service.restore_junk(payload['id'],payload.get('version'))
                self.respond(200,{'id':result.id,'status':result.status})
            elif self.path == "/api/decide":
                self.check_queue(payload['id'])
                if type(payload.get("approve")) is not bool:
                    raise ValueError("approve must be boolean")
                if type(payload.get('version')) is not int:
                    raise ValueError('Review version is required')
                self.server.service.decide(payload["id"], payload["approve"],payload['version'])
                self.respond(200, {"ok": True})
            else:
                self.respond(404, {"error": "Not found"})
        except (ValueError, KeyError) as error:
            self.respond(400, {"error": str(error)})
        except Exception:
            self.respond(500, {"error": "Processing failed; inspect the saved audit and server configuration."})

    def check_queue(self, eid):
        job = self.server.queue.latest(eid)
        if job and job['state'] != 'DONE':
            raise ValueError('Saved work must complete a new model run before this action can be approved')


def serve(path="beda-live.db", port=8000):
    db = Database(path)
    db.initialize()
    if not db.list_crm_records():
        with (ROOT / "data/crm.csv").open() as file:
            for row in csv.DictReader(file):
                db.upsert_crm_record(CRMRecord(**row))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.write_lock = Lock()
    server.db, server.service = db, LiveService(db)
    server.queue = WorkQueue(server.service)
    server.queue.start()
    print(f"Workflow workspace: http://127.0.0.1:{port} — model: {server.service.model.model}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.queue.stop()
        server.server_close()
