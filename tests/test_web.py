import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tests.fixtures import fixtures

# This will fail to import if beda.web does not exist
from beda.service import EnquiryService
from beda.storage import Database
from beda.web import create_server


class TestWeb(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.db = Database(self.db_path)
        self.db.initialize()
        for rec in fixtures.crm:
            self.db.upsert_crm_record(rec)
        self.service = EnquiryService(self.db)
        self.api_key = "test-secret-key"

        self.server = create_server(self.db_path, api_key=self.api_key, host="127.0.0.1", port=0)
        self.port = self.server.server_port
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp_dir.cleanup()

    def _post(self, path: str, data: dict, headers: dict = None):
        url = f"http://127.0.0.1:{self.port}{path}"
        body = json.dumps(data).encode("utf-8")
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            code = e.code
            body = e.read().decode("utf-8")
            e.close()
            return code, body

    def _get(self, path: str):
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            code = e.code
            body = e.read().decode("utf-8")
            e.close()
            return code, body

    def test_ingestion_rejects_missing_api_key(self):
        status, body = self._post("/api/enquiries", fixtures.payload("E001"))
        self.assertEqual(status, 401)

    def test_ingestion_accepts_valid_api_key(self):
        status, body = self._post(
            "/api/enquiries",
            fixtures.payload("E001"),
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(status, 200)
        res = json.loads(body)
        self.assertEqual(res["enquiry_id"], "E001")

    def test_ui_index_and_detail_and_approval(self):
        # Ingest E001
        self._post(
            "/api/enquiries",
            fixtures.payload("E001"),
            headers={"X-API-Key": self.api_key},
        )

        # GET / index
        status, html = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("E001", html)

        # GET /enquiries/E001 detail
        status, html = self._get("/enquiries/E001")
        self.assertEqual(status, 200)
        self.assertIn("Truganina", html)
        self.assertIn("PENDING_APPROVAL", html)

        # POST /enquiries/E001/approve
        url = f"http://127.0.0.1:{self.port}/enquiries/E001/approve"
        req = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)

        # Re-fetch detail
        status, html = self._get("/enquiries/E001")
        self.assertEqual(status, 200)
        self.assertIn("SUCCEEDED", html)


if __name__ == "__main__":
    unittest.main()
