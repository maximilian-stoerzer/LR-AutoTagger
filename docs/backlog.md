# LR-AutoTag — Backlog

Offene Aufgaben und geplante Verbesserungen.

---

## Erledigt

### ✅ Groessere Vision-Modelle evaluieren (erledigt 2026-04-15)

GPU-Benchmark durchgefuehrt nach Loesung des P40-Thermo-Problems. Getestet:
`llava:34b` (Yi-Basis), `gemma3:27b`, `gemma4:26b`, `gemma4:31b-it-q4_K_M`.

**Ergebnis:** Kein Modell schlaegt `llava:13b`.

| Modell | Score | Zeit | Urteil |
|---|---|---|---|
| **llava:13b** (Baseline) | 77 % | **15,8 s** | bleibt Empfehlung |
| gemma4:31b-it-q4_K_M | 77 % | 146,7 s | gleich gut, 9× langsamer |
| gemma3:27b | 73 % | 24,5 s | schlechter |
| gemma4:26b | 64 % | 255 s | Deadlock-Outlier |
| **llava:34b** | **45 %** | **69,9 s** | deutlich schlechter, 3× langsamer |

Details: `docs/benchmark/article.md` Kapitel 7.
