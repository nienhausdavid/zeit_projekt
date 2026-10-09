import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from PIL import Image

from zeit_projekt.fahrtenbuch.fahrtenbuch import get_odometer_reading, run_odometer_ocr
from zeit_projekt.zeit_projekt.tests.utils import TECH, ensure_fixtures


class FakeVisionApi(BaseHTTPRequestHandler):
	"""Antwortet wie eine OpenAI-kompatible Chat-Completions-API."""

	def do_POST(self):
		body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
		ok = body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
		antwort = {"choices": [{"message": {"content": "Stand: 123 456 km" if ok else "?"}}]}
		self.send_response(200)
		self.send_header("Content-Type", "application/json")
		self.end_headers()
		self.wfile.write(json.dumps(antwort).encode())

	def log_message(self, *args):
		pass


class TestKilometerstandErkennung(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_fixtures()
		buffer = io.BytesIO()
		Image.new("RGB", (2000, 1200), "white").save(buffer, format="PNG")
		cls.file = frappe.get_doc(
			{"doctype": "File", "file_name": "tacho.png", "content": buffer.getvalue(), "is_private": 1}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Fahrtenbuch Einstellungen", {"api_url": None, "model": None})
		frappe.clear_document_cache("Fahrtenbuch Einstellungen", "Fahrtenbuch Einstellungen")

	def test_ohne_einrichtung_kein_job(self):
		self.assertEqual(get_odometer_reading(self.file.file_url, "start_odometer"), {"queued": False})

	def test_fremde_datei_gesperrt(self):
		frappe.db.set_single_value("Fahrtenbuch Einstellungen", {"api_url": "http://127.0.0.1:1", "model": "x"})
		frappe.clear_document_cache("Fahrtenbuch Einstellungen", "Fahrtenbuch Einstellungen")
		frappe.set_user(TECH)
		with self.assertRaises(frappe.PermissionError):
			get_odometer_reading(self.file.file_url, "start_odometer")

	def test_erkennung_im_hintergrund(self):
		server = HTTPServer(("127.0.0.1", 0), FakeVisionApi)
		threading.Thread(target=server.serve_forever, daemon=True).start()
		try:
			frappe.db.set_single_value(
				"Fahrtenbuch Einstellungen",
				{"api_url": f"http://127.0.0.1:{server.server_port}/v1", "model": "test"},
			)
			frappe.clear_document_cache("Fahrtenbuch Einstellungen", "Fahrtenbuch Einstellungen")

			res = get_odometer_reading(self.file.file_url, "start_odometer")
			self.assertTrue(res["queued"])

			with patch("frappe.publish_realtime") as publish:
				run_odometer_ocr(self.file.name, "start_odometer", res["request_id"], "Administrator")
			event, daten = publish.call_args.args[:2]
			self.assertEqual(event, "zeit_projekt_odometer")
			self.assertEqual(daten, {"request_id": res["request_id"], "fieldname": "start_odometer", "reading": 123456})
		finally:
			server.shutdown()
