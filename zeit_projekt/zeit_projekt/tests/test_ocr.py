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
	kopfzeilen: list = []  # Kopfzeilen aller Anfragen (klein geschrieben)
	erzwinge = None  # (Status, Text): naechste POST-Antwort ueberschreiben
	protokolle: dict = {}  # OpenCode: Modell -> Protokoll (chat/responses/anthropic/google), Standard chat

	def do_GET(self):
		FakeVisionApi.pfade.append(self.path)
		FakeVisionApi.kopfzeilen.append({k.lower(): v for k, v in self.headers.items()})
		if self.path.endswith("/openai/v1/models"):  # wie OpenCode: Liste liegt NICHT neben dem Chat-Pfad
			self.send_response(404)
			self.end_headers()
			return
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
		FakeVisionApi.kopfzeilen.append({k.lower(): v for k, v in self.headers.items()})
		if FakeVisionApi.erzwinge:
			status, text = FakeVisionApi.erzwinge
			self.send_response(status)
			self.end_headers()
			self.wfile.write(text.encode())
			return
		if "/inference/go" in self.path and "x-opencode-session" not in {k.lower() for k in self.headers}:
			self.send_response(400)
			self.end_headers()
			self.wfile.write(b"Request is missing x-opencode-session and cannot be routed efficiently.")
			return
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
		if "/inference/go" in self.path:
			protokoll = (
				"responses" if self.path.endswith("/responses")
				else "anthropic" if self.path.endswith("/anthropic/v1/messages")
				else "google" if ":generateContent" in self.path
				else "chat"
			)
			modell = self.path.split("/models/")[1].split(":")[0] if protokoll == "google" else body.get("model")
			if FakeVisionApi.protokolle.get(modell, "chat") != protokoll:
				self.send_response(400)
				self.end_headers()
				self.wfile.write(b"Model does not support this protocol.")
				return
			if protokoll != "chat":
				antwort = {
					"responses": {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Stand: 123 456 km"}]}]},
					"anthropic": {"content": [{"type": "text", "text": "Stand: 123 456 km"}]},
					"google": {"candidates": [{"content": {"parts": [{"text": "Stand: 123 456 km"}]}}]},
				}[protokoll]
				self.send_response(200)
				self.send_header("Content-Type", "application/json")
				self.end_headers()
				self.wfile.write(json.dumps(antwort).encode())
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
				"opencode_zugang": "Go (Abo)",
			},
		)
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")
		FakeVisionApi.verzoegerung = 0
		FakeVisionApi.erzwinge = None
		FakeVisionApi.kopfzeilen = []
		FakeVisionApi.protokolle = {}
		frappe.cache.delete_key(ocr._PROTOKOLL_CACHE)
		ocr._OHNE_DENKEN_PARAMETER.clear()

	def _api(self, antworten=None, ollama=False, kontext=None, keep_alive=None, bild_px=None):
		"""Startet den Fake-Server und richtet die Einstellungen darauf ein."""
		FakeVisionApi.antworten = list(antworten or [])
		server = HTTPServer(("127.0.0.1", 0), FakeVisionApi)
		threading.Thread(target=server.serve_forever, daemon=True).start()
		self.addCleanup(server.shutdown)
		self.port = server.server_port
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

	def test_genauer_status_der_erkennung(self):
		"""Der Job meldet vor dem Ergebnis die Phasen: start, bild, frage/antwort je Anfrage."""
		self._api(["55055", "55055"])
		with patch("frappe.publish_realtime") as publish:
			run_odometer_ocr(self.file.name, "start_odometer", "req", "Administrator")
		status = [c.args[1] for c in publish.call_args_list if c.args[0] == "zeit_projekt_odometer_status"]
		self.assertEqual([m["phase"] for m in status], ["start", "bild", "frage", "antwort", "frage", "antwort"])
		self.assertTrue(all(m["request_id"] == "req" and m["fieldname"] == "start_odometer" for m in status))
		self.assertEqual((status[2]["nr"], status[2]["von"]), (1, 3))
		self.assertEqual(status[3]["wert"], 55055)
		# das Ergebnis kommt als letztes Ereignis
		self.assertEqual(publish.call_args.args[0], "zeit_projekt_odometer")

	def test_abgestuerzter_job_meldet_fehler_statt_zu_schweigen(self):
		with (
			patch("zeit_projekt.fahrtenbuch.ocr.read_odometer_detail", side_effect=RuntimeError("kaputt")),
			patch("frappe.publish_realtime") as publish,
		):
			run_odometer_ocr(self.file.name, "start_odometer", "req", "Administrator")
		event, daten = publish.call_args.args[:2]
		self.assertEqual(event, "zeit_projekt_odometer")
		self.assertEqual((daten["fehler"], daten["reading"]), ("intern", None))

	def test_antwort_nennt_die_jobzeit_fuer_das_formular(self):
		self._api()
		self.assertEqual(get_odometer_reading(self.file.file_url, "start_odometer")["timeout"], ocr.job_timeout())

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

	@staticmethod
	def _http(status, daten=None):
		import requests

		antwort = requests.Response()
		antwort.status_code = status
		antwort._content = json.dumps(daten or {}).encode()
		return antwort

	def test_modellliste_weicht_bei_404_auf_den_listenpfad_aus(self):
		"""OpenCode Go: Chat unter .../go/openai/v1, Modellliste unter .../go/v1/models."""
		urls = []

		def get(url, **kwargs):
			urls.append(url)
			return self._http(404) if "/openai/v1/" in url else self._http(200, {"data": [{"id": "kimi-k3"}, {"id": "glm-5.3"}]})

		with patch("zeit_projekt.fahrtenbuch.ocr.requests.get", side_effect=get):
			modelle = ocr.list_models("https://opencode.ai/inference/go/openai/v1", "k", "OpenAI-kompatibel")
		self.assertEqual(modelle, ["glm-5.3", "kimi-k3"])
		self.assertEqual(
			urls,
			["https://opencode.ai/inference/go/openai/v1/models", "https://opencode.ai/inference/go/v1/models"],
		)

	def test_modellliste_meldet_die_echte_ursache(self):
		import requests

		from frappe import _

		url = "https://opencode.ai/inference/openai/v1"
		erwartet_404 = _("Der Pfad {0} wurde nicht gefunden (HTTP 404). Bitte die API-URL prüfen.").format(f"{url}/models")
		faelle = (
			(dict(return_value=self._http(404)), erwartet_404),  # Pfad falsch (auch der Ausweichpfad)
			(
				dict(return_value=self._http(401)),
				_("Die API hat den Zugang abgelehnt (HTTP {0}). Bitte API-Schlüssel und Abo prüfen.").format(401),
			),
			(dict(return_value=self._http(500)), _("Die API meldet einen Fehler (HTTP {0}).").format(500)),
			(
				dict(side_effect=requests.Timeout()),
				_("Zeitüberschreitung: Die API hat nicht innerhalb von 15 Sekunden geantwortet."),
			),
			(dict(side_effect=requests.ConnectionError()), _("Die API war nicht erreichbar.")),
		)
		for mock_args, erwartet in faelle:
			with patch("zeit_projekt.fahrtenbuch.ocr.requests.get", **mock_args):
				with self.assertRaises(frappe.ValidationError, msg=erwartet) as ctx:
					ocr.list_models(url, "k", "OpenAI-kompatibel")
			self.assertIn(erwartet, str(ctx.exception))

	def _opencode(self, modell="kimi-k3", zugang="Go (Abo)"):
		"""OpenCode gegen den Fake-Server: beide Basis-URLs auf ihn umgebogen, URL-Feld leer."""
		self._api()
		frappe.db.set_single_value(
			"Zeit Projekt Einstellungen",
			{"api_type": "OpenCode", "api_url": None, "model": modell, "opencode_zugang": zugang},
		)
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")
		return patch.multiple(
			ocr,
			OPENCODE_URL=f"http://127.0.0.1:{self.port}/inference/go",
			OPENCODE_ZEN_URL=f"http://127.0.0.1:{self.port}/inference",
			_bildfaehige_modelle=lambda zugang: None,  # kein Zugriff auf models.dev im Test
		)

	def test_opencode_sendet_pflicht_header_und_nutzt_den_go_pfad(self):
		with self._opencode():
			self.assertEqual(ocr.read_odometer(self.file), 123456)
		self.assertTrue(FakeVisionApi.pfade[-1].endswith("/inference/go/openai/v1/chat/completions"))
		sitzungen = {k["x-opencode-session"] for k in FakeVisionApi.kopfzeilen}
		self.assertEqual(len(sitzungen), 1)  # alle Anfragen eines Fotos in einer Sitzung
		self.assertTrue(FakeVisionApi.kopfzeilen[0]["user-agent"].startswith("zeit-projekt/"))
		self.assertEqual(FakeVisionApi.anfragen[0]["model"], "kimi-k3")

	def test_opencode_zugang_schaltet_zwischen_go_und_zen(self):
		with self._opencode(zugang="Go (Abo)"):
			self.assertEqual(ocr.read_odometer(self.file), 123456)
		self.assertTrue(FakeVisionApi.pfade[-1].endswith("/inference/go/openai/v1/chat/completions"))

		FakeVisionApi.pfade = []
		with self._opencode(zugang="Zen (Pay per use)"):
			self.assertEqual(ocr.read_odometer(self.file), 123456)
			ocr.list_models()
		self.assertTrue(FakeVisionApi.pfade[0].endswith("/inference/openai/v1/chat/completions"))
		self.assertNotIn("/inference/go", FakeVisionApi.pfade[0])
		self.assertTrue(FakeVisionApi.pfade[-1].endswith("/inference/v1/models"))

	def test_modelle_ohne_bild_eingabe_werden_ausgeblendet(self):
		antwort = self._http(200, {"data": [{"id": "kimi-k3"}, {"id": "glm-5.3"}, {"id": "hy3"}, {"id": "neues-modell"}]})
		bild = {"kimi-k3": True, "glm-5.3": False, "hy3": False}  # "neues-modell" kennt das Verzeichnis nicht
		with patch("zeit_projekt.fahrtenbuch.ocr.requests.get", return_value=antwort), patch.object(
			ocr, "_bildfaehige_modelle", return_value=bild
		):
			self.assertEqual(ocr.list_models(None, "k", "OpenCode", "Go (Abo)"), ["kimi-k3", "neues-modell"])

	def test_bildfaehige_modelle_aus_models_dev(self):
		import requests

		frappe.cache.delete_key(f"{ocr._BILD_CACHE}:opencode-go")
		frappe.cache.delete_key(f"{ocr._BILD_CACHE}:opencode")
		verzeichnis = {
			"opencode-go": {"models": {"kimi-k3": {"modalities": {"input": ["text", "image"]}}, "glm-5.3": {"modalities": {"input": ["text"]}}}},
			"opencode": {"models": {"gpt-5.4": {"modalities": {"input": ["text", "image", "pdf"]}}}},
		}
		with patch("zeit_projekt.fahrtenbuch.ocr.requests.get", return_value=self._http(200, verzeichnis)) as get:
			# je Zugang die eigenen Eintraege, Luecken aus dem anderen Zugang (gleiche Modelle)
			self.assertEqual(ocr._bildfaehige_modelle("Go (Abo)"), {"gpt-5.4": True, "kimi-k3": True, "glm-5.3": False})
			self.assertEqual(ocr._bildfaehige_modelle("Zen (Pay per use)"), {"kimi-k3": True, "glm-5.3": False, "gpt-5.4": True})
		self.assertEqual(get.call_count, 1)  # beide Zugaenge aus einem Abruf, danach aus dem Zwischenspeicher

		# nicht erreichbar: nichts filtern (None), kein Fehler
		frappe.cache.delete_key(f"{ocr._BILD_CACHE}:opencode-go")
		frappe.cache.delete_key(f"{ocr._BILD_CACHE}:opencode")
		with patch("zeit_projekt.fahrtenbuch.ocr.requests.get", side_effect=requests.ConnectionError()):
			self.assertIsNone(ocr._bildfaehige_modelle("Go (Abo)"))
		frappe.cache.delete_key(f"{ocr._BILD_CACHE}:opencode-go")
		frappe.cache.delete_key(f"{ocr._BILD_CACHE}:opencode")

	def test_go_liste_behaelt_die_enthaltenen_free_modelle(self):
		antwort = self._http(200, {"data": [{"id": "kimi-k3"}, {"id": "longcat-2.5-preview-free"}, {"id": "muse-spark-1.3-contributor"}]})
		with patch("zeit_projekt.fahrtenbuch.ocr.requests.get", return_value=antwort), patch.object(
			ocr, "_bildfaehige_modelle", return_value=None
		):
			modelle = ocr.list_models(None, "k", "OpenCode", "Go (Abo)")
		self.assertEqual(modelle, ["kimi-k3", "longcat-2.5-preview-free"])  # nur Contributor fliegt raus

	def test_zen_liste_ohne_free_und_contributor(self):
		antwort = self._http(
			200,
			{"data": [{"id": "gpt-5.4-nano"}, {"id": "big-pickle"}, {"id": "cat-jam-free"}, {"id": "muse-spark-1.3-contributor-free"}, {"id": "kimi-k3"}]},
		)
		with patch("zeit_projekt.fahrtenbuch.ocr.requests.get", return_value=antwort) as get, patch.object(
			ocr, "_bildfaehige_modelle", return_value=None
		):
			modelle = ocr.list_models(None, "k", "OpenCode", "Zen (Pay per use)")
		self.assertEqual(get.call_args.args[0], "https://opencode.ai/inference/v1/models")
		self.assertEqual(modelle, ["big-pickle", "gpt-5.4-nano", "kimi-k3"])  # big-pickle hat kein -free im Namen

	def test_opencode_ignoriert_eine_alte_api_url(self):
		with self._opencode():
			frappe.db.set_single_value("Zeit Projekt Einstellungen", "api_url", "https://opencode.ai/inference/openai/v1")
			frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")
			self.assertEqual(ocr.read_odometer(self.file), 123456)
			ocr.list_models()
		self.assertTrue(all("/inference/go/" in p for p in FakeVisionApi.pfade))

	def test_opencode_ohne_url_ist_konfiguriert(self):
		with self._opencode():
			self.assertTrue(ocr.is_configured())
		frappe.db.set_single_value("Zeit Projekt Einstellungen", "model", None)
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")
		self.assertFalse(ocr.is_configured())  # ohne Modell nicht

	def test_opencode_modellliste_liegt_unter_v1(self):
		with self._opencode():
			modelle = ocr.list_models()
		self.assertTrue(FakeVisionApi.pfade[-1].endswith("/inference/go/v1/models"))
		self.assertIn("x-opencode-session", FakeVisionApi.kopfzeilen[-1])
		self.assertIn("gpt-4o", modelle)

	def test_opencode_findet_das_protokoll_des_modells_selbst(self):
		for protokoll in ("responses", "anthropic", "google"):
			modell = f"m-{protokoll}"
			FakeVisionApi.protokolle = {modell: protokoll}
			FakeVisionApi.pfade = []
			with self._opencode(modell):
				self.assertEqual(ocr.read_odometer(self.file), 123456, protokoll)
			pfade = [p for p in FakeVisionApi.pfade if "/inference/go" in p]
			self.assertTrue(pfade[0].endswith("/openai/v1/chat/completions"), protokoll)  # erst Chat probiert
			self.assertTrue(any(protokoll in p or ("generateContent" in p) for p in pfade[1:]), protokoll)

			# Merken je Modell: die zweite Anfrage geht gleich ans richtige Protokoll
			FakeVisionApi.pfade = []
			with self._opencode(modell):
				ocr.read_odometer(self.file)
			self.assertFalse(FakeVisionApi.pfade[0].endswith("/openai/v1/chat/completions"), protokoll)

	def test_modellliste_ignoriert_maskierten_schluessel(self):
		"""Das Formular schickt einen gespeicherten Schluessel nur als Sternchen: dann den echten nehmen."""
		frappe.get_doc("Zeit Projekt Einstellungen").update({"api_key": "geheim-123"}).save()
		gesendet = []

		def get(url, headers=None, **kwargs):
			gesendet.append(headers.get("Authorization"))
			return self._http(200, {"data": [{"id": "kimi-k3"}]})

		with patch("zeit_projekt.fahrtenbuch.ocr.requests.get", side_effect=get):
			ocr.list_models("https://api.example.com/v1", "*********", "OpenAI-kompatibel")
			ocr.list_models("https://api.example.com/v1", "neu-eingetippt", "OpenAI-kompatibel")
		self.assertEqual(gesendet, ["Bearer geheim-123", "Bearer neu-eingetippt"])

	def test_opencode_modellliste_ohne_contributor(self):
		antwort = self._http(200, {"data": [{"id": "kimi-k3"}, {"id": "gemini-4-argon-contributor"}, {"id": "muse-spark-1.3-contributor"}]})
		with patch("zeit_projekt.fahrtenbuch.ocr.requests.get", return_value=antwort), patch.object(
			ocr, "_bildfaehige_modelle", return_value=None
		):
			self.assertEqual(ocr.list_models(None, "k", "OpenCode"), ["kimi-k3"])

	def test_denkblock_in_der_antwort(self):
		self.assertEqual(ocr._zahl_aus("<think>Tageszaehler 357.9, Gesamt 185460</think>185460"), 185460)
		self.assertIsNone(ocr._zahl_aus("<think>Der Nutzer will den Gesamtstand, 185460 vielleicht"))  # abgeschnitten
		self.assertIsNone(ocr._zahl_aus("<think>x</think>NONE"))

	def test_nachkommastellen_gehoeren_nicht_zum_stand(self):
		for text, erwartet in (
			("12345.6", 12345),
			("12345,6", 12345),
			("123 456,7 km", 123456),
			("123.456", 123456),  # Tausenderpunkt
			("1.234,5", 1234),
			("185460", 185460),
			("Stand: 123 456 km", 123456),
		):
			self.assertEqual(ocr._zahl_aus(text), erwartet, text)

	def test_fehlerursachen_der_anfrage(self):
		faelle = (
			((401, "unauthorized"), "zugang_abgelehnt"),
			((403, "forbidden"), "zugang_abgelehnt"),
			((400, "Upstream request failed: [400] This model does not support image inputs"), "modell_ohne_bild"),
			((400, "Model does not support this protocol."), "modell_nicht_unterstuetzt"),
			((400, "Upstream request failed: This Go model trains on your data"), "modell_freigabe_noetig"),
			((403, "OpenCode's free tier can only be used from within OpenCode."), "free_nur_in_opencode"),
			((429, "rate limit"), "limit_erreicht"),
			((402, "insufficient balance"), "limit_erreicht"),
			((500, "kaputt"), "nicht_erreichbar"),
		)
		with self._opencode():
			for erzwungen, erwartet in faelle:
				FakeVisionApi.erzwinge = erzwungen
				self.assertEqual(ocr.read_odometer_detail(self.file)["fehler"], erwartet, str(erzwungen))
		# Ein Modell ohne Bildfaehigkeit darf die URL nicht als "lehnt reasoning_effort ab" vormerken
		self.assertFalse(any("go/openai" in u for u in ocr._OHNE_DENKEN_PARAMETER))

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

	def test_handyfoto_wird_nach_exif_gedreht(self):
		"""Hochformat-Aufnahme = Querformat-Pixel + Orientation 6: das Modell soll sie aufrecht sehen."""
		bild = Image.new("RGB", (4080, 3072), (200, 200, 200))
		exif = Image.Exif()
		exif[0x0112] = 6  # 90 Grad im Uhrzeigersinn drehen
		puffer = io.BytesIO()
		bild.save(puffer, "JPEG", exif=exif)
		ergebnis = Image.open(io.BytesIO(ocr._downscale_to_jpeg(puffer.getvalue(), 1024)))
		self.assertEqual(ergebnis.size, (771, 1024))  # Hochformat

		# ohne Drehvermerk bleibt das Format
		ohne = io.BytesIO()
		bild.save(ohne, "JPEG")
		self.assertEqual(Image.open(io.BytesIO(ocr._downscale_to_jpeg(ohne.getvalue(), 1024))).size, (1024, 771))

	def test_50_megapixel_foto_wird_verkleinert(self):
		bild = Image.new("RGB", (8160, 6120), (180, 180, 180))  # 50 MP
		puffer = io.BytesIO()
		bild.save(puffer, "JPEG", quality=80)
		self.assertEqual(Image.open(io.BytesIO(ocr._downscale_to_jpeg(puffer.getvalue(), 1024))).size, (1024, 768))

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
