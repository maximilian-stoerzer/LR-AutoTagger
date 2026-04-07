# Installation & Troubleshooting

Diese Anleitung beschreibt, wie das LR-AutoTag Backend und das Lightroom Plugin
installiert und konfiguriert werden.

> **Status:** Das Backend ist implementiert (Sprint 1+2). Das Lightroom Plugin
> ist noch nicht implementiert (Sprint 3) — die Plugin-Abschnitte beschreiben
> den geplanten Installationsweg.

---

## 1. Voraussetzungen

### Server (Backend)
- Debian/Ubuntu VM oder Linux-Server
- Python 3.12 oder neuer
- PostgreSQL 14+ (Erweiterung `pgcrypto` muss verfügbar sein)
- Netzwerkzugriff zum Ollama-Daemon (Port 11434)
- Internetzugang fuer Nominatim-Reverse-Geocoding (oder eigene Instanz)

### GPU-Server (Ollama, ggf. separat)
- Nvidia GPU mit ≥ 24 GB VRAM (z.B. P40)
- Ollama installiert und laufend
- Modell `llava:13b` per `ollama pull llava:13b` heruntergeladen

### Fotografen-Rechner (Plugin)
- Adobe Lightroom Classic (Version 12 oder neuer)
- Netzwerkverbindung zum Backend-Server (LAN)

---

## 2. Backend-Installation

### 2.1 Quellcode klonen
```bash
git clone https://github.com/maximilian-stoerzer/LR-AutoTagger.git
cd LR-AutoTagger/backend
```

### 2.2 Python venv anlegen
```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
```

### 2.3 PostgreSQL-Datenbank anlegen
```bash
# Als Postgres-Superuser:
createuser lr_autotag
createdb -O lr_autotag lr_autotag
psql lr_autotag -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
```

> Passwort fuer den User setzen: `psql -c "ALTER USER lr_autotag WITH PASSWORD '...';"`

### 2.4 Konfiguration (`.env`)
Im Repository-Root liegt `.env.example`. Datei nach `backend/.env` kopieren
und Werte eintragen:

```bash
cp ../.env.example backend/.env
```

Pflichtfelder:

| Variable | Beispiel | Beschreibung |
|---|---|---|
| `DATABASE_URL` | `postgresql://lr_autotag:secret@localhost:5432/lr_autotag` | PostgreSQL-Verbindungsstring |
| `OLLAMA_BASE_URL` | `http://192.168.1.10:11434` | Endpunkt des Ollama-Servers |
| `OLLAMA_MODEL` | `llava:13b` | Vision-Modell-Name (muss in Ollama vorhanden sein) |
| `API_KEY` | `<32-byte random>` | API-Key, den der Plugin senden muss |

Optionale Felder mit sinnvollen Defaults:

| Variable | Default | Beschreibung |
|---|---|---|
| `OLLAMA_MAX_CONCURRENT` | `2` | Max. parallele Ollama-Requests (Shared-Service-Schutz) |
| `OLLAMA_TIMEOUT` | `120` | Timeout in Sekunden fuer einen Vision-Request |
| `IMAGE_MAX_SIDE` | `1024` | Bilder werden auf diese maximale lange Seite skaliert |
| `BATCH_CHUNK_SIZE` | `50` | Anzahl Bilder pro Chunk im Batch-Modus |
| `MAX_KEYWORDS` | `25` | Max. Keywords pro Bild |
| `MAX_RETRY_ATTEMPTS` | `3` | Retry-Versuche pro fehlgeschlagenem Chunk |
| `NOMINATIM_URL` | `https://nominatim.openstreetmap.org` | Reverse-Geocoder-Endpunkt |
| `NOMINATIM_USER_AGENT` | `lr-autotag/1.0` | Pflicht laut Nominatim-Nutzungsbedingungen |

API-Key generieren:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2.5 Schema-Migration
Migrationen laufen automatisch beim Start. Manuell pruefen:
```bash
psql $DATABASE_URL -f migrations/001_initial.sql
```

### 2.6 Backend starten
```bash
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health-Check:
```bash
curl http://localhost:8000/api/v1/health
# {"status":"ok","database":"ok","ollama":"ok"}
```

### 2.7 systemd-Service (optional, fuer Produktion)
Datei `/etc/systemd/system/lr-autotag.service`:
```ini
[Unit]
Description=LR-AutoTag Backend
After=network.target postgresql.service

[Service]
Type=simple
User=lr_autotag
WorkingDirectory=/opt/lr-autotag/backend
EnvironmentFile=/opt/lr-autotag/backend/.env
ExecStart=/opt/lr-autotag/backend/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now lr-autotag
systemctl status lr-autotag
```

---

## 3. Plugin-Installation (geplant)

> **Hinweis:** Die folgenden Schritte sind die geplante Installation, sobald
> das Lua-Plugin in Sprint 3 fertig ist.

1. `plugin/LR-AutoTag.lrplugin` aus dem Repository kopieren
2. In Lightroom: **Datei → Plug-in-Manager... → Hinzufuegen**
3. Den Ordner `LR-AutoTag.lrplugin` auswaehlen
4. Plugin-Einstellungen oeffnen, Backend-URL und API-Key eintragen
   (siehe `docs/admin.md`)

---

## 4. Troubleshooting

### 4.1 Backend startet nicht

| Symptom | Mögliche Ursache | Lösung |
|---|---|---|
| `connection refused` zur DB | PostgreSQL läuft nicht | `systemctl status postgresql`, ggf. starten |
| `role "lr_autotag" does not exist` | DB-User nicht angelegt | `createuser lr_autotag` |
| `permission denied for schema public` | Rechte fehlen | `GRANT ALL ON SCHEMA public TO lr_autotag;` |
| `function gen_random_uuid() does not exist` | Extension fehlt | `CREATE EXTENSION pgcrypto;` |
| `Address already in use` | Port 8000 belegt | Anderen Port via `--port 8001` oder Prozess beenden |

### 4.2 `/health` zeigt `ollama: unavailable`

1. Ist `OLLAMA_BASE_URL` korrekt?
2. Erreicht der Backend-Server den Ollama-Daemon?
   ```bash
   curl http://<ollama-host>:11434/api/tags
   ```
3. Läuft Ollama? `systemctl status ollama` (auf dem Ollama-Server)
4. Ist Port 11434 in der Firewall offen?

### 4.3 `/health` zeigt `database: unavailable`

1. `DATABASE_URL` korrekt?
2. PostgreSQL erreichbar?
   ```bash
   psql "$DATABASE_URL" -c 'SELECT 1'
   ```
3. Connection-Pool erschöpft? Backend-Logs nach `pool` durchsuchen

### 4.4 Bildanalyse schlägt fehl mit `httpx.TimeoutException`

- Ollama braucht für LLaVA-13B ca. 6–12 s pro Bild
- Standard-Timeout ist 120 s — bei Bildern, die länger brauchen, `OLLAMA_TIMEOUT` erhöhen
- Mehrfaches Timeout deutet auf Ollama-Überlast → `OLLAMA_MAX_CONCURRENT` reduzieren

### 4.5 Reverse Geocoding liefert immer `None`

- Nominatim-Public-API hat ein Rate-Limit von 1 req/s — wir respektieren das
- Bei Fehlern in den Logs nach `Reverse geocoding failed` suchen
- `NOMINATIM_USER_AGENT` muss gesetzt sein, sonst blockt Nominatim
- Ohne Internet eigene Nominatim-Instanz aufsetzen und `NOMINATIM_URL` umbiegen

### 4.6 `401 Unauthorized` bei API-Calls

- `X-API-Key` Header fehlt oder stimmt nicht mit `API_KEY` aus `.env` überein
- `/api/v1/health` ist die einzige Ausnahme — alle anderen Endpunkte brauchen den Key

### 4.7 Batch-Job hängt nach Server-Neustart

- Chunks im Status `processing` werden derzeit nicht automatisch fortgesetzt
- Manuell: `UPDATE chunks SET status = 'pending' WHERE status = 'processing';`
- (Auto-Resume ist im Backlog für Sprint 4)

### 4.8 Tests laufen lokal aber nicht in CI

- CI nutzt PostgreSQL 16, lokal evtl. andere Version
- `TEST_DATABASE_URL` muss gesetzt sein für Integration/System-Tests
- `pytest-timeout` und `python-multipart` müssen installiert sein

---

## 5. Backup & Wiederherstellung

### Datenbank-Backup
```bash
pg_dump "$DATABASE_URL" > lr_autotag_backup_$(date +%Y%m%d).sql
```

### Restore
```bash
psql "$DATABASE_URL" < lr_autotag_backup_20260101.sql
```

Da die DB nur abgeleitete Daten (Keywords) enthält, ist ein Verlust nicht
katastrophal — die Keywords lassen sich aus den Originalbildern neu generieren.
