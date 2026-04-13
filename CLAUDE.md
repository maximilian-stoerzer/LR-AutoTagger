# LR-AutoTag — CLAUDE.md

Projektweite Leitlinien fuer Claude Code. Diese Datei gilt verbindlich und ueberschreibt Default-Verhalten.

---

## Projektuebersicht

Lightroom Classic Plugin + Backend-Service fuer automatische Verschlagwortung einer Fotobibliothek (100.000+ Bilder). Bildanalyse ueber lokales Vision-Modell (LLaVA auf Ollama/Nvidia P40), ergaenzt durch GPS-basiertes Reverse Geocoding. Interaktiver Modus (ausgewaehlte Bilder) und autonomer Batch-Modus (gesamte Bibliothek).

**Stack:** FastAPI (Python 3.12) Backend · Lua (Lightroom SDK) Plugin · PostgreSQL · Ollama/LLaVA 13B · httpx · Pillow

---

## Entwicklungsumgebung

### Python / venv
```bash
# Python-Interpreter
.venv/bin/python
.venv/bin/python -m pip   # pip ueber Modul aufrufen

# Tests ausfuehren
.venv/bin/python -m pytest
```

### PostgreSQL
- Bestehende PostgreSQL-Instanz auf dem Server
- Schema-Migration ueber SQL-Skripte (siehe Abschnitt Datenbank)

### Backend starten
```bash
# FastAPI Backend (uvicorn)
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Architektur (verbindlich)

> **Verbindlich / nicht verhandelbar:** Die folgenden Abschnitte
> (Schichtenmodell, Abhaengigkeitsregeln, ADRs) sind harte Vorgaben.
> Aenderungen an Schichten, Abhaengigkeiten oder ADR-Entscheidungen
> erfordern eine ausdrueckliche Diskussion mit dem User und das
> Aktualisieren dieses Dokuments. Code, der gegen diese Regeln
> verstoesst, wird vom CI-Job `quality` blockiert.

### Systemkontext

- **Fotografen-Rechner:** Lightroom Classic + LR-AutoTag Plugin (Lua)
- **Server (Debian VM):** LR-AutoTag Backend (FastAPI), erreichbar ueber LAN (HTTP)
- **Bestehende Infra:** Ollama (Shared Service, Nvidia P40) + PostgreSQL

### Komponentenmodell

```
┌─────────────────────────────────────────────┐
│     Lightroom Classic + Plugin (Lua)        │
│     Interaktiver Modus / Batch-Modus        │
└──────────────────┬──────────────────────────┘
                   │ REST API (HTTP/LAN)
                   ▼
┌─────────────────────────────────────────────┐
│     Backend-Service (Python / FastAPI)       │
│                                              │
│  REST API ─── Job-Manager ─── Keyword-Pipeline │
│                                              │
│  Pipeline: Vorverarbeitung → Reverse Geocoding │
│            → Vision-Analyse (Ollama) → Kombinator │
└───────────────┬──────────────┬──────────────┘
                │              │
        ┌───────┘              └───────┐
        ▼                              ▼
   Ollama/LLaVA 13B              PostgreSQL
   (Shared Service)          (Jobs, Ergebnisse)
```

### Schichten (Backend)

```
REST API Layer        app/api/         (FastAPI Router, Validierung)
    │
Service Layer         app/services/    (Business-Logik, Orchestrierung)
    │
Pipeline              app/pipeline/    (Keyword-Pipeline, Vision, Geocoding)
    │
Repository Layer      app/db/          (PostgreSQL-Zugriff, Job-Persistenz)
    │
Externe Services      Ollama (HTTP), Nominatim (HTTP)
```

**Abhaengigkeitsregeln (verbindlich, nicht verhandelbar):**
- Abhaengigkeiten nur von oben nach unten (API → Service → Pipeline → Repository → DB)
- API-Layer importiert **nicht** direkt aus `app.db.repository` (Zugriff nur ueber `request.app.state.repo`)
- Pipeline-, Service- und DB-Layer importieren **nicht** aus `app.api`
- Repository-Layer importiert **nicht** aus `app.services` oder `app.pipeline`
- Externe Services (Ollama, Nominatim) werden ausschliesslich ueber Clients im Pipeline-Layer angesprochen
- Kein zirkulaerer Import zwischen Modulen
- Diese Regeln werden vom CI-Job `quality` (`.github/workflows/ci.yml`) per grep-Check erzwungen

**Weitere harte Architektur-Regeln (nicht verhandelbar):**
- Alle API-Endpoints ausser `/api/v1/health` erfordern einen gueltigen `X-API-Key`
- Alle DB-Queries verwenden parametrisierte Statements (kein f-string oder `%`-Interpolation)
- Ollama-Requests laufen durch eine modul-globale `asyncio.Semaphore` (Shared-Service-Schutz)
- Nominatim-Requests werden auf max. 1 req/s gedrosselt (oeffentliche OSM-Nutzungsbedingungen)
- `image_keywords.image_id` ist Primary Key — Speichern erfolgt idempotent via `INSERT ... ON CONFLICT DO UPDATE`
- Bereits verschlagwortete Bilder werden in Batch-Jobs als `skipped` gefiltert (Idempotenz)
- Migrationen sind idempotent und werden beim Service-Start automatisch ausgefuehrt
- Keine hardcoded Secrets im Code — alle Konfigurationen ueber `.env` / `app/config.py`

### Architecture Decision Records (ADRs, verbindlich)

Die folgenden Entscheidungen sind getroffen und gelten verbindlich.
Volltext und Begruendung in `docs/tech.md` Abschnitt 5.

| ID | Entscheidung | Status |
|----|--------------|--------|
| ADR-001 | PostgreSQL als Task-Queue (kein Redis/RabbitMQ) | akzeptiert |
| ADR-002 | Batch-Modus ist Plugin-getrieben (Plugin pollt `/batch/next` und laedt einzeln hoch) | akzeptiert |
| ADR-003 | API-Key-Auth via `X-API-Key` Header (kein OAuth/JWT) | akzeptiert |
| ADR-004 | Ollama-Concurrency hart begrenzt durch `asyncio.Semaphore(OLLAMA_MAX_CONCURRENT)`, default 2 | akzeptiert |
| ADR-005 | Nominatim wird auf 1 req/s gedrosselt (modul-globaler Lock) | akzeptiert |
| ADR-006 | Eigene PostgreSQL-DB `lr_autotag` mit eigenem User (kein Schema-Sharing mit anderen Apps) | akzeptiert |
| ADR-007 | Coverage-Gates: 80% Line, 70% Branch im CI; Ziel der kritischen Module ≥ 90% | akzeptiert |

> **Aenderung von ADRs:** Wenn ein ADR ersetzt werden muss, wird der alte
> Eintrag auf `superseded by ADR-XXX` gesetzt und ein neuer ADR mit
> Begruendung der Aenderung in `docs/tech.md` ergaenzt. Niemals stillschweigend
> umentscheiden.

---

## REST API Endpunkte

| Endpunkt | Methode | Beschreibung |
|---|---|---|
| `/api/v1/analyze` | POST | Einzelbild analysieren (interaktiver Modus) |
| `/api/v1/batch/start` | POST | Batch-Job fuer Bibliothek starten |
| `/api/v1/batch/status` | GET | Fortschritt des laufenden Batch-Jobs |
| `/api/v1/batch/pause` | POST | Batch pausieren |
| `/api/v1/batch/resume` | POST | Batch fortsetzen |
| `/api/v1/batch/cancel` | POST | Batch abbrechen |
| `/api/v1/results/{image_id}` | GET | Keywords fuer ein bestimmtes Bild abrufen |
| `/api/v1/health` | GET | Service-Health inkl. Ollama-Verfuegbarkeit |

---

## Datenbank

### Tabellen

- **`batch_jobs`** — Batch-Job-Status (pending, running, paused, done, cancelled), Fortschritt
- **`chunks`** — Chunks innerhalb eines Batch-Jobs (pending → processing → done/failed), max. 3 Retries
- **`image_keywords`** — Ergebnisse pro Bild (Keywords, Geo-Keywords, Vision-Keywords, GPS, Modell)

### Konventionen
- UUIDs als Primary Keys (`gen_random_uuid()`)
- `TIMESTAMPTZ` fuer alle Zeitstempel
- Status als `TEXT` (nicht Enum) fuer Flexibilitaet
- Chunk-Groesse: 50 Bilder pro Chunk

---

## Keyword-Pipeline

1. **Vorverarbeitung:** Bild auf Analyse-Groesse skalieren (max. 1024px lange Seite), EXIF extrahieren
2. **Reverse Geocoding:** GPS → Ort, Stadt, Bundesland, Land (Nominatim/OpenStreetMap)
3. **Vision-Analyse:** Bild an Ollama/LLaVA mit strukturiertem Prompt → JSON-Array deutscher Keywords
4. **Kombinator:** Vision-Keywords + Geo-Keywords zusammenfuehren, Duplikate entfernen, normalisieren
5. **Ergebnis:** Max. 30 Keywords pro Bild, sachlich/technisch, deutsch

### Vision-Prompt (V2, mit Chain-of-Thought)

Der Prompt wird dynamisch zusammengebaut (`app/pipeline/ollama_client.py`).
Kanonische Version im Code, hier der kompakte Ueberblick:

```
Analysiere dieses Foto und gib deutsche Schlagworte zurueck.

Bevor du antwortest, ueberlege kurz:
- Woher kommt das Hauptlicht?
- Aus welchem Winkel wurde fotografiert?
- Ist das Bild schwarzweiss? Gibt es Bokeh, Langzeitbelichtung?
- Welche Stimmung vermittelt das Bild?

Kategorien:
- Objekte: frei, MAXIMAL 5
- Szene: frei, max 2
- Umgebung: frei, max 2
- Tageszeit: [Whitelist, 1 Wert]
- Jahreszeit: [Whitelist, 1 Wert]
- Wetter: [Whitelist, 1-2 Werte]
- Stimmung: [Whitelist, 1-2 Werte, Dramaturgie-zuerst-Reihenfolge]
- Lichtsituation: [Whitelist, 0-3 Werte, leer wenn unauffaellig]
- Perspektive: [Whitelist, 1 Wert, Normalperspektive nur als Fallback]
- Technik: [Whitelist, 0-2 Werte, leer wenn nichts erkennbar]

Regeln: Nur Whitelist-Werte, JSON-Array, max 30 Keywords.
```

Vollstaendige Whitelist-Inhalte: siehe `docs/tech.md` Abschnitt 3.5.1.

---

## Job-Manager (Batch-Modus)

- Teilt Bibliothek in Chunks a 50 Bilder
- Chunk-Status: `pending` → `processing` → `done` | `failed`
- Automatischer Retry bei Fehlschlag (max. 3 Versuche)
- Checkpoint nach jedem Chunk in PostgreSQL — ueberlebt Neustarts
- Ollama-Timeout-Handling: bei Nicht-Antwort → Chunk zurueck in Queue
- Idempotenz: bereits getaggte Bilder werden uebersprungen

---

## Ollama Shared Service

- Ollama laeuft als zentraler Daemon (HTTP API)
- Wird von mehreren Apps genutzt — Rate-Limiting ist Pflicht
- **Max. 2 parallele Requests** an Ollama (konfigurierbar)
- Modell: LLaVA 13B (24 GB VRAM auf Nvidia P40)
- Tageszeit-basierte Priorisierung moeglich (nachts hoeherer Durchsatz)

---

## Lightroom Plugin (Lua)

- Native LR-Integration ueber Lightroom SDK
- Exportiert JPG-Vorschaubilder (max. 1024px lange Seite)
- Liest GPS-Koordinaten und Metadaten aus LR-Katalog
- Kommuniziert per REST mit dem Backend
- Schreibt Keywords ueber LR SDK API in den Katalog zurueck
- Batch-UI: Fortschrittsanzeige, Pause/Resume/Abbruch

---

## Nichtfunktionale Anforderungen

| Anforderung | Zielwert |
|---|---|
| Durchsatz | 5-10 Bilder/Minute (LLaVA auf P40) |
| Datenverlust | Null (Checkpoint nach jedem Chunk) |
| Ollama-Koexistenz | Max. 2 parallele Requests |
| Keyword-Qualitaet | Sachlich, deutsch, relevant — lieber weniger als falsche |
| Idempotenz | Bereits getaggte Bilder ueberspringen |
| Neustart-Resilienz | Automatisch bei letztem Checkpoint fortsetzen |

---

## Coding-Konventionen

- **Python:** >= 3.12
- **Line-Length:** 120 Zeichen
- **Linter:** ruff (E, F, I, W)
- **Async:** FastAPI mit asyncio, httpx fuer Ollama-/Nominatim-Calls
- **Bildverarbeitung:** Pillow (Resize)
- **DB-Client:** psycopg (async)
- **Sprache im Code:** Englisch (Variablen, Funktionen, Kommentare)
- **Keywords/UI:** Deutsch
- **Pre-Commit (verbindlich):** Vor jedem Commit `/simplify` ausfuehren — Code-Review auf Reuse, Qualitaet und Effizienz

---

## Technologie-Stack

| Komponente | Technologie |
|---|---|
| LR Plugin | Lua (Lightroom SDK) |
| Backend | Python 3.12 + FastAPI |
| Task Queue | Eigene Implementierung auf PostgreSQL |
| Datenbank | PostgreSQL (bestehend) |
| Vision-Modell | LLaVA 13B via Ollama |
| Reverse Geocoding | Nominatim (OpenStreetMap) |
| Bildverarbeitung | Pillow |
| HTTP Client | httpx (async) |
