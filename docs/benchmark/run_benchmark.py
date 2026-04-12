#!/usr/bin/env python3
"""Comprehensive vision-model benchmark for LR-AutoTag.

Runs the V2 production prompt against every model × every test image,
captures raw responses + Ollama timings, and writes:

  results/           — one JSON per model with raw data
  report.md          — markdown article skeleton with tables + analysis
  summary.json       — compact machine-readable summary

Usage:
    python3 docs/benchmark/run_benchmark.py

Environment:
    OLLAMA_BASE_URL   defaults to http://localhost:11434
    BENCHMARK_TIMEOUT defaults to 1800 (seconds per request)

The script processes models sequentially (model-outer, image-inner) so
each model is loaded exactly once.  Images live in
tests/nfa/fixtures/benchmark_images/.
"""
import base64
import datetime as dt
import json
import os
import pathlib
import platform
import re
import subprocess
import sys
import time
import urllib.request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
TIMEOUT = int(os.getenv("BENCHMARK_TIMEOUT", "1800"))

MODELS = [
    "moondream",       # 1.4B — included for completeness; expect timeouts
    "llava-phi3",      # 3.8B
    "gemma3:4b",       # 4B
    "llava:7b",        # 7B
    "bakllava",        # 7B (Mistral base)
    "llava-llama3",    # 8B
    "minicpm-v",       # 8B
    "llama3.2-vision", # 11B
    "llava:13b",       # 13B
]

# Models to skip entirely (checkpoint kept but no new inference).
# Moondream can't handle the V2 CoT prompt — generates garbage or
# hits the 1800s timeout on every image.
SKIP_MODELS: set[str] = {"moondream"}

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
IMG_DIR = PROJECT_ROOT / "backend" / "tests" / "nfa" / "fixtures" / "benchmark_images"
OUT_DIR = PROJECT_ROOT / "docs" / "benchmark" / "results"

# The production prompt (V2) — kept in sync with ollama_client.py.
PROMPT = """\
Analysiere dieses Foto und gib deutsche Schlagworte zurueck.

Bevor du antwortest, ueberlege kurz:
- Woher kommt das Hauptlicht im Bild? (von vorne, von der Seite, von hinten, von oben?)
- Aus welchem Winkel wurde das Foto aufgenommen? (von unten, von oben, Augenhoehe, Makro?)
- Ist das Bild schwarzweiss? Gibt es Bokeh, Langzeitbelichtung oder andere Techniken?
- Welche Stimmung vermittelt das Bild? Ist es friedlich, dramatisch, melancholisch?

Kategorien:
- Objekte: frei waehlbar, MAXIMAL 5
- Szene: frei waehlbar, max 2
- Umgebung: frei waehlbar, max 2
- Tageszeit: Morgengrauen, Morgen, Vormittag, Mittag, Nachmittag, Abend, Daemmerung, Nacht
- Jahreszeit: Fruehling, Sommer, Herbst, Winter
- Wetter: Sonnig, Bewoelkt, Bedeckt, Regen, Schnee, Nebel, Gewitter, Wind, Sturm, Dunst
- Stimmung (1-2 Werte): Dramatisch, Melancholisch, Mystisch, Bedrohlich, Einsam, \
Vertraeumt, Nostalgisch, Majestaetisch, Romantisch, Lebhaft, Froehlich, Friedlich
- Lichtsituation (0-3 Werte, NUR wenn im Bild erkennbar — leer lassen wenn unauffaellig): \
Gegenlicht, Seitenlicht, Hartes Licht, Weiches Licht, Diffuses Licht, \
Hell-Dunkel, Silhouette, Lichtstrahlen, High-Key, Low-Key, \
Kantenlicht, Oberlicht, Mischlicht, Kunstlicht, Natuerliches Licht, Frontlicht
- Perspektive (genau 1 Wert — Normalperspektive NUR wenn Kamera klar auf Augenhoehe \
und horizontal steht, sonst den spezifischen Winkel waehlen): \
Froschperspektive, Vogelperspektive, Draufsicht, Aufsicht, Untersicht, \
Schraegsicht, Normalperspektive
- Technik (0-2 Werte, NUR bei offensichtlichem Merkmal — leer lassen wenn nichts): \
Schwarzweiss, Makro, Bokeh, Langzeitbelichtung, Bewegungsunschaerfe, Infrarot

Regeln:
- Fuer alle Whitelist-Kategorien NUR Werte aus der jeweiligen Liste verwenden.
- Format: JSON-Array mit maximal 30 Keywords.
- Antworte NUR mit dem JSON-Array, kein weiterer Text."""

# ---------------------------------------------------------------------------
# Expected ground-truth (for quality scoring)
# ---------------------------------------------------------------------------

GROUND_TRUTH: dict[str, dict[str, list[str]]] = {
    "01_sunset.jpg": {
        "should_contain": ["Gegenlicht", "Abend"],
        "should_not_contain": ["Morgengrauen"],
        "perspective_expected": "Normalperspektive",
        "technik_expected": [],
        "description": "Panorama of Spanish town Cómpeta at golden-hour sunset",
    },
    "02_macro.jpg": {
        "should_contain": ["Biene", "Makro"],
        "should_not_contain": ["Regen"],
        "perspective_expected": "Froschperspektive",
        "technik_expected": ["Makro"],
        "description": "Macro shot of a bee on a purple flower (ForestWander, CC BY-SA)",
    },
    "03_night_city.jpg": {
        "should_contain": ["Nacht", "Kunstlicht"],
        "should_not_contain": ["Morgengrauen"],
        "perspective_expected": "Normalperspektive",
        "technik_expected": ["Langzeitbelichtung"],
        "description": "Manhattan skyline from Jersey City at night, reflections on Hudson",
    },
    "04_portrait_bw.jpg": {
        "should_contain": ["Mann", "Schwarzweiss"],
        "should_not_contain": ["Regen"],
        "perspective_expected": "Normalperspektive",
        "technik_expected": ["Schwarzweiss"],
        "description": "B&W portrait of elderly man in Rhodes, Greece",
    },
    "05_forest_autumn.jpg": {
        "should_contain": ["Wald", "Herbst"],
        "should_not_contain": [],
        "perspective_expected": "Normalperspektive",
        "technik_expected": [],
        "description": "Autumn forest path with tall deciduous trees",
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def system_info() -> dict:
    try:
        cpus = os.cpu_count() or 0
    except Exception:
        cpus = 0
    try:
        mem_kb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // 1024
        mem_gb = round(mem_kb / (1024 * 1024), 1)
    except Exception:
        mem_gb = 0
    try:
        cpu_model = subprocess.check_output(
            ["grep", "-m1", "model name", "/proc/cpuinfo"], text=True
        ).split(":", 1)[1].strip()
    except Exception:
        cpu_model = platform.processor() or "unknown"
    return {
        "hostname": platform.node(),
        "os": platform.platform(),
        "cpu_model": cpu_model,
        "cpu_count": cpus,
        "ram_gb": mem_gb,
        "python": platform.python_version(),
        "ollama_base_url": OLLAMA_BASE,
        "timeout_s": TIMEOUT,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def parse_keywords(raw: str) -> list[str]:
    """Mirror of OllamaClient._parse_keywords — flatten list or dict."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    def try_json(s):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None

    def flatten(value):
        result = []

        def add(item):
            if item is None:
                return
            if isinstance(item, str):
                s = item.strip()
                if s:
                    result.append(s)
            elif isinstance(item, dict):
                for v in item.values():
                    add(v)
            elif isinstance(item, (list, tuple)):
                for x in item:
                    add(x)
            else:
                s = str(item).strip()
                if s:
                    result.append(s)

        add(value)
        return result

    parsed = try_json(cleaned)
    if parsed is not None:
        return flatten(parsed)[:30]

    for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        match = re.search(pattern, cleaned)
        if match:
            parsed = try_json(match.group())
            if parsed is not None:
                return flatten(parsed)[:30]

    parts = [p.strip().strip('"').strip("'") for p in cleaned.split(",")]
    return [p for p in parts if p and len(p) < 50][:30]


def score_result(keywords: list[str], image_name: str) -> dict:
    """Score against ground truth; returns a dict of check results."""
    gt = GROUND_TRUTH.get(image_name, {})
    kw_lower = [k.lower() for k in keywords]
    checks = {}
    for expected in gt.get("should_contain", []):
        checks[f"has_{expected}"] = any(expected.lower() in k for k in kw_lower)
    for bad in gt.get("should_not_contain", []):
        checks[f"not_{bad}"] = not any(bad.lower() in k for k in kw_lower)
    p_exp = gt.get("perspective_expected", "")
    if p_exp:
        checks[f"perspective={p_exp}"] = any(p_exp.lower() in k for k in kw_lower)
    for tech in gt.get("technik_expected", []):
        checks[f"technik_{tech}"] = any(tech.lower() in k for k in kw_lower)
    checks["total_keywords"] = len(keywords)
    checks["score"] = sum(1 for k, v in checks.items() if isinstance(v, bool) and v)
    checks["max_score"] = sum(1 for v in checks.values() if isinstance(v, bool))
    return checks


def call_ollama(model: str, image_bytes: bytes) -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "model": model,
        "prompt": PROMPT,
        "images": [b64],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = json.load(r)
        elapsed = time.monotonic() - t0
    except Exception as e:
        elapsed = time.monotonic() - t0
        return {"error": str(e), "elapsed_sec": round(elapsed, 2)}

    raw = body.get("response", "")
    keywords = parse_keywords(raw)
    return {
        "elapsed_sec": round(elapsed, 2),
        "raw_response": raw,
        "keywords": keywords,
        "keyword_count": len(keywords),
        "timings": {
            "total_duration_ms": round((body.get("total_duration") or 0) / 1e6, 1),
            "load_duration_ms": round((body.get("load_duration") or 0) / 1e6, 1),
            "prompt_eval_count": body.get("prompt_eval_count"),
            "prompt_eval_ms": round((body.get("prompt_eval_duration") or 0) / 1e6, 1),
            "eval_count": body.get("eval_count"),
            "eval_ms": round((body.get("eval_duration") or 0) / 1e6, 1),
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _model_filename(model: str) -> str:
    return model.replace(":", "_").replace("/", "_") + ".json"


def _load_existing(model: str) -> dict:
    """Load previously saved results for *model* so we can skip images
    that were already benchmarked.  Returns an empty dict on the first run."""
    path = OUT_DIR / _model_filename(model)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    images = sorted(IMG_DIR.glob("*.jpg"))
    if not images:
        print(f"ERROR: no images found in {IMG_DIR}", file=sys.stderr)
        sys.exit(1)

    sysinfo = system_info()
    print(f"System: {sysinfo['cpu_count']} vCPUs, {sysinfo['ram_gb']} GB RAM, {sysinfo['cpu_model']}")
    print(f"Models: {len(MODELS)}")
    print(f"Images: {len(images)}")
    print(f"Timeout: {TIMEOUT}s per request")
    print(f"Total runs: {len(MODELS) * len(images)}")
    print()

    all_results: dict = {}
    summary_rows: list[dict] = []

    for mi, model in enumerate(MODELS, 1):
        if model in SKIP_MODELS:
            print(f"[{mi}/{len(MODELS)}] {model} — SKIPPED (in SKIP_MODELS)")
            print()
            continue

        print(f"{'='*60}")
        print(f"[{mi}/{len(MODELS)}] {model}")
        print(f"{'='*60}")

        # Resume support: load existing results and skip completed images.
        existing = _load_existing(model)
        done_images: dict = existing.get("images", {})
        model_results: dict = {
            "system": sysinfo,
            "model": model,
            "prompt": PROMPT,
            "images": dict(done_images),  # carry over completed
        }

        for ii, img_path in enumerate(images, 1):
            img_name = img_path.name

            # Skip if we already have a result for this image.
            if img_name in done_images:
                prev = done_images[img_name]
                prev_t = prev.get("elapsed_sec")
                prev_kw = prev.get("keyword_count", 0)
                print(f"  [{ii}/{len(images)}] {img_name} — SKIPPED (already done: "
                      f"{prev_t}s, {prev_kw} kws)")
                score = prev.get("score", {"score": 0, "max_score": 0})
                summary_rows.append({
                    "model": model, "image": img_name,
                    "elapsed_sec": prev_t, "keyword_count": prev_kw,
                    "score": score.get("score", 0), "max_score": score.get("max_score", 0),
                    "error": prev.get("error"),
                })
                continue

            img_bytes = img_path.read_bytes()
            print(f"  [{ii}/{len(images)}] {img_name} ({len(img_bytes)//1024} KB) ...", end="", flush=True)

            result = call_ollama(model, img_bytes)

            if "error" in result:
                print(f"  ERROR ({result['elapsed_sec']:.0f}s): {result['error'][:80]}")
                score = {"score": 0, "max_score": 0, "total_keywords": 0}
            else:
                score = score_result(result["keywords"], img_name)
                kw_preview = ", ".join(result["keywords"][:6])
                if len(result["keywords"]) > 6:
                    kw_preview += "..."
                print(
                    f"  {result['elapsed_sec']:6.1f}s  "
                    f"{result['keyword_count']:2d} kws  "
                    f"score {score['score']}/{score['max_score']}  "
                    f"[{kw_preview}]"
                )

            result["score"] = score
            model_results["images"][img_name] = result

            # Checkpoint: write per-model JSON after EVERY image so we
            # can resume if the script crashes or is interrupted.
            model_file = OUT_DIR / _model_filename(model)
            model_file.write_text(json.dumps(model_results, indent=2, ensure_ascii=False))

            summary_rows.append({
                "model": model, "image": img_name,
                "elapsed_sec": result.get("elapsed_sec"),
                "keyword_count": result.get("keyword_count", 0),
                "score": score.get("score", 0), "max_score": score.get("max_score", 0),
                "error": result.get("error"),
            })

        print(f"  -> Saved {_model_filename(model)}")
        print()

        all_results[model] = model_results

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------

    summary = {"system": sysinfo, "models": MODELS, "rows": summary_rows}
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    # -----------------------------------------------------------------------
    # Markdown report
    # -----------------------------------------------------------------------

    lines = [
        "# LR-AutoTag Vision Model Benchmark",
        "",
        f"**Datum:** {sysinfo['timestamp_utc'][:10]}",
        f"**System:** {sysinfo['cpu_count']} vCPUs ({sysinfo['cpu_model']}), "
        f"{sysinfo['ram_gb']} GB RAM, CPU-only (keine GPU)",
        f"**Prompt:** V2 mit Chain-of-Thought (siehe `backend/app/pipeline/ollama_client.py`)",
        f"**Timeout:** {TIMEOUT}s pro Request",
        f"**Bilder:** {len(images)} Wikimedia-Commons-Testbilder "
        "(Sunset, Makro, Nachtstadt, SW-Portrait, Herbstwald)",
        "",
        "---",
        "",
        "## Timing-Übersicht",
        "",
    ]

    # Timing table
    lines.append("| Modell | Params | " + " | ".join(p.stem for p in images) + " | Ø |")
    lines.append("|" + "---|" * (len(images) + 3))
    param_map = {
        "moondream": "1.4B", "llava-phi3": "3.8B", "gemma3:4b": "4B",
        "llava:7b": "7B", "bakllava": "7B", "llava-llama3": "8B",
        "minicpm-v": "8B", "llama3.2-vision": "11B", "llava:13b": "13B",
    }
    for model in MODELS:
        row = [f"`{model}`", param_map.get(model, "?")]
        times = []
        for img in images:
            r = all_results.get(model, {}).get("images", {}).get(img.name, {})
            t = r.get("elapsed_sec")
            if t is not None:
                row.append(f"{t:.0f}s")
                times.append(t)
            else:
                row.append("ERR")
        avg = f"{sum(times)/len(times):.0f}s" if times else "—"
        row.append(avg)
        lines.append("| " + " | ".join(row) + " |")

    lines += ["", "---", "", "## Qualitäts-Scoring", ""]
    lines.append(
        "Jedes Bild hat bekannte Ground-Truth-Checks (erwartete Keywords, "
        "verbotene Halluzinationen, erwartete Perspektive/Technik). "
        "Score = Anzahl bestandener Checks / Gesamtzahl Checks."
    )
    lines.append("")
    lines.append("| Modell | " + " | ".join(p.stem for p in images) + " | Gesamt |")
    lines.append("|" + "---|" * (len(images) + 2))
    for model in MODELS:
        row = [f"`{model}`"]
        total_score = 0
        total_max = 0
        for img in images:
            r = all_results.get(model, {}).get("images", {}).get(img.name, {})
            sc = r.get("score", {})
            s, mx = sc.get("score", 0), sc.get("max_score", 0)
            total_score += s
            total_max += mx
            row.append(f"{s}/{mx}" if mx > 0 else "—")
        row.append(f"**{total_score}/{total_max}**")
        lines.append("| " + " | ".join(row) + " |")

    lines += ["", "---", "", "## Keywords pro Bild (Detailansicht)", ""]
    for img in images:
        gt = GROUND_TRUTH.get(img.name, {})
        lines.append(f"### {img.name}")
        lines.append(f"_{gt.get('description', '')}_")
        lines.append("")
        for model in MODELS:
            r = all_results.get(model, {}).get("images", {}).get(img.name, {})
            kws = r.get("keywords", [])
            t = r.get("elapsed_sec")
            err = r.get("error")
            sc = r.get("score", {})
            if err:
                lines.append(f"**{model}** — ERROR: `{err[:80]}`")
            else:
                lines.append(
                    f"**{model}** ({t:.0f}s, {len(kws)} kws, "
                    f"score {sc.get('score',0)}/{sc.get('max_score',0)}):"
                )
                lines.append(f"  {', '.join(kws)}")
            lines.append("")

    lines += [
        "---",
        "",
        "## Methodik",
        "",
        "- Jedes Modell wird sequenziell getestet (model-outer, image-inner), "
        "damit das Modell einmal geladen wird und warm bleibt.",
        "- Temperature = 0.1 für reproduzierbare Ergebnisse.",
        "- Der Prompt ist identisch für alle Modelle (V2 mit Chain-of-Thought).",
        "- Scoring basiert auf manuell definierten Ground-Truth-Checks pro Bild "
        "(expected keywords, forbidden hallucinations, expected perspective/technique).",
        "- Alle Rohdaten (inkl. vollständige Ollama-Timings) liegen als JSON in `results/`.",
        "",
        "---",
        "",
        "## Fazit",
        "",
        "_TODO: manuell ergänzen nach Sichtung der Ergebnisse._",
    ]

    report_path = PROJECT_ROOT / "docs" / "benchmark" / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print("=" * 60)
    print("DONE")
    print(f"  Results:  {OUT_DIR}/")
    print(f"  Report:   {report_path}")
    print(f"  Summary:  {OUT_DIR / 'summary.json'}")
    print("=" * 60)

    # Final summary table
    print()
    print(f"{'Model':20s} {'Avg Time':>10s} {'Avg Score':>12s}")
    print("-" * 44)
    for model in MODELS:
        rows = [r for r in summary_rows if r["model"] == model and r.get("error") is None]
        if rows:
            avg_t = sum(r["elapsed_sec"] for r in rows) / len(rows)
            avg_s = sum(r["score"] for r in rows) / len(rows)
            max_s = rows[0]["max_score"]
            print(f"{model:20s} {avg_t:8.1f}s   {avg_s:.1f}/{max_s}")
        else:
            print(f"{model:20s}      —          —")


if __name__ == "__main__":
    main()
