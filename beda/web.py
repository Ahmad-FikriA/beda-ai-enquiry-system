import hmac
import http.server
import json
import re
from typing import Optional

from beda.service import EnquiryService
from beda.storage import Database
from beda.templates import render_detail, render_index


class EnquiryRequestHandler(http.server.BaseHTTPRequestHandler):
    # Attached at runtime on server instance:
    # server.db, server.service, server.api_key

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: int, html_str: str):
        body = html_str.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_api_key(self) -> bool:
        configured_key = getattr(self.server, "api_key", None)
        if not configured_key:
            return True

        # Check X-API-Key header
        header_key = self.headers.get("X-API-Key")
        if not header_key:
            auth_header = self.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                header_key = auth_header[7:].strip()

        if not header_key:
            return False

        return hmac.compare_digest(header_key.strip(), configured_key.strip())

    def do_GET(self):
        db: Database = self.server.db
        service: EnquiryService = self.server.service

        path = self.path.split("?")[0].rstrip("/")
        if path == "":
            path = "/"

        if path == "/":
            enquiries = db.list_enquiries()
            html_content = render_index(enquiries)
            self._send_html(200, html_content)
            return

        detail_match = re.match(r"^/enquiries/([^/]+)$", path)
        if detail_match:
            enquiry_id = detail_match.group(1)
            enquiry = db.get_enquiry(enquiry_id)
            if not enquiry:
                self._send_html(404, "<h1>404 Not Found</h1><p>Enquiry not found.</p>")
                return
            actions = service.actions_for(enquiry_id)
            audits = db.list_audit(enquiry_id)
            html_content = render_detail(enquiry, actions, audits)
            self._send_html(200, html_content)
            return

        self._send_html(404, "<h1>404 Not Found</h1>")

    def do_POST(self):
        db: Database = self.server.db
        service: EnquiryService = self.server.service

        path = self.path.split("?")[0].rstrip("/")

        # 1. Secured API ingestion endpoint
        if path == "/api/enquiries":
            if not self._check_api_key():
                self._send_json(401, {"error": "Unauthorized: Invalid or missing API key"})
                return

            try:
                content_len = int(self.headers.get("Content-Length", 0))
                body_bytes = self.rfile.read(content_len)
                payload = json.loads(body_bytes.decode("utf-8"))
            except Exception as e:
                self._send_json(400, {"error": f"Invalid JSON payload: {str(e)}"})
                return

            if not isinstance(payload, dict) or ("id" not in payload and "source_message_id" not in payload):
                self._send_json(400, {"error": "Payload must be a JSON object with 'id' or 'source_message_id'"})
                return

            try:
                enquiry = service.process_input(payload)
                actions = service.actions_for(enquiry.id)
                action_status = actions[0].status if actions else "NONE"
                self._send_json(
                    200,
                    {
                        "status": "success",
                        "enquiry_id": enquiry.id,
                        "category": enquiry.proposal.category if enquiry.proposal else None,
                        "action_status": action_status,
                        "assigned_owner": enquiry.recommendation.owner if enquiry.recommendation else None,
                    },
                )
            except Exception as e:
                self._send_json(500, {"error": f"Processing error: {str(e)}"})
            return

        # 2. UI Approval action endpoint
        approve_match = re.match(r"^/enquiries/([^/]+)/approve$", path)
        if approve_match:
            enquiry_id = approve_match.group(1)
            enquiry = db.get_enquiry(enquiry_id)
            if not enquiry:
                self._send_html(404, "<h1>404 Not Found</h1>")
                return

            try:
                service.approve_and_execute(enquiry_id, approver="local_reviewer")
                # Redirect back to enquiry detail
                self.send_response(303)
                self.send_header("Location", f"/enquiries/{enquiry_id}")
                self.end_headers()
            except Exception as e:
                self._send_html(500, f"<h1>Action Error</h1><p>{html.escape(str(e))}</p>")
            return

        self._send_html(404, "<h1>404 Not Found</h1>")

    def log_message(self, format, *args):
        # Silence default stderr logging during tests
        pass


def create_server(
    database_path: str,
    api_key: Optional[str] = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> http.server.HTTPServer:
    db = Database(database_path)
    db.initialize()
    service = EnquiryService(db)

    server = http.server.HTTPServer((host, port), EnquiryRequestHandler)
    server.db = db
    server.service = service
    server.api_key = api_key
    return server


def run_server(
    database_path: str,
    api_key: Optional[str] = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    server = create_server(database_path, api_key=api_key, host=host, port=port)
    print(f"Server started at http://{host}:{port}")
    if api_key:
        print("Ingestion API secured with configured API key.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server.server_close()
