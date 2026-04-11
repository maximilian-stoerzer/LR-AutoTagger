# Admin-Dokumentation

Wie das Plugin so konfiguriert wird, dass es das Backend nutzen kann.

> **Status:** Das Lightroom-Plugin ist noch nicht implementiert. Dieses
> Dokument beschreibt das geplante Setup und gilt fuer alle HTTP-Clients,
> die heute schon das Backend ansprechen koennen (curl, Postman, etc.).

---

## 1. Architektur-Ueberblick (Admin-Sicht)

```
┌────────────────────┐         ┌─────────────────────┐
│  Lightroom Classic │  HTTP   │  LR-AutoTag Backend │
│  + Plugin (Lua)    │────────►│  (FastAPI, Port     │
│                    │  +Auth  │   8000, LAN)        │
└────────────────────┘         └──────┬──────────┬───┘
                                      │          │
                                      ▼          ▼
                              ┌──────────┐  ┌──────────┐
                              │  Ollama  │  │ Postgres │
                              │ (shared) │  │          │
                              └──────────┘  └──────────┘
```

Der Plugin spricht **nur** mit dem Backend. Alle anderen Verbindungen
(Backend↔Ollama, Backend↔Postgres, Backend↔Nominatim) laufen serverseitig.

---

## 2. Backend-seitig: Was muss eingestellt sein

### 2.1 `.env` (Backend-Server)

Mindestens diese vier Variablen muessen gesetzt sein:

```bash
DATABASE_URL=postgresql://lr_autotag:<password>@localhost:5432/lr_autotag
OLLAMA_BASE_URL=http://192.168.1.10:11434
OLLAMA_MODEL=llava:13b
API_KEY=<32-byte random string>
```

Weitere Parameter, die typischerweise angefasst werden:

```bash
# Wie lange der Backend auf eine Ollama-Antwort wartet. Auf CPU-only
# Systemen unbedingt hochsetzen — siehe Abschnitt 6.1.
OLLAMA_TIMEOUT=600

# Max. parallele Ollama-Requests. Ollama ist meist Shared Service —
# zwei gleichzeitige Requests sind in der Regel ausreichend, lassen aber
# Platz fuer andere Clients.
OLLAMA_MAX_CONCURRENT=2

# Hartes Cap fuer Keywords pro Bild. 30 ist der Default seit Einfuehrung
# der Kategorien Lichtsituation / Perspektive / Technik / Brennweite /
# Tageslichtphase.
MAX_KEYWORDS=30

# Fallback-Ort fuer die Sonnenstand-basierte Tageslichtphase (Goldene
# Stunde, Blaue Stunde, Nacht, Tageslicht), wenn ein Foto keine GPS-
# Daten hat. Zulaessige Werte:
#   BAYERN = Regensburg (49.0134 N, 12.1016 E) — Default
#   MUNICH = Muenchen (48.1374 N, 11.5754 E)
#   NONE   = kein Fallback, Tageslichtphasen-Keyword entfaellt
# Ungueltige Werte (z.B. BERLIN) werden beim per-Request-Override mit
# HTTP 400 abgewiesen.
SUN_CALC_DEFAULT_LOCATION=BAYERN
```

Weitere Defaults siehe `docs/installation.md` Abschnitt 2.4 und die
vollstaendige Keyword-Kategorien-Uebersicht in `docs/tech.md` Abschnitt
3.5.

### 2.2 Netzwerk

| Verbindung | Port | Direction |
|---|---|---|
| Plugin → Backend | 8000/tcp | LAN, eingehend |
| Backend → Ollama | 11434/tcp | LAN, ausgehend |
| Backend → Postgres | 5432/tcp | meist localhost |
| Backend → Nominatim | 443/tcp | Internet, ausgehend (oder LAN bei eigener Instanz) |

Firewall des Backend-Servers muss Port 8000 fuer das LAN-Subnetz freigeben.

### 2.3 API-Key generieren und verteilen

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Den generierten Key:
1. In `backend/.env` unter `API_KEY` eintragen
2. Backend neu starten (`systemctl restart lr-autotag`)
3. Im Plugin (oder im HTTP-Client) als `X-API-Key`-Header senden

**Wichtig:** Bei Aenderung des Keys muessen alle Clients aktualisiert werden.

### 2.4 Health-Check

Vor jeder Plugin-Konfiguration verifizieren, dass das Backend gesund ist:

```bash
curl http://<backend-host>:8000/api/v1/health
```

Erwartete Antwort:
```json
{"status": "ok", "database": "ok", "ollama": "ok"}
```

Bei `degraded` siehe `installation.md` Abschnitt 4.

---

## 3. Plugin-seitig: Was muss eingestellt sein

Im Lightroom-Plugin unter **Datei → Zusatzmodul-Manager → LR-AutoTag**
gibt es drei Sektionen.

**Sektion „Verbindung" — zwingend:**

| Feld | Pflicht | Beispiel | Erlaeuterung |
|---|---|---|---|
| Backend URL | ja | `http://192.168.1.20:8001` | Vollstaendige URL inkl. Schema und Port, ohne `/api/v1` |
| API Key | ja | `7f3...XYZ` | Wert aus `backend/.env` `API_KEY` |

**Sektion „Einstellungen":**

| Feld | Pflicht | Default | Erlaeuterung |
|---|---|---|---|
| Timeout (Sek.) | nein | `30` | HTTP-Timeout fuer Plugin-Requests. **Auf CPU-only Servern mindestens 600 setzen**, sonst bricht das Plugin ab, bevor die Ollama-Antwort da ist. |
| Vorschaugroesse (px) | nein | `1024` | Lange Seite des Vorschaubilds in Pixeln |

**Sektion „Analyse-Optionen" — optionale per-Plugin Overrides:**

| Feld | Pflicht | Beispiel | Erlaeuterung |
|---|---|---|---|
| Ollama-Modell | nein | leer (= Backend-Default) oder `llava:7b` | Ueberschreibt `OLLAMA_MODEL` nur fuer Requests dieses Plugin-Users. Der Button „Modelle laden" fragt `/api/v1/models` an und zeigt die auf dem Server installierten Modelle. |
| Tageslicht-Fallback | nein | `Backend-Default verwenden` | Ueberschreibt `SUN_CALC_DEFAULT_LOCATION` (BAYERN / MUNICH / NONE) nur fuer Requests dieses Plugin-Users. Ungueltige Werte werden vom Backend mit HTTP 400 abgewiesen. |

Diese Werte werden im Plugin lokal in den LR-Settings persistiert und
auf jeder `/analyze`- und `/batch/image`-Anfrage als Form-Felder
mitgeschickt. Wenn leer, greift der Backend-Default aus `.env`.

---

## 4. Verbindung testen (manuell, vor Plugin-Verfuegbarkeit)

### 4.1 Health pruefen
```bash
curl -i http://<backend-host>:8000/api/v1/health
```

### 4.2 Auth pruefen
```bash
# Ohne Key → 401 erwartet
curl -i http://<backend-host>:8000/api/v1/results/test

# Mit Key → 404 (image_id existiert nicht) erwartet
curl -i -H "X-API-Key: <KEY>" http://<backend-host>:8000/api/v1/results/test
```

### 4.3 Einzelbild analysieren
```bash
curl -X POST http://<backend-host>:8000/api/v1/analyze \
  -H "X-API-Key: <KEY>" \
  -F "file=@/pfad/zum/bild.jpg" \
  -F "gps_lat=49.4094" \
  -F "gps_lon=8.6942" \
  -F "image_id=test_001"
```

Erwartete Antwort:
```json
{
  "image_id": "test_001",
  "keywords": ["Heidelberg", "Deutschland", "Bruecke", "Fluss", "..."],
  "geo_keywords": ["Heidelberg", "Baden-Wuerttemberg", "Deutschland"],
  "vision_keywords": ["Bruecke", "Fluss", "Stein", "Wasser"],
  "location_name": "Heidelberg, Baden-Wuerttemberg, Deutschland"
}
```

### 4.4 Batch-Modus testen
```bash
# 1. Batch starten
curl -X POST http://<backend-host>:8000/api/v1/batch/start \
  -H "X-API-Key: <KEY>" \
  -H "Content-Type: application/json" \
  -d '{"images": [{"image_id": "img_1", "gps_lat": 49.4, "gps_lon": 8.7}]}'

# 2. Naechstes Bild abfragen
curl -H "X-API-Key: <KEY>" http://<backend-host>:8000/api/v1/batch/next

# 3. Bild hochladen
curl -X POST http://<backend-host>:8000/api/v1/batch/image \
  -H "X-API-Key: <KEY>" \
  -F "image_id=img_1" \
  -F "file=@/pfad/zum/bild.jpg"

# 4. Status pruefen
curl -H "X-API-Key: <KEY>" http://<backend-host>:8000/api/v1/batch/status
```

---

## 5. Operative Aufgaben

### 5.1 Logs einsehen
```bash
journalctl -u lr-autotag -f                    # Live-Log (systemd)
journalctl -u lr-autotag --since "1 hour ago"  # Letzte Stunde
```

### 5.2 Backend neu starten (z.B. nach `.env`-Aenderung)
```bash
systemctl restart lr-autotag
```

### 5.3 Datenbank-Status
```bash
psql $DATABASE_URL <<'SQL'
SELECT
  (SELECT COUNT(*) FROM image_keywords) AS verschlagwortete_bilder,
  (SELECT COUNT(*) FROM batch_jobs WHERE status='running') AS laufende_jobs,
  (SELECT COUNT(*) FROM chunks WHERE status='failed') AS fehlgeschlagene_chunks;
SQL
```

### 5.4 Hängenden Batch-Job manuell abbrechen
```bash
curl -X POST http://<backend-host>:8000/api/v1/batch/cancel \
  -H "X-API-Key: <KEY>"
```

Oder direkt in der DB:
```sql
UPDATE batch_jobs SET status='cancelled' WHERE id='<job-id>';
```

### 5.5 Verschlagwortete Bilder zuruecksetzen
Wenn ein Bild noch einmal analysiert werden soll (z.B. nach Modell-Update):
```sql
DELETE FROM image_keywords WHERE image_id = 'foto_42';
```
Beim naechsten Batch wird es nicht mehr als "schon verarbeitet" erkannt.

### 5.6 Ollama-Auslastung steuern

Wenn Ollama auch von einer anderen App genutzt wird und blockiert:
- `OLLAMA_MAX_CONCURRENT=1` setzen → maximal 1 paralleler Request
- Backend neu starten
- Optional zu Tageszeiten mit weniger Last hochfahren (Cron-Job, nicht im Backend)

---

## 6. Performance-Hinweise

### 6.1 CPU-only Betrieb (kein GPU)

Wenn Ollama auf CPU laeuft (z.B. waehrend die GPU wegen Hardware-Problemen
gesperrt ist), braucht eine Einzel-Inferenz mit LLaVA 13B und dem
vollen Prompt leicht 60–120 Sekunden — abhaengig davon, wie viele
vCPUs der VM zugewiesen sind. Konsequenzen:

- **`OLLAMA_TIMEOUT` in `backend/.env` auf mindestens `600` setzen** —
  der Default `120` ist fuer CPU-Betrieb zu kurz und fuehrt zu
  `httpx.ReadTimeout`
- **Plugin-Timeout ebenfalls hochsetzen** (Default 30 s → mindestens
  600 s), sonst bricht das Plugin ab, bevor das Backend antwortet
- **vCPU-Zuweisung pruefen**: in `lscpu` sollte `CPU(s)` die
  zugewiesene Anzahl zeigen. Zeigt es `1`, obwohl der Host mehr hat,
  muss der Host-Admin die VM erweitern (`virsh setvcpus <vm> <n>`).

Ein Perspektivwechsel auf ein kleineres Modell wie `llava:7b` halbiert
die Inferenzzeit grob. Ueber die Plugin-Sektion „Analyse-Optionen"
kann das per Plugin-User (ohne Backend-Restart) getestet werden, siehe
Abschnitt 3.

### 6.2 GPU-Betrieb

Mit LLaVA 13B auf einer Nvidia P40 (24 GB VRAM) rechnet die Pipeline
etwa **5–10 Bilder/Minute** — einige Sekunden pro Bild. In dem Regime
ist das Backend in der Regel I/O-gebunden (Nominatim, Plugin-Upload)
statt CPU-gebunden.

---

## 7. Sicherheit

| Risiko | Gegenmassnahme |
|---|---|
| Unbefugter Zugriff | API-Key-Auth, LAN-only (kein Internet-Exposure) |
| Bruteforce auf API-Key | Key ausreichend lang waehlen (≥ 32 Bytes URL-safe) |
| Pfad-Traversal in `image_id` | Backend behandelt `image_id` als String, nie als Pfad |
| SQL-Injection | psycopg-Parameter-Binding, vom CI-Architektur-Check verifiziert |
| Bilder-Upload als DoS | LAN-only mitigiert, optional `client_max_body_size` im Reverse-Proxy |

**Empfehlung:** Keinen Internet-Zugriff auf den Backend-Port erlauben. Falls
remote noetig, ein VPN nutzen.
