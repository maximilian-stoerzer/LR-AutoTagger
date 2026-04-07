# User Guide — LR-AutoTag fuer Fotografen

Willkommen! Dieses Dokument zeigt, wie du LR-AutoTag in deinem Foto-Workflow
einsetzt — ohne technische Vorkenntnisse.

> **Kurzfassung:** Du waehlst Bilder in Lightroom aus, klickst auf
> "Auto-Verschlagworten", und das Plugin schreibt automatisch passende
> deutsche Keywords inklusive Ortsnamen in deinen Katalog. Bei grossen
> Bibliotheken kannst du das auch im Hintergrund fuer alle Bilder
> gleichzeitig laufen lassen.

> **Status:** Das Plugin ist in Entwicklung. Dieser Guide beschreibt den
> geplanten Workflow. Solange das Plugin nicht fertig ist, koennen
> technisch versierte Nutzer das Backend manuell mit `curl` ansprechen
> (siehe `docs/admin.md` Abschnitt 4).

---

## 1. Was macht LR-AutoTag fuer dich?

| Du machst | Das Plugin macht |
|---|---|
| Bilder in LR auswaehlen | Vorschau exportieren, an den Server schicken |
| Auf "Auto-Tag" klicken | Wartet auf das Ergebnis |
| Nichts | Keywords werden in den Katalog geschrieben |

Die Schlagworte sind:
- **deutsch** und sachlich (z.B. "Bruecke", "Sonnenuntergang", "Fluss")
- **ortsbezogen**, wenn dein Bild GPS-Daten hat ("Heidelberg", "Baden-Wuerttemberg", "Deutschland")
- **maximal 25 pro Bild**, sortiert nach Relevanz (Ort zuerst, dann Bildinhalt)

---

## 2. Voraussetzungen

Bevor du loslegen kannst, muss folgendes vorhanden sein:

1. **Adobe Lightroom Classic** — Version 12 oder neuer
2. **Das LR-AutoTag-Plugin** — vom Admin installiert
3. **Eine Backend-URL und einen API-Key** — bekommst du vom Admin
   (z.B. `http://192.168.1.20:8000` und einen langen zufaelligen Schluessel)

Wenn etwas davon fehlt, frag deinen Admin oder schau in `docs/installation.md`.

---

## 3. Erste Einrichtung

### 3.1 Plugin-Einstellungen oeffnen
1. In Lightroom: **Datei → Plug-in-Manager...**
2. In der Liste **LR-AutoTag** auswaehlen
3. Rechts auf **Plugin-Einstellungen** klicken

### 3.2 Beispiel-Settings

| Feld | Wert eintragen | Bedeutung |
|---|---|---|
| **Backend URL** | `http://192.168.1.20:8000` | Adresse des Servers im Heimnetz |
| **API Key** | `7f3aXkP9...EinLangerSchluessel` | Vom Admin erhalten |
| **Connection Timeout** | `30` | Sekunden, die das Plugin auf eine Antwort wartet |
| **Vorschau-Qualitaet** | `JPEG 85` | Kompromiss aus Datenmenge und Qualitaet |
| **Vorschau-Groesse** | `1024 px` | Lange Seite des hochgeladenen Bildes |
| **Batch-Upload-Groesse** | `50` | Wie viele Bilder pro Block hochgeladen werden |

> 💡 **Tipp:** Klicke nach dem Eintragen auf **"Verbindung testen"** —
> wenn alles passt, siehst du einen gruenen Haken.

### 3.3 Erste Pruefung
1. Im Plugin-Dialog auf **Verbindung testen** klicken
2. Erwartete Anzeige: ✅ **"Backend erreichbar — alle Dienste OK"**
3. Bei Fehlern siehe Abschnitt 7 (Troubleshooting)

---

## 4. Workflow 1 — Einzelbild oder Auswahl verschlagworten

Dieser Modus ist ideal fuer **frische Aufnahmen**, die du gerade
importiert hast.

1. In der **Bibliothek** ein oder mehrere Bilder auswaehlen
2. **Bibliothek → Plug-in-Extras → LR-AutoTag → Ausgewaehlte verschlagworten**
   (oder Tastenkombination, falls du eine zugewiesen hast)
3. Eine kleine Fortschrittsanzeige laeuft
4. Wenn fertig: Die Keywords stehen direkt im rechten Bedienfeld unter
   **Stichwoerter**

**Wie lange dauert das?**
- 1 Bild: ca. 8–15 Sekunden
- 10 Bilder: ca. 1–2 Minuten
- Mehr siehe Workflow 2

> ⚠️ **Hinweis:** Falls Bilder schon Keywords haben, werden die neuen
> **dazugefuegt** (nicht ueberschrieben). Wenn du das nicht willst,
> entferne die alten Keywords vorher manuell.

---

## 5. Workflow 2 — Komplette Bibliothek im Batch-Modus

Fuer die Erstverschlagwortung deines kompletten Archivs (10.000 oder
100.000+ Bilder).

### 5.1 Starten
1. **Bibliothek → Plug-in-Extras → LR-AutoTag → Bibliothek verschlagworten**
2. Im Dialog auswaehlen, **welche Sammlung** verarbeitet werden soll
   (z.B. "Alle Fotos", oder ein bestimmter Ordner)
3. Auf **Starten** klicken

### 5.2 Was passiert
- Das Plugin sammelt alle Bild-IDs und schickt die Liste ans Backend
- Der Server filtert Bilder, die schon Keywords haben (du sparst Zeit)
- Das Plugin laedt Bilder Stueck fuer Stueck hoch und schreibt die
  Keywords zurueck
- Der Fortschritt wird live angezeigt:
  > **2.341 von 12.000 Bildern — geschaetzte Restdauer: 18 Std**

### 5.3 Steuerung waehrend des Laufs
- ⏸ **Pause** — Verarbeitung anhalten, kann jederzeit fortgesetzt werden
- ▶ **Fortsetzen** — Setzt da fort, wo pausiert wurde
- ⏹ **Abbrechen** — Beendet den Job. Bisher verschlagwortete Bilder
  bleiben behalten.

### 5.4 Was du waehrend des Laufs tun kannst
- **Lightroom weiter benutzen** (auch andere Bilder bearbeiten)
- **Lightroom schliessen** — beim naechsten Start meldet sich das Plugin
  und fragt, ob es fortsetzen soll
- **Computer ausschalten** — wird nach Neustart fortgesetzt, sobald
  Lightroom + Plugin wieder offen sind

> 💡 **Tipp fuer grosse Bibliotheken:** Starte den Batch abends/nachts.
> Pro 1.000 Bilder rechnest du grob mit ~2 Stunden (haengt von
> Server-Geschwindigkeit ab).

### 5.5 Nach Abschluss
- Eine Zusammenfassung wird angezeigt:
  > ✅ **12.000 Bilder verschlagwortet**
  > **127 uebersprungen** (hatten bereits Keywords)
  > **8 fehlgeschlagen** (siehe Log)
- Optional: Auf **Fehlerliste anzeigen** klicken, um die 8 Problemfaelle
  manuell zu pruefen

---

## 6. Was du wissen solltest

### 6.1 Welche Keywords bekomme ich?

**Beispiel 1 — Landschaftsfoto mit GPS:**
> Heidelberg, Baden-Wuerttemberg, Deutschland, Altstadt, Bruecke, Fluss,
> Wasser, Stein, Daemmerung, Wolken, Sonnenuntergang, Architektur,
> Stadt, Herbst

**Beispiel 2 — Portraet ohne GPS:**
> Person, Portrait, Frau, Lachen, Innenraum, Kunstlicht, Tageslicht,
> Fenster, Hintergrund-unscharf

**Beispiel 3 — Tierfoto mit GPS:**
> Bayern, Deutschland, Allgaeu, Tier, Kuh, Wiese, Gras, Berg, Alpen,
> Sommer, Tag, klare-Sicht

### 6.2 Was bekomme ich NICHT
- **Personennamen** ("Maria", "Hund Bello") — das System erkennt nur
  generische Inhalte
- **Stimmungen** ("traurig", "romantisch") — das Plugin ist bewusst sachlich
- **Marken/Modelle** ("Kanon EOS R5") — wird nicht aus EXIF gelesen,
  da Lightroom das eh schon hat
- **Englische Begriffe** — alle Keywords sind deutsch

### 6.3 Datenschutz
- **Bilder werden nur an deinen eigenen Backend-Server geschickt** — nicht
  an Cloud-Dienste
- Es gehen nur **JPG-Vorschauen** raus (max 1024 px), nicht die Originale
- GPS-Daten werden zum Server geschickt, um Ortsnamen aufzuloesen — die
  Aufloesung passiert ueber **OpenStreetMap (Nominatim)**, ein
  oeffentlicher Dienst
- Wenn du das nicht willst, kann der Admin eine eigene Nominatim-Instanz
  betreiben (siehe `docs/admin.md`)

### 6.4 Idempotenz — was bedeutet das?
Wenn du ein Bild zweimal verschlagwortest, ueberschreibt das Backend
einfach die alten Werte. Wenn du den ganzen Batch ein zweites Mal
startest, werden bereits verschlagwortete Bilder uebersprungen — du
verlierst keinen Fortschritt.

---

## 7. Troubleshooting

### "Verbindung testen" gibt Fehler

| Fehlermeldung | Was tun |
|---|---|
| **Backend nicht erreichbar** | Backend URL falsch? Server laeuft? WLAN/LAN-Verbindung? |
| **API Key ungueltig** | Schluessel beim Admin neu anfordern |
| **Datenbank nicht verfuegbar** | Admin informieren — Server-Problem |
| **Ollama nicht verfuegbar** | Admin informieren — KI-Modell offline |

### Bilder werden nicht analysiert
- Hast du Bilder ausgewaehlt, bevor du auf den Menupunkt geklickt hast?
- Sind die Bilder bereits verschlagwortet? Dann werden sie uebersprungen
- Pruefe die Statuszeile unten in Lightroom auf eine Fehlermeldung

### Batch laeuft sehr langsam
- Normal: 5–10 Bilder pro Minute (das Modell braucht Zeit)
- Wenn deutlich langsamer: Admin fragen, ob ein anderer Dienst den
  Server gerade auslastet
- Tipp: Nachts laufen lassen

### Keywords sind komisch oder unpassend
- Das KI-Modell macht ab und zu Fehler — du kannst sie wie jedes andere
  Keyword in Lightroom korrigieren oder loeschen
- Wenn du systematisch falsche Keywords siehst, melde das dem Admin —
  ggf. wird das Modell oder der Prompt angepasst

### Plugin "haengt" bei einem Bild
- Warte bis zu 2 Minuten — manche Bilder brauchen laenger
- Wenn nichts passiert: Plugin abbrechen und das Bild manuell ueberspringen
- Bei wiederholten Problemen: Bild-Format pruefen (RAW direkt geht nicht,
  das Plugin nutzt JPG-Vorschauen — Lightroom muss diese erzeugen koennen)

---

## 8. Tipps fuer den taeglichen Workflow

### 8.1 Tastenkombinationen einrichten
In Lightroom: **Bearbeiten → Tastaturbefehle...**, dann unter
"Plug-in-Extras" eine Tastenkombination fuer "Ausgewaehlte verschlagworten"
hinterlegen — z.B. `Cmd + Alt + K` (macOS) oder `Strg + Alt + K` (Windows).

### 8.2 Smart-Sammlungen fuer "noch nicht getaggt"
Erstelle eine **Smart-Sammlung** mit der Regel "Stichwoerter ist leer".
So findest du sofort alle Bilder, die noch nicht verschlagwortet sind, und
kannst sie gezielt ans Plugin uebergeben.

### 8.3 Reihenfolge im Import-Workflow
Empfohlener Workflow nach einem Foto-Shooting:
1. Importieren in Lightroom
2. Schnelle Vor-Sortierung (Sterne, Auswahl)
3. **LR-AutoTag** auf die Auswahl loslassen
4. Manuell ergaenzen (Personennamen, spezielle Tags)
5. Entwickeln / exportieren

### 8.4 Geo-Daten nachtragen
Bilder ohne GPS bekommen keine Ortsnamen. Wenn du nachtraeglich GPS-Daten
in Lightroom ergaenzt (Karten-Modul, oder GPX-Track), starte das Plugin
fuer diese Bilder einfach noch einmal — es ueberschreibt mit den jetzt
besseren Keywords.

---

## 9. FAQ

**F: Wird mein Internet-Traffic dafuer benoetigt?**
A: Nur das Reverse Geocoding (Ortsnamen) nutzt das Internet, sofern dein
Admin die oeffentliche OSM-Instanz konfiguriert hat. Die Bildanalyse selbst
laeuft komplett auf deinem eigenen Server im Heimnetz.

**F: Wird mein Bild irgendwo gespeichert?**
A: Im Backend werden die **erkannten Keywords** in einer Datenbank
gespeichert (zur Wiederverwendung). Die hochgeladenen JPG-Vorschauen
selbst werden **nach der Analyse weggeworfen**.

**F: Kann ich das System auch fuer Videos nutzen?**
A: Nein, aktuell nur Fotos.

**F: Funktioniert das mit RAW-Dateien?**
A: Ja — Lightroom erzeugt automatisch JPG-Vorschauen aus deinen RAW-Dateien
und schickt nur die zum Server. Die Originale werden nie hochgeladen.

**F: Kann ich das Modell wechseln (z.B. zu einem besseren KI)?**
A: Das macht der Admin in der Backend-Konfiguration (`OLLAMA_MODEL`).
Frag ihn, falls du Wuensche hast.

**F: Was kostet das?**
A: Nichts laufendes — alles laeuft auf deiner eigenen Hardware. Ein
einmaliger Aufwand fuer Server und GPU ist noetig (siehe
`docs/installation.md`).

---

## 10. Hilfe und Feedback

- **Technische Probleme:** An den Admin wenden
- **Bug oder Wunsch:** Issue im Repo erstellen:
  https://github.com/maximilian-stoerzer/LR-AutoTagger/issues
- **Dokumentation:** Siehe auch `docs/admin.md` und `docs/installation.md`
