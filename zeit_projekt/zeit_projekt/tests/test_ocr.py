import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from PIL import Image

from zeit_projekt.fahrtenbuch import ocr
from zeit_projekt.fahrtenbuch.fahrtenbuch import get_odometer_reading, run_odometer_ocr
from zeit_projekt.zeit_projekt.tests.utils import TECH, ensure_fixtures


class FakeVisionApi(BaseHTTPRequestHandler):
	"""Antwortet wie eine OpenAI-kompatible Chat-Completions-API.

	antworten: nacheinander ausgelieferte Antworttexte (leer: immer "Stand: 123 456 km")
	anfragen: alle empfangenen Bodies
	lehnt_reasoning_ab: HTTP 400, wenn reasoning_effort mitgeschickt wird"""

	antworten: list = []
	anfragen: list = []
	lehnt_reasoning_ab = False

	def do_POST(self):
		body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
		FakeVisionApi.anfragen.append(body)
		if FakeVisionApi.lehnt_reasoning_ab and "reasoning_effort" in body:
			self.send_response(400)
			self.end_headers()
			return
		ok = body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
		if FakeVisionApi.antworten:
			text = FakeVisionApi.antworten.pop(0)
		else:
			text = "Stand: 123 456 km" if ok else "?"
		antwort = {"choices": [{"message": {"content": text}}]}
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

	def setUp(self):
		FakeVisionApi.antworten, FakeVisionApi.anfragen, FakeVisionApi.lehnt_reasoning_ab = [], [], False
		ocr._OHNE_DENKEN_PARAMETER.clear()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Fahrtenbuch Einstellungen", {"api_url": None, "model": None})
		frappe.clear_document_cache("Fahrtenbuch Einstellungen", "Fahrtenbuch Einstellungen")
		ocr._OHNE_DENKEN_PARAMETER.clear()

	def _api(self, antworten=None):
		"""Startet den Fake-Server und richtet die Einstellungen darauf ein."""
		FakeVisionApi.antworten = list(antworten or [])
		server = HTTPServer(("127.0.0.1", 0), FakeVisionApi)
		threading.Thread(target=server.serve_forever, daemon=True).start()
		self.addCleanup(server.shutdown)
		frappe.db.set_single_value(
			"Fahrtenbuch Einstellungen",
			{"api_url": f"http://127.0.0.1:{server.server_port}/v1", "model": "test"},
		)
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
		self._api()
		res = get_odometer_reading(self.file.file_url, "start_odometer")
		self.assertTrue(res["queued"])

		with patch("frappe.publish_realtime") as publish:
			run_odometer_ocr(self.file.name, "start_odometer", res["request_id"], "Administrator")
		event, daten = publish.call_args.args[:2]
		self.assertEqual(event, "zeit_projekt_odometer")
		self.assertEqual(
			daten,
			{"request_id": res["request_id"], "fieldname": "start_odometer", "reading": 123456, "unsicher": False},
		)

	def _melde(self, antworten):
		"""Fuehrt den Hintergrund-Job gegen den Fake-Server aus und liefert die Meldung ans Formular."""
		self._api(antworten)
		with patch("frappe.publish_realtime") as publish:
			run_odometer_ocr(self.file.name, "end_odometer", "req", "Administrator")
		return publish.call_args.args[1]

	def test_einhellig_ist_sicher(self):
		daten = self._melde(["55055", "55055"])
		self.assertEqual((daten["reading"], daten["unsicher"]), (55055, False))

	def test_mehrheit_mit_ausreisser_ist_unsicher(self):
		daten = self._melde(["2082", "100000", "100000"])
		self.assertEqual((daten["reading"], daten["unsicher"]), (100000, True))

	def test_ohne_wert_nicht_als_unsicher_gemeldet(self):
		daten = self._melde(["111", "222", "333"])
		self.assertEqual((daten["reading"], daten["unsicher"]), (None, False))

	def test_zwei_gleiche_antworten_genuegen(self):
		self._api(["55055", "55055", "99"])
		self.assertEqual(ocr.read_odometer(self.file), 55055)
		self.assertEqual(len(FakeVisionApi.anfragen), 2)  # die dritte Anfrage entfaellt

	def test_mehrheit_gegen_ausreisser(self):
		self._api(["2082", "100000", "100000"])
		self.assertEqual(ocr.read_odometer(self.file), 100000)
		self.assertEqual(len(FakeVisionApi.anfragen), 3)

	def test_keine_mehrheit_kein_wert(self):
		self._api(["111", "222", "333"])
		self.assertIsNone(ocr.read_odometer(self.file))

	def test_zahlensalat_wird_verworfen(self):
		salat = "9840984016093441583615836"  # so hat ein Modell einmal geantwortet
		self._api([salat, salat, salat])
		self.assertIsNone(ocr.read_odometer(self.file))

	def test_denken_wird_abgeschaltet(self):
		self._api()
		ocr.read_odometer(self.file)
		self.assertTrue(all(b.get("reasoning_effort") == "none" for b in FakeVisionApi.anfragen))

	def test_api_ohne_reasoning_parameter(self):
		"""Lehnt die API reasoning_effort ab (HTTP 400), geht es ohne weiter - und
		die naechste Erkennung schickt den Parameter gar nicht erst."""
		FakeVisionApi.lehnt_reasoning_ab = True
		self._api()
		self.assertEqual(ocr.read_odometer(self.file), 123456)
		ablehnungen = sum("reasoning_effort" in b for b in FakeVisionApi.anfragen)
		self.assertEqual(ablehnungen, 1)  # nur die erste Anfrage wurde abgelehnt

		FakeVisionApi.anfragen.clear()
		self.assertEqual(ocr.read_odometer(self.file), 123456)
		self.assertFalse(any("reasoning_effort" in b for b in FakeVisionApi.anfragen))

	def test_api_nicht_erreichbar(self):
		frappe.db.set_single_value("Fahrtenbuch Einstellungen", {"api_url": "http://127.0.0.1:1/v1", "model": "x"})
		frappe.clear_document_cache("Fahrtenbuch Einstellungen", "Fahrtenbuch Einstellungen")
		self.assertIsNone(ocr.read_odometer(self.file))
