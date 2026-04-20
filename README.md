# LR-AutoTag

Automatische Verschlagwortung fuer Adobe Lightroom Classic. Ein Lightroom-Plugin sendet Vorschaubilder an einen Backend-Service, der mittels KI-Bildanalyse (LLaVA auf Ollama) und GPS-basiertem Reverse Geocoding deutsche Schlagworte generiert und in den Katalog zurueckschreibt.

## Features

- **Interaktiver Modus** — Ausgewaehlte Bilder direkt verschlagworten
- **Batch-Modus** — Gesamte Bibliothek automatisch verarbeiten (Pause/Resume/Abbruch)
- **Vision-Analyse** — LLaVA 13B erkennt Objekte, Szene, Umgebung, Tageszeit, Jahreszeit, Wetter, Stimmung
- **Reverse Geocoding** — GPS-Koordinaten werden zu Orts-Keywords aufgeloest (Nominatim/OSM)
- **Idempotent** — Bereits verschlagwortete Bilder werden uebersprungen
- **Checkpoint-basiert** — Ueberlebt Neustarts, setzt beim letzten Chunk fort

## Architektur

```
Lightroom Classic + Plugin (Lua)
        │  REST API (HTTP/LAN)
        ▼
Backend-Service (Python/FastAPI)
        │              │
        ▼              ▼
  Ollama/LLaVA    PostgreSQL
  (Nvidia GPU)    (Jobs, Ergebnisse)
```

## Voraussetzungen

| Komponente | Anforderung |
|---|---|
| GPU-Server | Nvidia GPU mit >= 24 GB VRAM (z.B. P40, A5000) |
| Ollama | Installiert, `llava:13b` Modell geladen |
| Backend-Server | Debian/Ubuntu, Python >= 3.12, PostgreSQL 14+ |
| Lightroom | Adobe Lightroom Classic v12+ |
| Netzwerk | LAN-Verbindung zwischen Fotograf und Server |

## Schnellstart

### 1. Ollama vorbereiten (GPU-Server)

```bash
# Ollama installieren (https://ollama.com)
curl -fsSL https://ollama.com/install.sh | sh

# Vision-Modell laden (~8 GB Download)
ollama pull llava:13b

# Pruefen, ob es laeuft
curl http://localhost:11434/api/tags
```

### 2. Backend installieren

```bash
git clone https://github.com/maximilian-stoerzer/LR-AutoTagger.git
cd LR-AutoTagger/backend

python3.12 -m venv .venv
.venv/bin/pip install -e .

# PostgreSQL-Datenbank anlegen
createuser lr_autotag
createdb -O lr_autotag lr_autotag
psql lr_autotag -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

# Konfiguration
cp ../.env.example .env
# .env editieren: DATABASE_URL, OLLAMA_BASE_URL, API_KEY setzen

# Starten
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3. Lightroom-Plugin installieren

1. `plugin/LR-AutoTag.lrplugin` in einen lokalen Ordner kopieren (oder ZIP aus Release entpacken)
2. Lightroom: **Datei → Plug-in-Manager → Hinzufuegen**
3. Den Ordner `LR-AutoTag.lrplugin` auswaehlen
4. Plugin-Einstellungen: Backend-URL und API-Key eintragen
5. **"Verbindung testen"** klicken

### 4. Verschlagworten

- **Einzelne Bilder:** Bilder auswaehlen → Bibliothek → Plug-in-Extras → *Ausgewaehlte verschlagworten*
- **Ganze Bibliothek:** Bibliothek → Plug-in-Extras → *Bibliothek verschlagworten*

## Release-Artefakte bauen

```bash
make all
# -> release/backend/lr-autotag-backend-0.1.0.tar.gz
# -> release/plugin/lr-autotag-plugin-0.1.0.zip
```

Deployment auf dem Server:
```bash
scp release/backend/*.tar.gz server:/tmp/
ssh server 'cd /tmp && tar xzf lr-autotag-backend-*.tar.gz && sudo bash install.sh'
```

## Dokumentation

| Dokument | Inhalt |
|---|---|
| [docs/installation.md](docs/installation.md) | Detaillierte Installation & Troubleshooting |
| [docs/admin.md](docs/admin.md) | Administration, Konfiguration, Betrieb |
| [docs/user-guide.md](docs/user-guide.md) | Benutzerhandbuch fuer Fotografen |
| [docs/tech.md](docs/tech.md) | Technische Architektur, ADRs, Datenmodell |

## Technologie-Stack

| Komponente | Technologie |
|---|---|
| LR Plugin | Lua (Lightroom SDK) |
| Backend | Python 3.12, FastAPI, uvicorn |
| Datenbank | PostgreSQL |
| Vision-Modell | LLaVA 13B via Ollama |
| Reverse Geocoding | Nominatim (OpenStreetMap) |
| HTTP Client | httpx (async) |
| Bildverarbeitung | Pillow |

## Lizenz

Privates Projekt.
