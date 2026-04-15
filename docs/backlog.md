# LR-AutoTag — Backlog

Offene Aufgaben und geplante Verbesserungen.

---

## Offen

### Groessere Vision-Modelle evaluieren

**Voraussetzung:** P40 GPU Thermo-Problem geloest, Ollama wieder mit GPU-Zugriff. Fuer Modelle >=24 GB (Q4) und MoE-Modelle zusaetzlich: VM-RAM auf mind. 32 GB aufgeruestet (MoE-Modelle muessen alle Gesamtparameter im Speicher halten).

Benchmark mit folgenden Modellen durchfuehren, die auf die P40 (24 GB VRAM) passen:

| Modell | Ollama-Tag | Parameter | VRAM (Q4) | Erwartung |
|---|---|---|---|---|
| LLaVA 34B (Yi-34B Basis) | `llava:34b` | 34B | ~20 GB | Bessere Lichtsituation/Perspektive-Erkennung |
| Gemma 4 26B A4B (Google, MoE) | `gemma4:26b-a4b-it-q4_K_M` | 26B gesamt / 4B aktiv | ~15,6 GB | MoE: Inferenz-Kosten auf 4B-Niveau bei 26B-Kapazitaet. Multimodal (Text/Bild/Video/Audio), 256K Kontext. Nachfolger von Gemma 3 27B. |
| InternVL2 26B | Community-Build (GGUF) | 26B | ~16 GB | Starke Bildverstaendnis-Performance in Benchmarks. Deutsche Sprachqualitaet explizit pruefen (EN->DE Postprocessing ggf. noetig). |

**Vorgehen:**
- Bestehenden Benchmark (`docs/benchmark/run_benchmark.py`) mit allen Kandidaten ausfuehren
- Ergebnisse gegen LLaVA 13B vergleichen (aktuell 68% Qualitaet, ~440s/Bild auf CPU)
- Auf GPU erwartete Inferenzzeit: 15-30s/Bild fuer 26B-34B dichte Modelle, ~8-15s fuer Gemma 4 MoE (vs. 6-12s fuer LLaVA 13B)
- Fokus auf Schwachstellen des 13B: Lichtsituation, Perspektive, Technik-Erkennung
- Auf Basis der Ergebnisse: Entscheidung ob Produktionsmodell wechselt (ADR-Update in `docs/tech.md`)

**Offene Vorab-Checks:**
- [ ] InternVL2 Verfuegbarkeit in Ollama / GGUF-Format pruefen (aktuell nur Community-Builds)
- [ ] Falls englischsprachiges Modell gewinnt: EN->DE Keyword-Normalizer als eigene Aufgabe einplanen
