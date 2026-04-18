#!/usr/bin/env python3
"""Extended vision-model benchmark against 487-image ground-truth dataset.

Phase 1 (inference): runs selected models against all ground-truth images,
    checkpointing after every image so the script can resume on crash.
Phase 2 (scoring):   compares Ollama keywords against oracle labels
    (Claude + GPT-5 consensus) and computes per-category and overall metrics.

Usage:
    cd <project-root>
    backend/.venv/bin/python backend/scripts/benchmark/run_extended.py

    # override models (comma-separated):
    BENCHMARK_MODELS=llava:13b,gemma3:4b  backend/.venv/bin/python ...

    # skip scoring (inference only):
    backend/.venv/bin/python backend/scripts/benchmark/run_extended.py --no-score

Environment:
    OLLAMA_BASE_URL        defaults to http://localhost:11434
    BENCHMARK_TIMEOUT      defaults to 600 (seconds per request)
    BENCHMARK_MODELS       comma-separated override
    BENCHMARK_GPU_TEMP_HOT defaults to 85
    BENCHMARK_GPU_TEMP_COOL defaults to 75
"""
from __future__ import annotations

import argparse
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

# ---------------------------------------------------------------------------
# Paths (script runs from project root)
# ---------------------------------------------------------------------------

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
GT_ROOT = PROJECT_ROOT / "docs" / "benchmark" / "ground_truth"
IMAGES_ROOT = GT_ROOT / "images"
LABELS_ROOT = GT_ROOT / "labels"
MANIFEST_PATH = GT_ROOT / "manifest.jsonl"
OUT_DIR = PROJECT_ROOT / "docs" / "benchmark" / "results" / "extended"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
TIMEOUT = int(os.getenv("BENCHMARK_TIMEOUT", "60"))

GPU_TEMP_HOT = int(os.getenv("BENCHMARK_GPU_TEMP_HOT", "85"))
GPU_TEMP_COOL = int(os.getenv("BENCHMARK_GPU_TEMP_COOL", "75"))
GPU_POLL_INTERVAL = int(os.getenv("BENCHMARK_GPU_POLL_SEC", "10"))

MODELS = [
    "llava:13b",
    "gemma3:27b",
    "llama3.2-vision",
    "minicpm-v",
    "gemma3:4b",
    "llava:7b",
]

KEEP_MODELS = {"llava:13b"}

if (_models_override := os.getenv("BENCHMARK_MODELS", "").strip()):
    MODELS = [m.strip() for m in _models_override.split(",") if m.strip()]

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
# Helpers
# ---------------------------------------------------------------------------

import urllib.request  # noqa: E402


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
    try:
        gpu_name = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True, timeout=5, stderr=subprocess.DEVNULL,
        ).strip().splitlines()[0] or None
    except (subprocess.SubprocessError, FileNotFoundError, IndexError):
        gpu_name = None
    return {
        "hostname": platform.node(),
        "os": platform.platform(),
        "cpu_model": cpu_model,
        "cpu_count": cpus,
        "ram_gb": mem_gb,
        "gpu": gpu_name,
        "python": platform.python_version(),
        "ollama_base_url": OLLAMA_BASE,
        "timeout_s": TIMEOUT,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def load_manifest() -> list[dict]:
    if not MANIFEST_PATH.is_file():
        return []
    return [json.loads(line) for line in MANIFEST_PATH.read_text().splitlines() if line.strip()]


def parse_keywords(raw: str) -> list[str]:
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


def get_gpu_temp() -> int | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            text=True, timeout=5, stderr=subprocess.DEVNULL,
        )
        return int(out.strip().split()[0])
    except (subprocess.SubprocessError, FileNotFoundError, ValueError, IndexError):
        return None


def wait_for_cooldown() -> None:
    temp = get_gpu_temp()
    if temp is None or temp < GPU_TEMP_HOT:
        return
    print(f"\n  GPU {temp}C (>{GPU_TEMP_HOT}C) — waiting for {GPU_TEMP_COOL}C ...", flush=True)
    waited = 0
    while True:
        time.sleep(GPU_POLL_INTERVAL)
        waited += GPU_POLL_INTERVAL
        temp = get_gpu_temp()
        if temp is None or temp <= GPU_TEMP_COOL:
            print(f"  GPU cooled to {temp}C after {waited}s — resuming.", flush=True)
            return
        if waited % 60 == 0:
            print(f"    still {temp}C after {waited}s ...", flush=True)


def call_ollama(model: str, image_bytes: bytes) -> dict:
    wait_for_cooldown()
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
# Model pull management
# ---------------------------------------------------------------------------

PULL_RETRY_INTERVAL = 300  # 5 minutes


def is_model_available(model: str) -> bool:
    """Check if model is already pulled on the Ollama server."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        names = [m.get("name", "") for m in data.get("models", [])]
        return any(model == n or model == n.split(":")[0] or f"{model}:latest" == n for n in names)
    except Exception:
        return False


def start_pull(model: str) -> subprocess.Popen:
    """Start `ollama pull <model>` in the background, return the Popen handle."""
    print(f"  [PULL] Starting background pull: {model}", flush=True)
    return subprocess.Popen(
        ["ollama", "pull", model],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def wait_for_model(model: str, pull_proc: subprocess.Popen | None) -> None:
    """Block until model is available. If a pull process is running, wait for it.
    Otherwise poll every 5 minutes."""
    if is_model_available(model):
        if pull_proc and pull_proc.poll() is None:
            pull_proc.terminate()
        return

    if pull_proc is None:
        pull_proc = start_pull(model)

    while True:
        retcode = pull_proc.poll()
        if retcode is not None:
            if retcode == 0 and is_model_available(model):
                print(f"  [PULL] {model} ready.", flush=True)
                return
            print(f"  [PULL] {model} pull exited with code {retcode}, retrying ...", flush=True)
            pull_proc = start_pull(model)

        if is_model_available(model):
            print(f"  [PULL] {model} ready.", flush=True)
            pull_proc.terminate()
            return

        print(f"  [PULL] {model} not ready yet, checking again in 5 min ...", flush=True)
        time.sleep(PULL_RETRY_INTERVAL)


# ---------------------------------------------------------------------------
# Checkpoint I/O
# ---------------------------------------------------------------------------


def _model_filename(model: str) -> str:
    return model.replace(":", "_").replace("/", "_") + ".json"


def load_checkpoint(model: str) -> dict:
    path = OUT_DIR / _model_filename(model)
    if path.is_file():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


def save_checkpoint(model: str, data: dict) -> None:
    path = OUT_DIR / _model_filename(model)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Phase 1: Inference
# ---------------------------------------------------------------------------


def run_inference(manifest: list[dict]) -> None:
    sysinfo = system_info()
    total_images = len(manifest)

    print(f"System: {sysinfo.get('gpu') or 'CPU'}, {sysinfo['ram_gb']} GB RAM")
    print(f"Models: {len(MODELS)} — {', '.join(MODELS)}")
    print(f"Images: {total_images}")
    print(f"Timeout: {TIMEOUT}s per request")
    print(f"Max runs: {len(MODELS) * total_images}")
    print()

    # Kick off pull for the first model that isn't available and needs work
    next_pull_proc: subprocess.Popen | None = None
    next_pull_model: str | None = None
    for m in MODELS:
        ckpt = load_checkpoint(m)
        ok = {k: v for k, v in ckpt.get("images", {}).items() if not v.get("error")}
        if len(ok) >= total_images:
            continue
        if not is_model_available(m):
            next_pull_proc = start_pull(m)
            next_pull_model = m
            break

    for mi, model in enumerate(MODELS, 1):
        print(f"{'=' * 70}")
        print(f"[{mi}/{len(MODELS)}] {model}")
        print(f"{'=' * 70}")

        # Skip model entirely if checkpoint already has all images
        existing = load_checkpoint(model)
        existing_ok = {k: v for k, v in existing.get("images", {}).items() if not v.get("error")}
        if len(existing_ok) >= total_images:
            print(f"  => {model}: already complete ({len(existing_ok)}/{total_images}), skipping.")
            print()
            continue

        # Wait for current model to be available
        if next_pull_model == model:
            wait_for_model(model, next_pull_proc)
            next_pull_proc = None
            next_pull_model = None
        elif not is_model_available(model):
            wait_for_model(model, None)

        # Start pulling the NEXT unavailable model in the background
        if next_pull_proc is None:
            for future_model in MODELS[mi:]:
                if not is_model_available(future_model):
                    future_ckpt = load_checkpoint(future_model)
                    future_ok = {k: v for k, v in future_ckpt.get("images", {}).items() if not v.get("error")}
                    if len(future_ok) >= total_images:
                        continue
                    next_pull_proc = start_pull(future_model)
                    next_pull_model = future_model
                    break

        existing = load_checkpoint(model)
        all_saved: dict = existing.get("images", {})
        done_images = {k: v for k, v in all_saved.items() if not v.get("error")}
        checkpoint = {
            "system": sysinfo,
            "model": model,
            "prompt": PROMPT,
            "images": dict(done_images),
        }

        skipped = 0
        errors = 0
        model_start = time.monotonic()

        for ii, entry in enumerate(manifest, 1):
            sha1 = entry["sha1"]
            cat = entry["category"]

            if sha1 in done_images:
                skipped += 1
                continue

            img_path = IMAGES_ROOT / cat / f"{sha1}.jpg"
            if not img_path.is_file():
                print(f"  [{ii}/{total_images}] MISSING {cat}/{sha1[:8]}")
                errors += 1
                continue

            img_bytes = img_path.read_bytes()
            size_kb = len(img_bytes) // 1024

            result = call_ollama(model, img_bytes)
            result["category"] = cat

            done_count = len(checkpoint["images"]) + 1
            remaining = total_images - skipped - done_count - errors

            if "error" in result:
                errors += 1
                print(
                    f"  [{ii}/{total_images}] {cat}/{sha1[:8]}  "
                    f"ERROR ({result['elapsed_sec']:.0f}s): {result['error'][:60]}  "
                    f"[done={done_count} skip={skipped} err={errors} left={remaining}]"
                )
            else:
                elapsed_model = time.monotonic() - model_start
                inferred_so_far = done_count - skipped
                rate = inferred_so_far / elapsed_model if elapsed_model > 0 else 0
                eta_min = remaining / rate / 60 if rate > 0 else 0

                kw_preview = ", ".join(result["keywords"][:5])
                if len(result["keywords"]) > 5:
                    kw_preview += "..."
                print(
                    f"  [{ii}/{total_images}] {cat}/{sha1[:8]}  "
                    f"{result['elapsed_sec']:5.1f}s  {result['keyword_count']:2d}kw  "
                    f"[done={done_count} left={remaining} eta={eta_min:.0f}m]  "
                    f"[{kw_preview}]"
                )

            checkpoint["images"][sha1] = result
            save_checkpoint(model, checkpoint)

        done_total = len(checkpoint["images"])
        elapsed_total = time.monotonic() - model_start
        print(f"  => {model}: {done_total}/{total_images} done "
              f"({skipped} resumed, {errors} errors) in {elapsed_total / 60:.1f}m")

        # Cleanup: remove model to free disk, unless it's in KEEP_MODELS
        if model not in KEEP_MODELS and is_model_available(model):
            print(f"  [CLEANUP] Removing {model} to free disk ...", flush=True)
            try:
                subprocess.run(["ollama", "rm", model], check=True,
                               capture_output=True, text=True, timeout=60)
                print(f"  [CLEANUP] {model} removed.", flush=True)
            except Exception as e:
                print(f"  [CLEANUP] Failed to remove {model}: {e}", flush=True)

        print()


# ---------------------------------------------------------------------------
# Phase 2: Scoring
# ---------------------------------------------------------------------------

# Whitelist categories for exact-match scoring
WHITELISTS = {
    "tageszeit": {"Morgengrauen", "Morgen", "Vormittag", "Mittag", "Nachmittag",
                  "Abend", "Daemmerung", "Nacht"},
    "jahreszeit": {"Fruehling", "Sommer", "Herbst", "Winter"},
    "perspektive": {"Froschperspektive", "Vogelperspektive", "Draufsicht", "Aufsicht",
                    "Untersicht", "Schraegsicht", "Normalperspektive"},
    "wetter": {"Sonnig", "Bewoelkt", "Bedeckt", "Regen", "Schnee", "Nebel",
               "Gewitter", "Wind", "Sturm", "Dunst"},
    "stimmung": {"Dramatisch", "Melancholisch", "Mystisch", "Bedrohlich", "Einsam",
                 "Vertraeumt", "Nostalgisch", "Majestaetisch", "Romantisch", "Lebhaft",
                 "Froehlich", "Friedlich"},
    "lichtsituation": {"Gegenlicht", "Seitenlicht", "Hartes Licht", "Weiches Licht",
                       "Diffuses Licht", "Hell-Dunkel", "Silhouette", "Lichtstrahlen",
                       "High-Key", "Low-Key", "Kantenlicht", "Oberlicht", "Mischlicht",
                       "Kunstlicht", "Natuerliches Licht", "Frontlicht"},
    "technik": {"Schwarzweiss", "Makro", "Bokeh", "Langzeitbelichtung",
                "Bewegungsunschaerfe", "Infrarot"},
}


def load_oracle_labels(sha1: str) -> dict | None:
    """Load and merge Claude + GPT oracle labels. Returns None if either is missing."""
    yaml_path = LABELS_ROOT / f"{sha1}.yaml"
    if not yaml_path.is_file():
        return None
    text = yaml_path.read_text()

    def extract_section(section: str) -> dict | None:
        block = re.search(rf"^{section}:.*?(?=^\w|\Z)", text, re.MULTILINE | re.DOTALL)
        if not block:
            return None
        obj_match = re.search(r"^\s+objekte:\s*(.+?)(?:\s*#.*)?$", block.group(0), re.MULTILINE)
        if not obj_match or obj_match.group(1).strip() == "null":
            return None

        fields = {}
        for m in re.finditer(r"^\s+(\w+):\s*(.+?)(?:\s*#.*)?$", block.group(0), re.MULTILINE):
            key, val = m.group(1), m.group(2).strip()
            if key.startswith("_"):
                continue
            if val == "null":
                fields[key] = None
            elif val == "[]":
                fields[key] = []
            elif val.startswith("["):
                items = re.findall(r'"([^"]*)"', val)
                fields[key] = items
            elif val.startswith('"') and val.endswith('"'):
                fields[key] = val.strip('"')
            else:
                fields[key] = val
        return fields

    claude = extract_section("claude")
    gpt = extract_section("gpt")
    if not claude or not gpt:
        return None

    return {"claude": claude, "gpt": gpt}


def keyword_in_list(keyword: str, keyword_list: list[str]) -> bool:
    """Case-insensitive substring match (mirrors old benchmark scorer)."""
    kw_low = keyword.lower()
    return any(kw_low in k.lower() for k in keyword_list)


def score_image(ollama_keywords: list[str], oracle: dict) -> dict:
    """Score Ollama output against oracle consensus (Claude ∩ GPT agreement).

    For whitelist categories: count hits where both oracles agree AND Ollama matches.
    For free-text (objekte): fuzzy overlap between Ollama keywords and oracle objects.
    """
    claude = oracle["claude"]
    gpt = oracle["gpt"]
    scores = {"checks_passed": 0, "checks_total": 0, "details": {}}

    # Whitelist single-choice fields
    for field in ("tageszeit", "jahreszeit", "perspektive"):
        c_val = claude.get(field)
        g_val = gpt.get(field)
        if c_val and g_val and c_val == g_val:
            hit = keyword_in_list(c_val, ollama_keywords)
            scores["details"][field] = {"expected": c_val, "found": hit}
            scores["checks_total"] += 1
            if hit:
                scores["checks_passed"] += 1

    # Whitelist multi-label fields
    for field in ("wetter", "stimmung", "lichtsituation", "technik"):
        c_vals = set(claude.get(field) or [])
        g_vals = set(gpt.get(field) or [])
        agreed = c_vals & g_vals
        for val in agreed:
            hit = keyword_in_list(val, ollama_keywords)
            scores["details"][f"{field}:{val}"] = hit
            scores["checks_total"] += 1
            if hit:
                scores["checks_passed"] += 1

    # Free-text: objekte overlap (both oracles have it, check fuzzy match)
    c_obj = claude.get("objekte") or []
    g_obj = gpt.get("objekte") or []
    if c_obj and g_obj:
        all_oracle_obj = set(o.lower() for o in c_obj) | set(o.lower() for o in g_obj)
        ollama_low = [k.lower() for k in ollama_keywords]
        obj_hits = sum(1 for o in all_oracle_obj if any(o in k or k in o for k in ollama_low))
        scores["details"]["objekte_union"] = len(all_oracle_obj)
        scores["details"]["objekte_hits"] = obj_hits

    return scores


def run_scoring(manifest: list[dict]) -> None:
    print(f"\n{'=' * 70}")
    print("PHASE 2: SCORING")
    print(f"{'=' * 70}\n")

    # Pre-load all oracle labels
    oracles: dict[str, dict] = {}
    for entry in manifest:
        sha1 = entry["sha1"]
        oracle = load_oracle_labels(sha1)
        if oracle:
            oracles[sha1] = oracle
    print(f"Oracle labels available: {len(oracles)}/{len(manifest)}")

    results_all = {}

    for model in MODELS:
        checkpoint = load_checkpoint(model)
        images = checkpoint.get("images", {})
        if not images:
            print(f"\n{model}: no inference data found, skipping.")
            continue

        model_scores = []
        category_scores: dict[str, list] = {}

        for sha1, oracle in oracles.items():
            if sha1 not in images:
                continue
            img_data = images[sha1]
            if img_data.get("error"):
                continue
            keywords = img_data.get("keywords", [])
            cat = img_data.get("category", "unknown")

            score = score_image(keywords, oracle)
            score["sha1"] = sha1
            score["category"] = cat
            model_scores.append(score)

            category_scores.setdefault(cat, []).append(score)

        if not model_scores:
            print(f"\n{model}: no scorable images (missing oracle labels?).")
            continue

        total_passed = sum(s["checks_passed"] for s in model_scores)
        total_checks = sum(s["checks_total"] for s in model_scores)
        pct = total_passed / total_checks * 100 if total_checks else 0

        total_obj_hits = sum(s["details"].get("objekte_hits", 0) for s in model_scores)
        total_obj_union = sum(s["details"].get("objekte_union", 0) for s in model_scores)
        obj_pct = total_obj_hits / total_obj_union * 100 if total_obj_union else 0

        avg_time = sum(
            images[s["sha1"]]["elapsed_sec"]
            for s in model_scores if s["sha1"] in images
        ) / len(model_scores)

        print(f"\n{'─' * 50}")
        print(f"{model}")
        print(f"  Images scored:       {len(model_scores)}")
        print(f"  Whitelist accuracy:  {total_passed}/{total_checks} ({pct:.1f}%)")
        print(f"  Object recall:       {total_obj_hits}/{total_obj_union} ({obj_pct:.1f}%)")
        print(f"  Avg time/image:      {avg_time:.1f}s")

        # Per-category breakdown
        print(f"  {'Category':<25s} {'WL-Acc':>8s} {'Obj-Recall':>12s} {'N':>4s}")
        for cat in sorted(category_scores):
            cat_scores = category_scores[cat]
            cp = sum(s["checks_passed"] for s in cat_scores)
            ct = sum(s["checks_total"] for s in cat_scores)
            oh = sum(s["details"].get("objekte_hits", 0) for s in cat_scores)
            ou = sum(s["details"].get("objekte_union", 0) for s in cat_scores)
            wl = f"{cp}/{ct}" if ct else "—"
            obj = f"{oh}/{ou}" if ou else "—"
            print(f"  {cat:<25s} {wl:>8s} {obj:>12s} {len(cat_scores):>4d}")

        results_all[model] = {
            "images_scored": len(model_scores),
            "whitelist_passed": total_passed,
            "whitelist_total": total_checks,
            "whitelist_pct": round(pct, 1),
            "object_hits": total_obj_hits,
            "object_union": total_obj_union,
            "object_pct": round(obj_pct, 1),
            "avg_sec": round(avg_time, 1),
            "per_category": {
                cat: {
                    "n": len(scores),
                    "wl_passed": sum(s["checks_passed"] for s in scores),
                    "wl_total": sum(s["checks_total"] for s in scores),
                    "obj_hits": sum(s["details"].get("objekte_hits", 0) for s in scores),
                    "obj_union": sum(s["details"].get("objekte_union", 0) for s in scores),
                }
                for cat, scores in sorted(category_scores.items())
            },
        }

    # Write scoring summary
    score_path = OUT_DIR / "scoring_summary.json"
    score_path.write_text(json.dumps(results_all, indent=2, ensure_ascii=False))
    print(f"\nScoring summary saved to {score_path}")

    # Leaderboard
    print(f"\n{'=' * 70}")
    print("LEADERBOARD")
    print(f"{'=' * 70}")
    print(f"{'Model':<22s} {'WL-Acc':>10s} {'Obj-Recall':>12s} {'Avg sec':>9s} {'N':>5s}")
    print("─" * 60)
    ranked = sorted(results_all.items(), key=lambda x: x[1]["whitelist_pct"], reverse=True)
    for model, r in ranked:
        print(
            f"{model:<22s} "
            f"{r['whitelist_pct']:>8.1f}%  "
            f"{r['object_pct']:>9.1f}%  "
            f"{r['avg_sec']:>7.1f}s  "
            f"{r['images_scored']:>5d}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Extended benchmark (487 images)")
    parser.add_argument("--no-score", action="store_true", help="skip scoring phase")
    parser.add_argument("--score-only", action="store_true", help="skip inference, only score")
    parser.add_argument("--limit", type=int, help="cap images per model (for testing)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    if not manifest:
        print(f"ERROR: empty manifest at {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)

    if args.limit:
        manifest = manifest[:args.limit]
        print(f"[TEST MODE] Limited to {args.limit} images\n")

    if not args.score_only:
        run_inference(manifest)

    if not args.no_score:
        run_scoring(manifest)


if __name__ == "__main__":
    main()
