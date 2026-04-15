# LR-AutoTag — Architektur & Projektplan

## Summary

LR-AutoTag ist ein Lightroom Classic Plugin mit zugehörigem Backend-Service, das eine Fotobibliothek mit 100.000+ Bildern automatisch verschlagwortet. Die Analyse erfolgt über ein lokal betriebenes Vision-Modell (LLaVA auf Ollama/Nvidia P40) und ergänzt GPS-basierte Ortsinformationen per Reverse Geocoding. Das System unterstützt sowohl interaktive Verschlagwortung ausgewählter Bilder als auch einen autonomen Batch-Modus, der die gesamte Bibliothek im Hintergrund verarbeitet.

---

## 1. Systemkontext

**Akteure:**
- Fotograf (Lightroom Classic User)
- Lightroom Classic (Host-Applikation für das Plugin)
- Bestehender Ollama-Server (Shared Service, bereits durch andere App genutzt)
- PostgreSQL-Datenbank (bestehend auf dem Server)

**Rahmenbedingungen:**
- ca. 100.000+ Bilder, Mischung aus RAW und JPEG
- GPS-Daten nur teilweise vorhanden
- Keywords auf Deutsch, eher technisch/sachlich
- Server mit Nvidia P40 (24 GB VRAM), Debian VMs, Ollama bereits im Einsatz
- PostgreSQL bereits verfügbar
- Ollama wird als Shared Service betrieben (Priorisierung/Rate-Limiting nötig)

---

## 2. Komponentenarchitektur

```
┌─────────────────────────────────────────────┐
│           Lightroom Classic                  │
│  ┌───────────────────────────────────────┐  │
│  │         LR-AutoTag Plugin (Lua)       │  │
│  │  ┌─────────────┐  ┌────────────────┐  │  │
│  │  │ Interaktiver │  │  Batch-Modus   │  │  │
│  │  │    Modus     │  │  (Trigger +    │  │  │
│  │  │              │  │   Status)      │  │  │
│  │  └──────┬───────┘  └───────┬────────┘  │  │
│  └─────────┼──────────────────┼───────────┘  │
│            │                  │               │
└────────────┼──────────────────┼───────────────┘
             │ REST API         │ REST API
             ▼                  ▼
┌─────────────────────────────────────────────┐
│     Backend-Service (Python / FastAPI)       │
│           Debian VM auf Server               │
│                                              │
│  ┌──────────────┐  ┌─────────────────────┐  │
│  │   REST API   │  │    Job-Manager      │  │
│  │  (Plugin-    │  │  (Chunk-Verwaltung, │  │
│  │   Komm.)     │  │   Retry, Checkpoint)│  │
│  └──────┬───────┘  └──────────┬──────────┘  │
│         │                     │              │
│  ┌──────┴─────────────────────┴──────────┐  │
│  │         Keyword-Pipeline              │  │
│  │  ┌────────────┐  ┌─────────────────┐  │  │
│  │  │  Reverse   │  │  Vision-Analyse │  │  │
│  │  │  Geocoder  │  │  (Ollama-Client)│  │  │
│  │  └────────────┘  └────────┬────────┘  │  │
│  │  ┌────────────────────────┴────────┐  │  │
│  │  │  Keyword-Kombinator & Formatter │  │  │
│  │  └─────────────────────────────────┘  │  │
│  └───────────────────────────────────────┘  │
│                                              │
└───────────────┬──────────────────────────────┘
                │
        ┌───────┴───────┐
        ▼               ▼
┌──────────────┐  ┌──────────────┐
│   Ollama     │  │  PostgreSQL  │
│  (LLaVA 13B)│  │  (Job-Queue, │
│  Shared Svc  │  │   Ergebnisse)│
│  Nvidia P40  │  │              │
└──────────────┘  └──────────────┘
```

---

## 3. Komponenten im Detail

### 3.1 Lightroom Classic Plugin (Lua)

**Verantwortung:** UI-Integration, Bildexport, Keyword-Rückschreibung in den LR-Katalog.

**Interaktiver Modus:**
- User wählt Bilder in Lightroom aus
- Klickt "Auto-Verschlagworten"
- Plugin exportiert JPG-Vorschaubilder (max. 1024px lange Seite)
- Liest GPS-Koordinaten und vorhandene Metadaten aus dem LR-Katalog
- Schickt Bild + Metadaten per REST an den Backend-Service
- Empfängt Keywords und schreibt sie über die LR SDK API in den Katalog

**Batch-Modus:**
- "Gesamte Bibliothek verschlagworten" — einmal anstoßen
- Plugin sendet Kataloginhalt (Bild-IDs, Pfade, vorhandene Metadaten) ans Backend
- Backend übernimmt die Steuerung (Chunks, Queue, Retry)
- Plugin zeigt Fortschritt an: Anzahl bearbeitet / gesamt, geschätzte Restdauer
- Pause / Resume / Abbruch über Plugin-UI
- Bilder, die bereits verschlagwortet sind, werden übersprungen (Idempotenz)

**Technologie:** Lua (Lightroom SDK), HTTP-Client für REST-Kommunikation.

### 3.2 Backend-Service (Python / FastAPI)

**Verantwortung:** Bildanalyse orchestrieren, Job-Management, Keyword-Generierung.

**REST API Endpunkte:**

| Endpunkt | Methode | Beschreibung |
|---|---|---|
| `/api/v1/analyze` | POST | Einzelbild analysieren (interaktiver Modus) |
| `/api/v1/batch/start` | POST | Batch-Job für Bibliothek starten |
| `/api/v1/batch/status` | GET | Fortschritt des laufenden Batch-Jobs |
| `/api/v1/batch/pause` | POST | Batch pausieren |
| `/api/v1/batch/resume` | POST | Batch fortsetzen |
| `/api/v1/batch/cancel` | POST | Batch abbrechen |
| `/api/v1/results/{image_id}` | GET | Keywords für ein bestimmtes Bild abrufen |
| `/api/v1/health` | GET | Service-Health inkl. Ollama-Verfügbarkeit |

**Job-Manager:**
- Teilt Bibliothek in Chunks à 50 Bilder
- Persistiert Job-Status in PostgreSQL
- Chunk-Status: `pending` → `processing` → `done` | `failed`
- Automatischer Retry bei Fehlschlag (max. 3 Versuche)
- Checkpoint nach jedem Chunk — überlebt Neustarts
- Ollama-Timeout-Handling: bei Nicht-Antwort → Chunk zurück in Queue
- Rate-Limiting: konfigurierbare maximale Parallelität, damit Ollama-Shared-Service nicht überlastet wird

**Keyword-Pipeline:**

1. **Vorverarbeitung:** Bild auf Analyse-Größe skalieren, EXIF-Daten extrahieren
2. **Reverse Geocoding:** GPS-Koordinaten → Ort, Stadt, Bundesland, Land (via Nominatim/OpenStreetMap)
3. **Vision-Analyse:** Bild an Ollama/LLaVA senden mit strukturiertem Prompt:
   ```
   Analysiere dieses Foto und gib deutsche Schlagworte zurück.
   Kategorien: Objekte, Szene, Umgebung, Tageszeit, Jahreszeit, Wetter.
   Format: JSON-Array mit maximal 25 Keywords.
   Nur sachliche/technische Begriffe, keine Stimmungsbeschreibungen.
   ```
4. **Keyword-Kombinator:** Vision-Keywords + Geo-Keywords zusammenführen, Duplikate entfernen, normalisieren
5. **Ergebnis:** Strukturierte Keyword-Liste zurück an Plugin

**Technologie:** Python 3.12, FastAPI, asyncio, httpx (Ollama-Client), psycopg (PostgreSQL), Pillow (Bildverarbeitung).

### 3.3 Ollama Shared Service

**Verantwortung:** Vision-Modell bereitstellen für Bildanalyse.

**Modell:** LLaVA 13B (oder LLaVA-Next, je nach Qualitätstests). Passt in 24 GB VRAM der P40.

**Shared-Service-Konzept:**
- Ollama läuft als zentraler Daemon, erreichbar über HTTP API
- Beide Clients (bestehende App + LR-AutoTag Backend) nutzen denselben Endpunkt
- Ollama queued Requests intern — kein externer Load Balancer nötig
- LR-AutoTag Backend implementiert eigenes Rate-Limiting (z.B. max. 2 parallele Requests), um die bestehende App nicht zu blockieren
- Konfigurierbar: Tageszeit-basierte Priorisierung möglich (nachts höherer Durchsatz)

### 3.4 PostgreSQL

**Verantwortung:** Job-Persistenz, Ergebnis-Speicherung, Audit-Log.

**Tabellen (Entwurf):**

```sql
-- Batch-Jobs
CREATE TABLE batch_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending, running, paused, done, cancelled
    total_images  INTEGER NOT NULL,
    processed     INTEGER NOT NULL DEFAULT 0,
    failed        INTEGER NOT NULL DEFAULT 0,
    skipped       INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Chunks innerhalb eines Batch-Jobs
CREATE TABLE chunks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id      UUID NOT NULL REFERENCES batch_jobs(id),
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending, processing, done, failed
    image_ids     TEXT[] NOT NULL,
    attempt       INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ
);

-- Ergebnisse pro Bild
CREATE TABLE image_keywords (
    image_id      TEXT PRIMARY KEY,  -- Lightroom-interne Bild-ID oder Dateipfad
    keywords      TEXT[] NOT NULL,
    geo_keywords  TEXT[],
    vision_keywords TEXT[],
    gps_lat       DOUBLE PRECISION,
    gps_lon       DOUBLE PRECISION,
    location_name TEXT,
    model_used    TEXT NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 4. Datenfluss

### 4.1 Interaktiver Modus

```
User wählt Bilder in LR
        │
        ▼
Plugin exportiert JPG-Previews (1024px)
        │
        ▼
POST /api/v1/analyze  (Bild + GPS + Metadaten)
        │
        ▼
Backend: Reverse Geocoding (falls GPS vorhanden)
        │
        ▼
Backend: Bild → Ollama LLaVA → Vision-Keywords
        │
        ▼
Backend: Keywords kombinieren + normalisieren
        │
        ▼
Response: { keywords: ["Brücke", "Fluss", "Heidelberg", ...] }
        │
        ▼
Plugin schreibt Keywords in LR-Katalog
```

### 4.2 Batch-Modus

```
User klickt "Bibliothek verschlagworten"
        │
        ▼
Plugin sendet Katalog-Metadaten ans Backend
        │
        ▼
Backend: Filtert bereits getaggte Bilder (Idempotenz)
        │
        ▼
Backend: Erstellt Batch-Job + Chunks in PostgreSQL
        │
        ▼
┌─────────────────────────────────────┐
│  Job-Manager Loop (asynchron):      │
│                                      │
│  1. Nächsten pending Chunk holen     │
│  2. Bilder vom LR-Katalog lesen     │
│  3. Für jedes Bild:                  │
│     a) JPG-Preview erzeugen          │
│     b) GPS → Reverse Geocoding       │
│     c) Bild → Ollama → Keywords      │
│     d) Ergebnis in PostgreSQL         │
│  4. Chunk als done/failed markieren   │
│  5. Bei Fehler: Retry (max 3x)       │
│  6. Checkpoint in DB                  │
│                                      │
│  Wiederholen bis alle Chunks done     │
└─────────────────────────────────────┘
        │
        ▼
Plugin pollt /batch/status → zeigt Fortschritt
        │
        ▼
Plugin holt Ergebnisse und schreibt Keywords in LR-Katalog
```

---

## 5. Deployment

```
┌─────────────────────────────────────────────────────┐
│  Fotografen-Rechner                                  │
│  ┌─────────────────────────────────────────────┐    │
│  │  Lightroom Classic + LR-AutoTag Plugin       │    │
│  └─────────────────────────────────────────────┘    │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP (LAN)
                       ▼
┌─────────────────────────────────────────────────────┐
│  Server (bestehend)                                  │
│                                                      │
│  ┌──────────────────────┐  ┌──────────────────────┐ │
│  │  Debian VM (neu)      │  │  Bestehende Infra    │ │
│  │  ┌────────────────┐  │  │  ┌────────────────┐  │ │
│  │  │ LR-AutoTag     │  │  │  │ PostgreSQL     │  │ │
│  │  │ Backend        │  │  │  │ (bestehend)    │  │ │
│  │  │ (FastAPI)      │  │  │  └────────────────┘  │ │
│  │  └────────┬───────┘  │  │  ┌────────────────┐  │ │
│  │           │           │  │  │ Ollama         │  │ │
│  │           │           │  │  │ (Shared, P40)  │  │ │
│  │           │           │  │  └────────────────┘  │ │
│  └───────────┼───────────┘  └──────────────────────┘ │
│              │ HTTP                                    │
│              └──────────► Ollama + PostgreSQL          │
└─────────────────────────────────────────────────────┘
```

---

## 6. Nichtfunktionale Anforderungen

| Anforderung | Zielwert | Begründung |
|---|---|---|
| Durchsatz | 5-10 Bilder/Minute | Limitiert durch LLaVA-Inferenzzeit auf P40 |
| Verfügbarkeit | Best-Effort | Hobby-Projekt, kein SLA nötig |
| Datenverlust | Null | Checkpoint nach jedem Chunk in PostgreSQL |
| Ollama-Koexistenz | Max. 2 parallele Requests | Bestehende App darf nicht blockiert werden |
| Keyword-Qualität | Sachlich, deutsch, relevant | Keine Halluzinationen, lieber weniger als falsche Keywords |
| Idempotenz | Bereits getaggte Bilder überspringen | Mehrfach-Starts dürfen keine Duplikate erzeugen |
| Neustart-Resilienz | Automatisch fortsetzen | Nach Server/Service-Neustart weiter bei letztem Checkpoint |

---

## 7. Backlog

### Sprint 1: Fundament

| ID | Anforderung | Akzeptanzkriterien |
|---|---|---|
| T-001 | Debian VM aufsetzen mit Python, FastAPI | Service startet, `/health` antwortet |
| T-002 | PostgreSQL Schema anlegen | Tabellen erstellt, Migrations-Skript vorhanden |
| T-003 | Ollama-Client implementieren | Bild an LLaVA senden, Keywords als JSON zurückbekommen |
| T-004 | Reverse Geocoder implementieren | GPS-Koordinaten → Ortsname (deutsch) |
| T-005 | Keyword-Pipeline (einzelnes Bild) | Bild rein → deutsche Keywords raus, via REST API testbar |

### Sprint 2: Batch-Modus

| ID | Anforderung | Akzeptanzkriterien |
|---|---|---|
| T-006 | Job-Manager mit Chunk-Verwaltung | Batch starten, Chunks werden erstellt und abgearbeitet |
| T-007 | Retry-Logik | Fehlgeschlagene Chunks werden max. 3x wiederholt |
| T-008 | Checkpoint / Neustart-Resilienz | Service-Neustart → Verarbeitung wird fortgesetzt |
| T-009 | Rate-Limiting für Ollama | Max. konfigurierbare Parallelität, bestehende App nicht blockiert |
| T-010 | Fortschritts-API | `/batch/status` liefert processed/total/estimated_remaining |

### Sprint 3: Lightroom Plugin

| ID | Anforderung | Akzeptanzkriterien |
|---|---|---|
| T-011 | LR Plugin Grundgerüst (Lua) | Plugin erscheint in LR, Menüeintrag vorhanden |
| T-012 | Interaktiver Modus | Bilder auswählen → Keywords werden in LR eingetragen |
| T-013 | Batch-Modus Trigger | "Bibliothek verschlagworten" startet Batch im Backend |
| T-014 | Fortschrittsanzeige | Plugin zeigt Batch-Fortschritt in LR an |
| T-015 | Pause / Resume / Abbruch | Batch-Steuerung über Plugin-UI |

### Sprint 4: Qualität & Feinschliff

| ID | Anforderung | Akzeptanzkriterien |
|---|---|---|
| T-016 | Keyword-Qualität evaluieren | 100 Testbilder manuell geprüft, >80% der Keywords relevant |
| T-017 | Prompt-Tuning | Optimierter LLaVA-Prompt für deutsche, sachliche Keywords |
| T-018 | Duplikat-Erkennung | Keine doppelten Keywords pro Bild, Synonyme zusammengeführt |
| T-019 | Fehlerbehandlung End-to-End | Ollama down, DB down, LR geschlossen — alles getestet |
| T-020 | Dokumentation | Installationsanleitung, Admin-Handbuch, User-Guide |

> **Hinweis:** Die operativen Folge-Aufgaben (Hardware-Upgrade, erweiterter Modellbenchmark inkl. LLaVA 34B, Gemma 4 26B A4B, InternVL2 26B) werden im lebenden Backlog unter `docs/backlog.md` gepflegt.

---

## 8. Technologie-Stack

| Komponente | Technologie | Begründung |
|---|---|---|
| LR Plugin | Lua (Lightroom SDK) | Einzige Option für native LR-Integration |
| Backend | Python 3.12 + FastAPI | Async-fähig, gutes Ökosystem für ML/Bild |
| Task Queue | Eigene Implementierung auf PostgreSQL | Kein Redis nötig, PostgreSQL reicht für das Volumen |
| Datenbank | PostgreSQL (bestehend) | Bereits vorhanden, robust, ACID |
| Vision-Modell | LLaVA 13B via Ollama | Lokal, kostenlos, 24GB VRAM reicht |
| Reverse Geocoding | Nominatim (OSM) oder lokale DB | Kostenlos, datenschutzfreundlich |
| Bildverarbeitung | Pillow | Resize für Vorschaubilder |
| HTTP Client | httpx | Async-Support für Ollama-Calls |

---

## 9. Risiken

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|---|---|---|---|
| LLaVA-Qualität unzureichend für deutsche Keywords | Mittel | Hoch | Prompt-Tuning, ggf. Wechsel auf besseres Modell, Claude als Fallback |
| Ollama-Shared-Service wird überlastet | Mittel | Mittel | Rate-Limiting, Tageszeit-Steuerung |
| LR Plugin API-Einschränkungen | Niedrig | Hoch | Frühzeitig LR SDK Capabilities prüfen (Sprint 3 vorgezogen) |
| 100k Bilder Batch dauert zu lange | Niedrig | Niedrig | Parallelität erhöhen, oder kleinere Vision-Modelle testen |
| P40 thermisch instabil (Sprint 5 blockiert) | Hoch | Mittel | Kühlung/Gehäuselüftung optimieren, ggf. Austausch; Sprint 5 nicht ohne stabile GPU starten |
| InternVL2 26B nicht in Ollama-Library, nur Community-GGUF | Mittel | Niedrig | Verfügbarkeit prüfen, ggf. eigenes Modelfile bauen oder Modell aus Benchmark streichen |
| VM-RAM (14,5 GB) reicht nicht für 26B+-Modelle (insb. MoE) | Hoch | Mittel | Aufrüstung auf ≥32 GB als harte Vorbedingung für erweiterten Modellbenchmark |

---

## Fazit

Das System nutzt die bestehende Infrastruktur (Server, P40, PostgreSQL, Ollama) maximal aus. Die Kernherausforderung liegt in der Keyword-Qualität des lokalen Vision-Modells und der robusten Batch-Verarbeitung. Der Hybrid-Ansatz (lokal für Masse, optional Claude für Qualität) bietet Flexibilität. Die geschätzte Entwicklungszeit liegt bei 4-6 Sprints, wobei Sprint 1 und 2 unabhängig vom LR-Plugin entwickelt und getestet werden können.
