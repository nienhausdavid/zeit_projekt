import io
import json
import time
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
	pfade: list = []
	lehnt_reasoning_ab = False
	lehnt_think_ab = False
	verzoegerung = 0  # Sekunden vor der Antwort (langsames Modell)

	def do_GET(self):
		FakeVisionApi.pfade.append(self.path)
		if self.path.endswith("/api/tags"):
			antwort = {"models": [{"name": "qwen3-vl:4b-instruct"}, {"name": "gemma4:12b"}]}
		else:
			antwort = {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]}
		self.send_response(200)
		self.send_header("Content-Type", "application/json")
		self.end_headers()
		self.wfile.write(json.dumps(antwort).encode())

	def do_POST(self):
		body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
		time.sleep(FakeVisionApi.verzoegerung)
		FakeVisionApi.anfragen.append(body)
		FakeVisionApi.pfade.append(self.path)
		if FakeVisionApi.lehnt_reasoning_ab and "reasoning_effort" in body:
			self.send_response(400)
			self.end_headers()
			return
		if FakeVisionApi.lehnt_think_ab and "think" in body:
			self.send_response(400)
			self.end_headers()
			return
		nativ = self.path.endswith("/api/chat")
		if nativ:
			ok = any(m.get("images") for m in body["messages"])
		else:
			ok = body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
		if FakeVisionApi.antworten:
			text = FakeVisionApi.antworten.pop(0)
		else:
			text = "Stand: 123 456 km" if ok else "?"
		antwort = {"message": {"content": text}} if nativ else {"choices": [{"message": {"content": text}}]}
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
		FakeVisionApi.antworten, FakeVisionApi.anfragen, FakeVisionApi.pfade = [], [], []
		FakeVisionApi.lehnt_reasoning_ab = FakeVisionApi.lehnt_think_ab = False
		ocr._OHNE_DENKEN_PARAMETER.clear()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value(
			"Zeit Projekt Einstellungen",
			{
				"api_url": None,
				"model": None,
				"api_type": "OpenAI-kompatibel",
				"context_length": None,
				"keep_alive": None,
				"max_image_px": None,
				"image_original": 0,
				"request_timeout": None,
			},
		)
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")
		FakeVisionApi.verzoegerung = 0
		ocr._OHNE_DENKEN_PARAMETER.clear()

	def _api(self, antworten=None, ollama=False, kontext=None, keep_alive=None, bild_px=None):
		"""Startet den Fake-Server und richtet die Einstellungen darauf ein."""
		FakeVisionApi.antworten = list(antworten or [])
		server = HTTPServer(("127.0.0.1", 0), FakeVisionApi)
		threading.Thread(target=server.serve_forever, daemon=True).start()
		self.addCleanup(server.shutdown)
		frappe.db.set_single_value(
			"Zeit Projekt Einstellungen",
			{
				"api_url": f"http://127.0.0.1:{server.server_port}/v1",
				"model": "test",
				"api_type": "Ollama (nativ)" if ollama else "OpenAI-kompatibel",
				"context_length": kontext,
				"keep_alive": keep_alive,
				"max_image_px": bild_px,
			},
		)
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")

	def _gesendete_bildkante(self, body):
		"""Laengste Kante des Bildes, das der Fake-Server bekommen hat (JPEG, base64)."""
		import base64

		if "images" in body["messages"][-1]:
			b64 = body["messages"][-1]["images"][0]
		else:
			b64 = body["messages"][0]["content"][1]["image_url"]["url"].split(",", 1)[1]
		return max(Image.open(io.BytesIO(base64.b64decode(b64))).size)

	def test_ohne_einrichtung_kein_job(self):
		self.assertEqual(get_odometer_reading(self.file.file_url, "start_odometer"), {"queued": False})

	def test_fremde_datei_gesperrt(self):
		frappe.db.set_single_value("Zeit Projekt Einstellungen", {"api_url": "http://127.0.0.1:1", "model": "x"})
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")
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
			{
				"request_id": res["request_id"],
				"fieldname": "start_odometer",
				"reading": 123456,
				"unsicher": False,
				"fehler": None,
				"limit": 45,
			},
		)

	def _melde(self, antworten):
		"""Fuehrt den Hintergrund-Job gegen den Fake-Server aus und liefert die Meldung ans Formular."""
		self._api(antworten)
		with patch("frappe.publish_realtime") as publish:
			run_odometer_ocr(self.file.name, "end_odometer", "req", "Administrator")
		return publish.call_args.args[1]

	def test_ohne_antwort_wird_kein_fehler_gemeldet_wenn_nur_nichts_erkannt(self):
		daten = self._melde(["111", "222", "333"])
		self.assertIsNone(daten["fehler"])  # nichts erkannt ist kein Fehler

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

	def test_none_ist_kein_wert(self):
		"""Der Prompt erlaubt NONE (kein Gesamtstand sichtbar) - auch mit Zusatztext
		darf daraus keine Zahl werden."""
		self._api(["NONE", "none", "NONE (Tageszaehler 185.5)"])
		self.assertIsNone(ocr.read_odometer(self.file))
		self.assertEqual(len(FakeVisionApi.anfragen), 3)

	def test_prompt_erlaubt_none(self):
		self.assertIn("NONE", ocr.PROMPT)

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
		frappe.db.set_single_value("Zeit Projekt Einstellungen", {"api_url": "http://127.0.0.1:1/v1", "model": "x"})
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")
		self.assertEqual(ocr.read_odometer_detail(self.file)["fehler"], "nicht_erreichbar")
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")
		self.assertIsNone(ocr.read_odometer(self.file))

	def test_openai_pfad_bleibt_unveraendert(self):
		self._api(kontext=8192, keep_alive="30m")  # Felder gelten nur fuer Ollama (nativ)
		self.assertEqual(ocr.read_odometer(self.file), 123456)
		self.assertTrue(all(p.endswith("/v1/chat/completions") for p in FakeVisionApi.pfade))
		body = FakeVisionApi.anfragen[0]
		self.assertNotIn("options", body)
		self.assertNotIn("keep_alive", body)

	def test_ollama_nativ(self):
		"""Eigene Schnittstelle: /api/chat (ein angehaengtes /v1 der URL entfaellt), Bild
		als images, Denken aus, begrenzte Antwort, ohne Kontextfenster kein num_ctx."""
		self._api(ollama=True)
		self.assertEqual(ocr.read_odometer(self.file), 123456)
		self.assertTrue(all(p == "/api/chat" for p in FakeVisionApi.pfade))
		body = FakeVisionApi.anfragen[0]
		self.assertIs(body["think"], False)
		self.assertEqual(body["options"], {"num_predict": ocr.NUM_PREDICT})
		self.assertNotIn("keep_alive", body)
		# Text zuerst, Bild danach, als zwei Nachrichten (siehe ocr._frage_ollama)
		self.assertEqual([m["role"] for m in body["messages"]], ["user", "user"])
		self.assertEqual(body["messages"][0], {"role": "user", "content": ocr.PROMPT})
		self.assertTrue(body["messages"][1]["images"][0])
		self.assertEqual(body["messages"][1]["content"], "")

	def test_ollama_kontextfenster_und_verweildauer(self):
		self._api(ollama=True, kontext=8192, keep_alive="30m")
		ocr.read_odometer(self.file)
		body = FakeVisionApi.anfragen[0]
		self.assertEqual(body["options"], {"num_predict": ocr.NUM_PREDICT, "num_ctx": 8192})
		self.assertEqual(body["keep_alive"], "30m")

	def test_ollama_verweildauer_dauerhaft_als_zahl(self):
		self._api(ollama=True, keep_alive="-1")
		ocr.read_odometer(self.file)
		self.assertEqual(FakeVisionApi.anfragen[0]["keep_alive"], -1)

	def test_ollama_mehrheit_und_none(self):
		self._api(["2082", "100000", "100000"], ollama=True)
		self.assertEqual(ocr.read_odometer_mit_vertrauen(self.file), (100000, False))
		FakeVisionApi.antworten = ["NONE", "none", "NONE (Tageszaehler 185.5)"]
		self.assertEqual(ocr.read_odometer_mit_vertrauen(self.file), (None, False))

	def test_ollama_ohne_think_wenn_abgelehnt(self):
		FakeVisionApi.lehnt_think_ab = True
		self._api(ollama=True)
		self.assertEqual(ocr.read_odometer(self.file), 123456)
		self.assertEqual(sum("think" in b for b in FakeVisionApi.anfragen), 1)  # nur die erste wurde abgelehnt
		FakeVisionApi.anfragen.clear()
		self.assertEqual(ocr.read_odometer(self.file), 123456)
		self.assertFalse(any("think" in b for b in FakeVisionApi.anfragen))

	def test_modelle_abrufen_beide_schnittstellen(self):
		self._api()
		self.assertEqual(ocr.list_models(), ["gpt-4o", "gpt-4o-mini"])
		self.assertTrue(FakeVisionApi.pfade[-1].endswith("/v1/models"))
		self.assertEqual(ocr.list_models(api_type="Ollama (nativ)"), ["gemma4:12b", "qwen3-vl:4b-instruct"])
		self.assertEqual(FakeVisionApi.pfade[-1], "/api/tags")

	def test_einstellungen_pruefen_kontextfenster_und_verweildauer(self):
		einstellungen = frappe.get_doc("Zeit Projekt Einstellungen")
		for kontext in (100, 999999):
			einstellungen.context_length = kontext
			with self.assertRaises(frappe.ValidationError):
				einstellungen.validate()
		einstellungen.context_length = 8192
		einstellungen.keep_alive = "30m"
		einstellungen.validate()
		for falsch in ("abc", "30 Minuten", "m30"):
			einstellungen.keep_alive = falsch
			with self.assertRaises(frappe.ValidationError):
				einstellungen.validate()

	def test_bildgroesse_standard_1024(self):
		for ollama in (False, True):
			FakeVisionApi.anfragen.clear()
			self._api(ollama=ollama)
			ocr.read_odometer(self.file)  # Testbild ist 2000 x 1200
			self.assertEqual(self._gesendete_bildkante(FakeVisionApi.anfragen[0]), 1024)

	def test_bildgroesse_einstellbar(self):
		for ollama in (False, True):
			for px in (512, 1536):
				FakeVisionApi.anfragen.clear()
				self._api(ollama=ollama, bild_px=px)
				ocr.read_odometer(self.file)
				self.assertEqual(self._gesendete_bildkante(FakeVisionApi.anfragen[0]), px)

	def test_zeitlimit_aus_den_einstellungen(self):
		"""Ein langsames Modell (grosses Bild, grosses Modell) braucht mehr als die 45 s Standard;
		das Limit je Anfrage ist einstellbar und bestimmt auch Gesamtzeit und Job-Limit."""
		self.assertEqual((ocr.zeitlimit(), ocr.gesamtzeit(), ocr.job_timeout()), (45, 100, 120))

		FakeVisionApi.verzoegerung = 2.5
		self._api(ollama=True)
		frappe.db.set_single_value("Zeit Projekt Einstellungen", "request_timeout", 1)
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")
		self.assertEqual((ocr.zeitlimit(), ocr.job_timeout()), (1, 76))
		self.assertEqual(ocr.read_odometer_mit_vertrauen(self.file), (None, False))  # zu langsam fuer 1 s
		self.assertEqual(ocr.read_odometer_detail(self.file), {"wert": None, "sicher": False, "fehler": "timeout"})
		with patch("frappe.publish_realtime") as publish:
			run_odometer_ocr(self.file.name, "start_odometer", "req", "Administrator")
		daten = publish.call_args.args[1]
		self.assertEqual((daten["reading"], daten["fehler"], daten["limit"]), (None, "timeout", 1))

		frappe.db.set_single_value("Zeit Projekt Einstellungen", "request_timeout", 10)
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")
		self.assertEqual(ocr.read_odometer_mit_vertrauen(self.file)[0], 123456)  # mit 10 s klappt es

	def test_einstellungen_pruefen_zeitlimit(self):
		einstellungen = frappe.get_doc("Zeit Projekt Einstellungen")
		for sekunden in (5, 601):
			einstellungen.request_timeout = sekunden
			with self.assertRaises(frappe.ValidationError):
				einstellungen.validate()
		einstellungen.request_timeout = 120
		einstellungen.validate()

	def test_bildgroesse_vergroessert_nicht(self):
		self._api(bild_px=4096)  # das Testbild ist nur 2000 px breit
		ocr.read_odometer(self.file)
		self.assertEqual(self._gesendete_bildkante(FakeVisionApi.anfragen[0]), 2000)

	def test_originalaufloesung(self):
		self._api(bild_px=1024)
		frappe.db.set_single_value("Zeit Projekt Einstellungen", "image_original", 1)
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")
		ocr.read_odometer(self.file)
		self.assertEqual(self._gesendete_bildkante(FakeVisionApi.anfragen[0]), 2000)

	def test_einstellungen_pruefen_bildgroesse(self):
		einstellungen = frappe.get_doc("Zeit Projekt Einstellungen")
		for px in (100, 5000):
			einstellungen.max_image_px = px
			with self.assertRaises(frappe.ValidationError):
				einstellungen.validate()
		einstellungen.max_image_px = 1536
		einstellungen.validate()
