# LR-AutoTag — Testspezifikation

---

## 1. Ziele & Qualitaetsanforderungen

### 1.1 Testziele

| Ziel | Beschreibung |
|---|---|
| Korrektheit | Keyword-Pipeline liefert fachlich korrekte, deutsche Keywords |
| Robustheit | System uebersteht Ausfaelle von Ollama, Nominatim, PostgreSQL |
| Idempotenz | Mehrfach-Laeufe erzeugen keine Duplikate oder Seiteneffekte |
| Neustart-Resilienz | Batch-Jobs werden nach Neustart korrekt fortgesetzt |
| Sicherheit | API-Key-Auth schuetzt alle Endpunkte ausser /health |
| Performance | Durchsatz von 5-10 Bildern/Minute bei Einhaltung des Ollama-Rate-Limits |

### 1.2 Coverage-Anforderungen

| Metrik | Minimum | Ziel | Werkzeug |
|---|---|---|---|
| Line Coverage | 80% | 90% | `pytest-cov` |
| Branch Coverage | 70% | 85% | `pytest-cov --cov-branch` |
| Modul-Coverage (pro Modul) | 75% | 90% | `pytest-cov` pro Package |
| Mutations-Score (kritische Module) | — | 70% | `mutmut` (optional, spaeter) |

**Kritische Module mit erhoehter Coverage-Anforderung (min. 90% Line):**
- `app/pipeline/keyword_pipeline.py`
- `app/pipeline/ollama_client.py` (Parse-Logik)
- `app/db/repository.py`
- `app/services/job_manager.py`
- `app/api/auth.py`

**Coverage-Ausnahmen:**
- `app/config.py` (reine Konfiguration, kein Testmehrwert)
- `__init__.py` Dateien

### 1.3 Qualitaetsregeln fuer Tests

- Jeder Test hat genau eine Assertion (bzw. eine logische Pruefung)
- Testnamen folgen dem Schema: `test_<modul>_<szenario>_<erwartung>`
- Kein Test darf von externen Services abhaengen (Mocks fuer Ollama, Nominatim)
- Integrationstests nutzen eine echte PostgreSQL-Testdatenbank
- Tests muessen deterministisch und reihenfolge-unabhaengig sein
- Keine Sleep-Aufrufe in Tests (ausser explizite Timing-Tests)
- Test-Fixtures werden per `conftest.py` pro Teststufe bereitgestellt

---

## 2. Teststufen

### 2.1 Uebersicht

```
┌──────────────────────────────────────────────────────────┐
│  Stufe 4: UAT (User Acceptance Tests)                    │
│  Manuell + teilautomatisiert, End-to-End mit LR Plugin   │
├──────────────────────────────────────────────────────────┤
│  Stufe 3: Systemtests                                     │
│  Kompletter Backend-Service, echte DB, gemockte Ext.Svcs  │
├──────────────────────────────────────────────────────────┤
│  Stufe 3b: NFA-Tests (Performance, Security)              │
│  Last, Durchsatz, Auth, Input-Validation                  │
├──────────────────────────────────────────────────────────┤
│  Stufe 2: Integrationstests                               │
│  Modul-Zusammenspiel, echte DB, gemockte Ext.Svcs         │
├──────────────────────────────────────────────────────────┤
│  Stufe 1: Modultests (Unit Tests)                         │
│  Einzelne Klassen/Funktionen, alles gemockt               │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Testumgebungen

| Stufe | PostgreSQL | Ollama | Nominatim | FastAPI |
|---|---|---|---|---|
| Modultests | Mock | Mock | Mock | — |
| Integrationstests | Echte Test-DB | Mock | Mock | — |
| Systemtests | Echte Test-DB | Mock | Mock | TestClient |
| NFA-Performance | Echte Test-DB | Mock (schnell) | Mock | TestClient |
| NFA-Security | Echte Test-DB | Mock | Mock | TestClient |
| UAT | Produktions-DB | Echter Service | Echter Service | Echter Server |

---

## 3. Testableitungsmethoden

### 3.1 Systematische Ableitung

Jeder Testfall wird nach mindestens einer der folgenden Methoden abgeleitet:

#### Happy Path
Standardfall mit gueltigen Eingaben und erwarteter Ausgabe. Mindestens ein Happy-Path-Test pro oeffentlicher Funktion/Endpunkt.

#### Fehlerfaelle (Error Path)
Gezieltes Testen von Fehlersituationen:
- Externe Services nicht erreichbar (Ollama-Timeout, Nominatim-Fehler, DB-Verbindung verloren)
- Ungueltige Eingaben (kaputtes Bild, fehlende Pflichtfelder)
- Zustandskonflikte (Batch pausieren wenn keiner laeuft, doppelter Start)

#### Edge Cases (Grenzwertanalyse)
Testen an den Grenzen geltender Wertebereiche:
- GPS: (0, 0), (90, 180), (-90, -180), knapp ausserhalb
- Bildgroesse: 1x1px, exakt 1024px, 10000x10000px, 0 Bytes
- Keywords: 0 Keywords, exakt 25, mehr als 25 von Ollama
- Batch: 0 Bilder, 1 Bild, exakt 50 (=1 Chunk), 51 (=2 Chunks), 100.000

#### Aequivalenzklassen
Aufteilung des Eingaberaums in Klassen mit gleichem erwarteten Verhalten:

| Parameter | Klassen |
|---|---|
| Bild-Format | JPEG, PNG, TIFF, RAW, WebP, ungueltig |
| GPS-Daten | vorhanden + gueltig, vorhanden + ungueltig, fehlend |
| Ollama-Antwort | gueltiges JSON-Array, JSON in Markdown, Freitext, leer, Timeout |
| Batch-Status | pending, running, paused, done, cancelled |
| API-Key | gueltig, ungueltig, fehlend, leer |

#### Zustandsbasierte Tests (State Transition)
Fuer den Batch-Job-Lifecycle:

```
pending ──► running ──► done
                │
                ├──► paused ──► running (resume)
                │           ──► cancelled
                │
                └──► cancelled
```

Jeder erlaubte Uebergang = 1 Test. Jeder verbotene Uebergang = 1 Negativtest.

---

## 4. Teststruktur (Verzeichnislayout)

```
backend/
  tests/
    conftest.py                         # Gemeinsame Fixtures (DB, Mocks, Test-Images)
    
    unit/                               # Stufe 1: Modultests
      conftest.py
      pipeline/
        test_image_processor.py
        test_ollama_client.py
        test_geocoder.py
        test_keyword_pipeline.py
      db/
        test_repository.py
      services/
        test_job_manager.py
      api/
        test_auth.py
    
    integration/                        # Stufe 2: Integrationstests
      conftest.py                       # Test-DB Setup/Teardown
      test_pipeline_integration.py      # Pipeline mit echter DB
      test_batch_flow.py                # Batch-Lifecycle mit echter DB
      test_repository_integration.py    # Repository gegen echte DB
    
    system/                             # Stufe 3: Systemtests
      conftest.py                       # FastAPI TestClient
      test_api_analyze.py              # POST /analyze End-to-End
      test_api_batch.py                # Batch-Endpoints End-to-End
      test_api_health.py               # GET /health
      test_api_results.py              # GET /results/{image_id}
    
    nfa/                                # Stufe 3b: Nichtfunktionale Tests
      test_performance.py              # Durchsatz, Latenz
      test_security.py                 # Auth, Input Validation, Injection
    
    fixtures/                           # Testdaten
      test_image_rgb.jpg
      test_image_rgba.png
      test_image_small.jpg             # 1x1px
      test_image_large.jpg             # >1024px
      test_image_corrupt.bin           # Kaputte Datei
```

---

## 5. Testfaelle nach Teststufe und Modul

### 5.1 Modultests (Unit)

#### 5.1.1 `image_processor.py` — `resize_for_analysis()`

| ID | Szenario | Ableitung | Eingabe | Erwartung |
|---|---|---|---|---|
| U-IMG-01 | JPEG unter Maximalgroesse | Happy Path | 800x600 JPEG | Unveraenderte Groesse, JPEG-Output |
| U-IMG-02 | Groesseres Bild wird skaliert | Happy Path | 2048x1536 JPEG | 1024x768 JPEG |
| U-IMG-03 | Hochformat-Bild | Aequivalenzklasse | 1536x2048 JPEG | 768x1024 JPEG |
| U-IMG-04 | RGBA wird zu RGB konvertiert | Aequivalenzklasse | 800x600 PNG RGBA | RGB JPEG |
| U-IMG-05 | Minimales Bild | Grenzwert | 1x1 JPEG | 1x1 JPEG |
| U-IMG-06 | Exakt 1024px lange Seite | Grenzwert | 1024x768 JPEG | Unveraendert |
| U-IMG-07 | Sehr grosses Bild | Grenzwert | 10000x8000 JPEG | 1024x819 JPEG |
| U-IMG-08 | Kaputte Bilddaten | Fehlerfall | Zufaellige Bytes | Exception (Pillow) |
| U-IMG-09 | Leere Eingabe | Grenzwert | 0 Bytes | Exception |
| U-IMG-10 | Palette-Mode PNG | Aequivalenzklasse | Palette PNG | RGB JPEG |

#### 5.1.2 `ollama_client.py` — `OllamaClient`

| ID | Szenario | Ableitung | Eingabe/Mock | Erwartung |
|---|---|---|---|---|
| U-OLL-01 | Gueltiges JSON-Array | Happy Path | `["Bruecke", "Fluss"]` | `["Bruecke", "Fluss"]` |
| U-OLL-02 | JSON in Markdown-Codeblock | Aequivalenzklasse | `` ```json\n["a","b"]\n``` `` | `["a", "b"]` |
| U-OLL-03 | Mehr als 25 Keywords | Grenzwert | Array mit 30 Eintraegen | Abgeschnitten auf 25 |
| U-OLL-04 | Leeres Array | Grenzwert | `[]` | `[]` |
| U-OLL-05 | Freitext statt JSON | Aequivalenzklasse | `"Bruecke, Fluss, Berg"` | `["Bruecke", "Fluss", "Berg"]` |
| U-OLL-06 | Leere Antwort | Grenzwert | `""` | `[]` |
| U-OLL-07 | Gemischte Typen im Array | Edge Case | `["Bruecke", 42, null]` | `["Bruecke", "42"]` |
| U-OLL-08 | Ollama-Timeout | Fehlerfall | httpx.TimeoutException | Exception propagiert |
| U-OLL-09 | Ollama HTTP 500 | Fehlerfall | HTTP 500 Response | Exception propagiert |
| U-OLL-10 | Ollama nicht erreichbar | Fehlerfall | ConnectionError | Exception propagiert |
| U-OLL-11 | Health-Check positiv | Happy Path | HTTP 200 auf /api/tags | `True` |
| U-OLL-12 | Health-Check negativ | Fehlerfall | ConnectionError | `False` |
| U-OLL-13 | Semaphore begrenzt Parallelitaet | NFA | 5 parallele Aufrufe | Max. 2 gleichzeitig |
| U-OLL-14 | Keywords mit Whitespace | Edge Case | `[" Bruecke ", " "]` | `["Bruecke"]` |
| U-OLL-15 | JSON-Array im Fliesstext | Aequivalenzklasse | `Hier sind Keywords: ["a","b"]` | `["a", "b"]` |

#### 5.1.3 `geocoder.py` — `Geocoder`

| ID | Szenario | Ableitung | Eingabe/Mock | Erwartung |
|---|---|---|---|---|
| U-GEO-01 | Vollstaendige Adresse | Happy Path | Heidelberg-Koordinaten | city, state, country, geo_keywords |
| U-GEO-02 | Nur Land verfuegbar | Aequivalenzklasse | Ozean-nahe Koordinaten | country in geo_keywords |
| U-GEO-03 | Nominatim-Fehler | Fehlerfall | HTTP 500 | `None` |
| U-GEO-04 | Nominatim-Timeout | Fehlerfall | Timeout | `None` |
| U-GEO-05 | Nominatim liefert error-Feld | Fehlerfall | `{"error": "..."}` | `None` |
| U-GEO-06 | GPS (0, 0) — Null Island | Grenzwert | lat=0, lon=0 | Gueltiges Ergebnis oder None |
| U-GEO-07 | Extreme Koordinaten | Grenzwert | lat=90, lon=180 | Gueltiges Ergebnis oder None |
| U-GEO-08 | Throttle: 2 Requests < 1s | NFA | Zwei schnelle Aufrufe | Zweiter wartet mind. 1s |
| U-GEO-09 | Suburb + City + State | Happy Path | Stadtteil-Koordinaten | Alle Ebenen in geo_keywords |
| U-GEO-10 | Antwort ohne address-Feld | Edge Case | `{"display_name": "X"}` | location_name = "X" |

#### 5.1.4 `keyword_pipeline.py` — `KeywordPipeline`

| ID | Szenario | Ableitung | Setup | Erwartung |
|---|---|---|---|---|
| U-KWP-01 | Bild mit GPS | Happy Path | GPS + Vision-Mock | Vision + Geo Keywords kombiniert |
| U-KWP-02 | Bild ohne GPS | Aequivalenzklasse | Kein GPS | Nur Vision Keywords |
| U-KWP-03 | Duplikate zwischen Vision und Geo | Edge Case | "Berlin" in beiden | Nur einmal in Ergebnis |
| U-KWP-04 | Case-insensitive Deduplizierung | Edge Case | "berlin" + "Berlin" | Nur einmal |
| U-KWP-05 | Mehr als 25 kombinierte Keywords | Grenzwert | 20 Geo + 20 Vision | Max. 25 |
| U-KWP-06 | Geo-Keywords haben Vorrang | Happy Path | Geo + Vision | Geo zuerst in Liste |
| U-KWP-07 | Ollama-Fehler propagiert | Fehlerfall | Ollama wirft Exception | Exception propagiert |
| U-KWP-08 | Geocoding fehlgeschlagen | Fehlerfall | Geocoder returns None | Nur Vision Keywords |
| U-KWP-09 | Ergebnis wird in DB gespeichert | Happy Path | image_id angegeben | `save_image_keywords()` aufgerufen |
| U-KWP-10 | Kein Speichern ohne image_id | Edge Case | image_id = None | Kein DB-Aufruf |

#### 5.1.5 `repository.py` — `Repository` (mit Mock-DB)

| ID | Szenario | Ableitung | Erwartung |
|---|---|---|---|
| U-REP-01 | ping() bei aktiver Verbindung | Happy Path | `True` |
| U-REP-02 | ping() bei toter Verbindung | Fehlerfall | `False` |
| U-REP-03 | save + get image_keywords | Happy Path | Round-Trip korrekt |
| U-REP-04 | image_already_processed — ja | Happy Path | `True` |
| U-REP-05 | image_already_processed — nein | Happy Path | `False` |
| U-REP-06 | save_image_keywords UPSERT | Edge Case | Zweimal speichern, einmal lesen |

#### 5.1.6 `job_manager.py` — `JobManager`

| ID | Szenario | Ableitung | Setup | Erwartung |
|---|---|---|---|---|
| U-JOB-01 | Job erstellen | Happy Path | 100 Images | Job + 2 Chunks |
| U-JOB-02 | Bereits getaggte werden uebersprungen | Idempotenz | 50 neue + 50 bestehende | skipped=50, total=100 |
| U-JOB-03 | Leere Imageliste | Grenzwert | 0 new images | Job mit 0 Chunks |
| U-JOB-04 | Exakt 50 Bilder = 1 Chunk | Grenzwert | 50 Images | 1 Chunk |
| U-JOB-05 | 51 Bilder = 2 Chunks | Grenzwert | 51 Images | 2 Chunks (50 + 1) |
| U-JOB-06 | Pause wenn running | State Transition | Status=running | Status→paused |
| U-JOB-07 | Pause wenn nicht running | State Transition | Status=done | Keine Aenderung |
| U-JOB-08 | Resume wenn paused | State Transition | Status=paused | Status→running |
| U-JOB-09 | Cancel wenn running | State Transition | Status=running | Status→cancelled |
| U-JOB-10 | Cancel wenn paused | State Transition | Status=paused | Status→cancelled |
| U-JOB-11 | get_next_image_id bei leerem Batch | Grenzwert | Keine pending images | `None` |
| U-JOB-12 | mark_image_done letztes Bild | Edge Case | Letztes Bild im Batch | Job-Status→done |
| U-JOB-13 | get_status ohne aktiven Job | Edge Case | Kein Job | `{"status": "idle"}` |

#### 5.1.7 `auth.py` — API-Key Middleware

| ID | Szenario | Ableitung | Eingabe | Erwartung |
|---|---|---|---|---|
| U-AUTH-01 | Gueltiger API-Key | Happy Path | Korrekter X-API-Key Header | 200 (Weiterleitung) |
| U-AUTH-02 | Fehlender API-Key | Fehlerfall | Kein Header | 401 |
| U-AUTH-03 | Falscher API-Key | Fehlerfall | Falscher Wert | 401 |
| U-AUTH-04 | Leerer API-Key | Grenzwert | `X-API-Key: ""` | 401 |
| U-AUTH-05 | /health ohne Key | Happy Path | Kein Header, /health | 200 (exempt) |

---

### 5.2 Integrationstests

Echte PostgreSQL-Testdatenbank, externe Services gemockt.

#### 5.2.1 Repository-Integration (`test_repository_integration.py`)

| ID | Szenario | Ableitung | Erwartung |
|---|---|---|---|
| I-REP-01 | Migration laeuft fehlerfrei | Happy Path | Alle Tabellen erstellt |
| I-REP-02 | Doppelte Migration ist idempotent | Idempotenz | Kein Fehler bei erneutem Ausfuehren |
| I-REP-03 | Batch-Job CRUD Lifecycle | Happy Path | Create → Read → Update → Verify |
| I-REP-04 | Chunk-Erstellung und Abfrage | Happy Path | Chunks korrekt mit batch_id verknuepft |
| I-REP-05 | image_keywords UPSERT | Edge Case | Insert + Update, nur ein Eintrag |
| I-REP-06 | get_next_unprocessed_image Reihenfolge | Happy Path | Alphabetisch nach image_id |
| I-REP-07 | mark_chunk_image_done Chunk-Completion | Edge Case | Letztes Bild → Chunk auf done |
| I-REP-08 | has_pending_chunks nach Abschluss | Happy Path | `False` wenn alle done |
| I-REP-09 | Concurrent Chunk Access | Edge Case | Zwei parallele Zugriffe | Kein Chunk doppelt vergeben |
| I-REP-10 | FK Constraint batch_images → batch_jobs | Fehlerfall | Orphan Insert → FK-Fehler |

#### 5.2.2 Pipeline-Integration (`test_pipeline_integration.py`)

| ID | Szenario | Ableitung | Erwartung |
|---|---|---|---|
| I-PIP-01 | analyze_single speichert in DB | Happy Path | Keywords in image_keywords-Tabelle |
| I-PIP-02 | Zweiter Aufruf ueberschreibt (UPSERT) | Idempotenz | Neue Keywords ersetzen alte |
| I-PIP-03 | Pipeline mit GPS + Vision | Happy Path | Geo + Vision Keywords kombiniert |
| I-PIP-04 | Pipeline ohne GPS | Aequivalenzklasse | Nur Vision Keywords gespeichert |

#### 5.2.3 Batch-Flow (`test_batch_flow.py`)

| ID | Szenario | Ableitung | Erwartung |
|---|---|---|---|
| I-BAT-01 | Kompletter Batch-Lifecycle | Happy Path | Start → Bilder hochladen → Done |
| I-BAT-02 | Idempotenz bei bereits getaggten Bildern | Idempotenz | Uebersprungen, skipped-Counter |
| I-BAT-03 | Pause und Resume | State Transition | Fortschritt bleibt erhalten |
| I-BAT-04 | Cancel bricht ab | State Transition | Status=cancelled, keine weitere Verarbeitung |
| I-BAT-05 | Fortschritt-Tracking | Happy Path | processed/total stimmt nach jedem Bild |

---

### 5.3 Systemtests

Kompletter FastAPI-Stack via `TestClient`, echte DB, gemockte externe Services.

#### 5.3.1 `POST /api/v1/analyze` (`test_api_analyze.py`)

| ID | Szenario | Ableitung | Erwartung |
|---|---|---|---|
| S-ANL-01 | Bild mit GPS analysieren | Happy Path | 200, keywords + geo_keywords |
| S-ANL-02 | Bild ohne GPS | Aequivalenzklasse | 200, keywords ohne geo |
| S-ANL-03 | Kein Bild im Request | Fehlerfall | 422 (Validation Error) |
| S-ANL-04 | Kaputtes Bild | Fehlerfall | 500 / sinnvolle Fehlermeldung |
| S-ANL-05 | Fehlender API-Key | Fehlerfall | 401 |
| S-ANL-06 | Response-Format korrekt | Happy Path | JSON mit allen Feldern |

#### 5.3.2 `GET /api/v1/health` (`test_api_health.py`)

| ID | Szenario | Ableitung | Erwartung |
|---|---|---|---|
| S-HLT-01 | Alles gesund | Happy Path | 200, status=ok |
| S-HLT-02 | DB nicht erreichbar | Fehlerfall | 200, status=degraded, database=unavailable |
| S-HLT-03 | Ollama nicht erreichbar | Fehlerfall | 200, status=degraded, ollama=unavailable |
| S-HLT-04 | Kein API-Key noetig | Happy Path | 200 ohne X-API-Key Header |

#### 5.3.3 Batch-Endpoints (`test_api_batch.py`)

| ID | Szenario | Ableitung | Erwartung |
|---|---|---|---|
| S-BAT-01 | Batch starten | Happy Path | 200, Job-ID + Status |
| S-BAT-02 | Batch starten ohne Bilder | Fehlerfall | 400 |
| S-BAT-03 | Status abfragen (aktiver Job) | Happy Path | 200, Fortschrittsdaten |
| S-BAT-04 | Status abfragen (kein Job) | Edge Case | 200, status=idle |
| S-BAT-05 | Next Image abrufen | Happy Path | 200, image_id |
| S-BAT-06 | Next Image wenn leer | Edge Case | 200, image_id=null |
| S-BAT-07 | Bild hochladen im Batch | Happy Path | 200, Keywords |
| S-BAT-08 | Pause → Resume Zyklus | State Transition | Status wechselt korrekt |
| S-BAT-09 | Cancel | State Transition | 200, status=cancelled |
| S-BAT-10 | Alle Endpunkte ohne API-Key | Fehlerfall | 401 |

#### 5.3.4 `GET /api/v1/results/{image_id}` (`test_api_results.py`)

| ID | Szenario | Ableitung | Erwartung |
|---|---|---|---|
| S-RES-01 | Existierendes Bild | Happy Path | 200, Keywords |
| S-RES-02 | Nicht existierendes Bild | Fehlerfall | 404 |
| S-RES-03 | Ohne API-Key | Fehlerfall | 401 |

---

### 5.4 NFA-Tests: Performance (`test_performance.py`)

| ID | Szenario | Messung | Zielwert |
|---|---|---|---|
| P-THR-01 | Einzelbild-Analyse Latenz | Response Time POST /analyze | < 30s (abhaengig von Ollama-Mock) |
| P-THR-02 | Health-Endpoint Latenz | Response Time GET /health | < 200ms |
| P-THR-03 | Batch-Start Latenz (1000 Bilder) | Response Time POST /batch/start | < 5s |
| P-THR-04 | Batch-Status Latenz | Response Time GET /batch/status | < 100ms |
| P-THR-05 | Ollama-Semaphore unter Last | Gleichzeitige Requests | Max. `OLLAMA_MAX_CONCURRENT` parallel |
| P-THR-06 | Geocoder-Throttle | Request-Rate | Max. 1 req/s |
| P-THR-07 | DB Connection Pool unter Last | 20 parallele Requests | Keine Connection-Fehler |
| P-MEM-01 | Speicherverbrauch Bildverarbeitung | Memory nach 100 Bildern | Kein Memory Leak (stabil) |

**Durchfuehrung:**
- Ollama-Mock mit konfigurierbarer Latenz (default: 100ms statt echte 6-12s)
- `pytest-benchmark` fuer Latenz-Messungen
- Manuelle Last-Tests mit `locust` oder `hey` gegen gestarteten Server (optional)

### 5.5 NFA-Tests: Security (`test_security.py`)

| ID | Szenario | Ableitung | Erwartung |
|---|---|---|---|
| SEC-01 | API-Key in URL-Parameter ignoriert | Fehlerfall | 401 (nur Header akzeptiert) |
| SEC-02 | Timing-sicherer API-Key-Vergleich | Security | Konstante Vergleichszeit (hmac.compare_digest) |
| SEC-03 | Path Traversal in image_id | Injection | `../../etc/passwd` → kein Dateizugriff |
| SEC-04 | SQL-Injection in image_id | Injection | `'; DROP TABLE--` → kein Effekt (parametrisierte Queries) |
| SEC-05 | Uebergrosse Datei-Upload | DoS | 100MB Upload → 413 oder sinnvolles Limit |
| SEC-06 | Zip-Bomb als Bild | DoS | Komprimierte Datei → Fehler, kein OOM |
| SEC-07 | Content-Type Mismatch | Edge Case | .jpg Extension aber kein Bild-Content | Sinnvoller Fehler |
| SEC-08 | API-Key nicht in Logs | Security | Logger-Output enthaelt keinen Key |
| SEC-09 | CORS-Header korrekt | Security | Kein `Access-Control-Allow-Origin: *` |
| SEC-10 | Error-Responses leaken keine Internals | Security | Kein Stacktrace in 500-Responses |

---

### 5.6 UAT (User Acceptance Tests)

Manuell durchgefuehrt mit echtem Lightroom-Plugin gegen echten Backend-Service.

| ID | Szenario | Vorbedingung | Schritte | Erwartung |
|---|---|---|---|---|
| UAT-01 | Einzelbild mit GPS | Bild mit GPS in LR selektiert | Auto-Tag klicken | Deutsche Keywords + Ort in LR |
| UAT-02 | Einzelbild ohne GPS | Bild ohne GPS selektiert | Auto-Tag klicken | Deutsche Keywords ohne Ort |
| UAT-03 | Mehrere Bilder interaktiv | 5 Bilder selektiert | Auto-Tag klicken | Alle 5 mit Keywords versehen |
| UAT-04 | Batch-Start | Bibliothek mit 100 Bildern | Batch starten | Fortschrittsanzeige laeuft |
| UAT-05 | Batch-Pause/Resume | Laufender Batch | Pause → warten → Resume | Fortschritt pausiert und setzt fort |
| UAT-06 | Batch-Cancel | Laufender Batch | Cancel klicken | Batch stoppt, bisherige Keywords bleiben |
| UAT-07 | Idempotenz | Bereits getaggte Bibliothek | Batch erneut starten | Alle uebersprungen |
| UAT-08 | Keyword-Qualitaet | 20 diverse Testbilder | Manuell pruefen | >80% der Keywords sachlich korrekt |
| UAT-09 | Server-Neustart | Laufender Batch, Server restart | Server neu starten | Batch wird fortgesetzt |
| UAT-10 | Ollama nicht verfuegbar | Ollama gestoppt | Bild analysieren | Sinnvolle Fehlermeldung in LR |

---

## 6. Test-Fixtures & Hilfsmittel

### 6.1 Gemeinsame Fixtures (`conftest.py`)

```python
# Test-Bilder
@pytest.fixture
def sample_jpeg() -> bytes: ...          # 800x600 RGB JPEG

@pytest.fixture
def sample_large_jpeg() -> bytes: ...    # 2048x1536 JPEG

@pytest.fixture
def sample_rgba_png() -> bytes: ...      # 800x600 RGBA PNG

@pytest.fixture
def corrupt_image() -> bytes: ...        # Zufaellige Bytes

# Mocks
@pytest.fixture
def mock_ollama_response() -> list[str]: ...   # Standard-Keywords

@pytest.fixture
def mock_nominatim_response() -> dict: ...     # Heidelberg

# DB (Integration/System)
@pytest.fixture
async def test_db() -> Repository: ...         # Echte Test-DB, Schema migriert

# FastAPI (System)
@pytest.fixture
def client(test_db) -> TestClient: ...         # FastAPI TestClient mit Mocks
```

### 6.2 Test-DB Konvention

- Datenbank: `lr_autotag_test` (separater Name, nie Produktions-DB)
- Wird vor jedem Testlauf per `CREATE`/`DROP` neu erstellt
- Alternativ: Transaction-Rollback pro Test (schneller)
- Konfiguration via `TEST_DATABASE_URL` Umgebungsvariable

---

## 7. CI-Integration

```yaml
# pytest Aufruf
pytest tests/unit/                    # Stufe 1 — immer, schnell
pytest tests/integration/             # Stufe 2 — bei DB verfuegbar
pytest tests/system/                  # Stufe 3 — bei DB verfuegbar
pytest tests/nfa/                     # Stufe 3b — separat, laenger

# Coverage
pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80

# Ruff
ruff check backend/app/
```

### 7.1 Test-Marker

```python
@pytest.mark.unit          # Laeuft immer, keine externe Abhaengigkeit
@pytest.mark.integration   # Braucht PostgreSQL
@pytest.mark.system        # Braucht PostgreSQL + FastAPI TestClient
@pytest.mark.performance   # Benchmark-Tests, laenger
@pytest.mark.security      # Security-spezifische Tests
@pytest.mark.slow          # Tests > 5s
```

---

## 8. Priorisierung

| Prioritaet | Tests | Begruendung |
|---|---|---|
| P0 | Unit: Ollama-Client Parse-Logik | Kernfunktion, fehlerhafte Antworten wahrscheinlich |
| P0 | Unit: Keyword-Pipeline Kombination | Geschaeftslogik |
| P0 | Unit: API-Key Auth | Sicherheitskritisch |
| P1 | Unit: Image Processor | Robustheit bei diversen Formaten |
| P1 | Integration: Repository CRUD | Datenkorrektheit |
| P1 | System: POST /analyze Happy Path | End-to-End Validierung |
| P2 | Integration: Batch-Flow | Komplexer Lifecycle |
| P2 | System: Batch-Endpoints | API-Vertrag |
| P2 | NFA: Security | Injection, DoS |
| P3 | NFA: Performance | Durchsatz, Memory |
| P3 | Unit: Geocoder | Externer Service, einfache Logik |
