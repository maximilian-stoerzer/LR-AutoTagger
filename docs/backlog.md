# LR-AutoTag — Backlog

Offene Aufgaben und geplante Verbesserungen.

---

## Offen

### Groessere Vision-Modelle evaluieren

**Voraussetzung:** P40 GPU Thermo-Problem geloest, Ollama wieder mit GPU-Zugriff.

Benchmark mit zwei groesseren Modellen durchfuehren, die auf die P40 (24 GB VRAM) passen:

| Modell | Parameter | VRAM (Q4) | Erwartung |
|---|---|---|---|
| LLaVA 34B (Yi-34B Basis) | 34B | ~20 GB | Bessere Lichtsituation/Perspektive-Erkennung |
| Gemma 3 27B (Google) | 27B | ~16 GB | Neueres Modell, potenziell bessere Bildanalyse |

**Vorgehen:**
- Bestehenden Benchmark (`docs/benchmark/run_benchmark.py`) mit beiden Modellen ausfuehren
- Ergebnisse gegen LLaVA 13B vergleichen (aktuell 68% Qualitaet, ~440s/Bild auf CPU)
- Auf GPU erwartete Inferenzzeit: 15-30s/Bild (vs. 6-12s fuer LLaVA 13B)
- Fokus auf Schwachstellen des 13B: Lichtsituation, Perspektive, Technik-Erkennung
