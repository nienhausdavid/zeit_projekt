"""Pausen im Zeitraum eines Belegs (Fahrt): Pruefung und Arbeitsabschnitte.

Gleiche Logik wie beim Kundeneinsatz (site_visit.py): je Arbeitsabschnitt
zwischen den Pausen eine Zeitblatt-Zeile, damit Pausen weder abgerechnet werden
noch mit einer Zeitbuchung kollidieren, die waehrend der Pause erfasst wird
(z. B. Notfall bei einem anderen Kunden). Die Pausen liegen in der Tabelle
"breaks" (Doctype "Site Visit Break")."""

import frappe
from frappe import _
from frappe.utils import get_datetime


def pausen_pruefen(doc, von="start_time", bis="end_time"):
	"""Pausen muessen im Zeitraum liegen und duerfen sich nicht ueberschneiden.
	Hoechstens eine darf noch laufen; endet der Beleg waehrend einer Pause
	("Timer stoppen" in der Pause), endet sie mit ihm."""
	if not doc.get(von):
		return
	if doc.get(bis):
		for row in doc.breaks:
			if not row.to_time:
				row.to_time = doc.get(bis)

	beginn = get_datetime(doc.get(von))
	ende = get_datetime(doc.get(bis)) if doc.get(bis) else None
	vorher_bis = None
	for row in sorted(doc.breaks, key=lambda r: get_datetime(r.from_time)):
		ab = get_datetime(row.from_time)
		pause_bis = get_datetime(row.to_time) if row.to_time else None
		if ab < beginn or (ende and (pause_bis or ab) > ende):
			frappe.throw(_("Zeile {0}: Die Pause muss innerhalb des Zeitraums liegen.").format(row.idx))
		if pause_bis and pause_bis < ab:
			frappe.throw(_("Zeile {0}: Das Ende der Pause muss nach ihrem Beginn liegen.").format(row.idx))
		if vorher_bis and ab < vorher_bis:
			frappe.throw(_("Zeile {0}: Die Pause überschneidet sich mit einer anderen.").format(row.idx))
		# Eine laufende Pause blockiert alles danach - so kann nur die letzte offen sein.
		vorher_bis = pause_bis or get_datetime("9999-12-31")


def arbeitsabschnitte(doc, von="start_time", bis="end_time"):
	"""Zeitraum ohne Pausen als Liste von (ab, bis)."""
	if not (doc.get(von) and doc.get(bis)):
		return []
	zeiger = get_datetime(doc.get(von))
	ende = get_datetime(doc.get(bis))
	abschnitte = []
	for row in sorted(doc.breaks, key=lambda r: get_datetime(r.from_time)):
		ab, pause_bis = get_datetime(row.from_time), get_datetime(row.to_time)
		if ab > zeiger:
			abschnitte.append((zeiger, ab))
		zeiger = max(zeiger, pause_bis)
	if zeiger < ende:
		abschnitte.append((zeiger, ende))
	return abschnitte
