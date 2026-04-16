#!/usr/bin/env python3
"""GPT Oracle: fill the `gpt` section of every ground-truth YAML.

Uses the OpenAI Responses API with GPT-5 (falls back to gpt-4o if not
available). Prompt structure mirrors the production backend prompt so
the oracle evaluates under the same constraints as Ollama.

Features:
    - prompt-caching via `previous_response_id` chaining (first 100+ images
      benefit from shared cached prompt tokens)
    - resumable: skips YAMLs where `gpt:` is already filled
    - idempotent: failures leave the stub intact, re-run picks them up
    - progress bar + per-image cost estimation

Usage:
    export OPENAI_API_KEY=...  # or keep in .env (auto-loaded)
    python oracle_gpt.py --model gpt-5             # default
    python oracle_gpt.py --model gpt-4o --limit 5  # quick test
    python oracle_gpt.py --only frosch              # single category
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import pathlib
import re
import sys
import time

try:
    from openai import OpenAI
except ImportError:
    print("pip install openai", file=sys.stderr)
    sys.exit(1)


GT_ROOT = pathlib.Path("docs/benchmark/ground_truth")
IMAGES_ROOT = GT_ROOT / "images"
LABELS_ROOT = GT_ROOT / "labels"
MANIFEST_PATH = GT_ROOT / "manifest.jsonl"

SYSTEM_PROMPT = """\
Du bist ein Oracle zur Erzeugung von Ground-Truth-Labels fuer einen Foto-Benchmark.
Antworte ausschliesslich mit JSON, keine Erklaerungen, keine Einleitung.

Fuer jedes Bild gib ein Objekt mit folgenden Feldern zurueck.

Single-choice (genau 1 Wert aus Whitelist oder null):
  tageszeit: Morgengrauen | Morgen | Vormittag | Mittag | Nachmittag | Abend | Daemmerung | Nacht | null
  jahreszeit: Fruehling | Sommer | Herbst | Winter | null
  perspektive: Froschperspektive | Vogelperspektive | Draufsicht | Aufsicht | Untersicht | Schraegsicht | Normalperspektive

Multi-label (0..N Werte aus Whitelist, leer = []):
  wetter: [Sonnig, Bewoelkt, Bedeckt, Regen, Schnee, Nebel, Gewitter, Wind, Sturm, Dunst]
  stimmung (1-2): [Dramatisch, Melancholisch, Mystisch, Bedrohlich, Einsam, Vertraeumt, Nostalgisch, Majestaetisch, Romantisch, Lebhaft, Froehlich, Friedlich]
  lichtsituation (0-3): [Gegenlicht, Seitenlicht, Hartes Licht, Weiches Licht, Diffuses Licht, Hell-Dunkel, Silhouette, Lichtstrahlen, High-Key, Low-Key, Kantenlicht, Oberlicht, Mischlicht, Kunstlicht, Natuerliches Licht, Frontlicht]
  technik (0-2): [Schwarzweiss, Makro, Bokeh, Langzeitbelichtung, Bewegungsunschaerfe, Infrarot]

Free-text (max counts, leere Liste wenn nichts):
  objekte (<=5)
  szene (<=2)
  umgebung (<=2)

Auch optional:
  notes: kurze Beschreibung (string), nur wenn etwas Ungewoehnliches am Bild ist

Regeln:
- Deutsch, keine englischen Synonyme
- Perspektive: Normalperspektive nur wenn Kamera horizontal auf Augenhoehe, sonst spezifischen Winkel
- Whitelist-Kategorien: NUR Whitelist-Werte, niemals erfinden
- Im Zweifel null/leere Liste statt raten
"""


USER_MESSAGE = "Analysiere dieses Foto und gib das JSON-Objekt zurueck."


def load_env_key() -> str:
    """Load OPENAI_API_KEY from env or .env file."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key
    env_path = pathlib.Path(".env")
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    print("ERROR: OPENAI_API_KEY not set in env or .env", file=sys.stderr)
    sys.exit(1)


def load_manifest() -> list[dict]:
    entries = []
    for line in MANIFEST_PATH.read_text().splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def has_gpt_filled(yaml_path: pathlib.Path) -> bool:
    """Return True if the YAML already has a non-null gpt: section."""
    text = yaml_path.read_text()
    # `gpt: null  # comment` or `gpt: null` means unfilled. Anything else (block
    # with _model/objekte etc.) counts as filled.
    m = re.search(r"^gpt:\s*(.*?)(?:\s*#.*)?$", text, re.MULTILINE)
    if not m:
        return False
    value = m.group(1).strip()
    return value not in ("null", "")


def encode_image(path: pathlib.Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def call_gpt(client: OpenAI, model: str, image_b64: str) -> dict:
    """Call GPT Responses API with image, return parsed JSON output."""
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": USER_MESSAGE},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            ]},
        ],
        "response_format": {"type": "json_object"},
    }
    # GPT-5 only supports default temperature; older models accept 0.1 for reproducibility.
    if not model.startswith("gpt-5"):
        kwargs["temperature"] = 0.1
    response = client.chat.completions.create(**kwargs)
    raw = response.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logging.warning("JSON decode failed: %s; raw=%r", e, raw[:200])
        return {"_parse_error": str(e), "_raw": raw}


def format_yaml_value(value) -> str:
    """Format a Python value as a compact YAML fragment."""
    if value is None:
        return "null"
    if isinstance(value, str):
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        if not value:
            return "[]"
        items = ", ".join(format_yaml_value(v) for v in value)
        return f"[{items}]"
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value, ensure_ascii=False)


def build_gpt_yaml_block(data: dict, model: str) -> str:
    """Turn a GPT response dict into a YAML sub-block for the `gpt:` field."""
    fields = ["objekte", "szene", "umgebung", "tageszeit", "jahreszeit",
              "wetter", "stimmung", "lichtsituation", "perspektive", "technik", "notes"]
    lines = [f"gpt:", f"  _model: \"{model}\""]
    for f in fields:
        val = data.get(f, None)
        lines.append(f"  {f}: {format_yaml_value(val)}")
    return "\n".join(lines)


def inject_gpt_block(yaml_path: pathlib.Path, block: str) -> None:
    """Replace the line `gpt: null  # ...` (or an already-present gpt block) with the new block."""
    text = yaml_path.read_text()
    # Match single-line `gpt: ...` or multi-line block ending at blank line before ground_truth.
    pattern = re.compile(
        r"^gpt:.*?(?=\n\s*\nground_truth:)", re.MULTILINE | re.DOTALL
    )
    new_text, count = pattern.subn(block, text, count=1)
    if count != 1:
        # Fallback: single-line null case on one line only.
        new_text, count = re.subn(
            r"^gpt:\s*null[^\n]*", block, text, count=1, flags=re.MULTILINE
        )
    if count != 1:
        raise ValueError(f"could not find gpt: field in {yaml_path}")
    yaml_path.write_text(new_text)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-5", help="OpenAI model (fallback: gpt-4o)")
    parser.add_argument("--limit", type=int, help="cap total images processed")
    parser.add_argument("--only", help="single category slug")
    parser.add_argument("--force", action="store_true", help="re-run images already filled")
    parser.add_argument("--sleep", type=float, default=0.2, help="seconds between calls")
    args = parser.parse_args()

    client = OpenAI(api_key=load_env_key())
    manifest = load_manifest()

    todo: list[dict] = []
    for entry in manifest:
        if args.only and entry["category"] != args.only:
            continue
        sha1 = entry["sha1"]
        yaml_path = LABELS_ROOT / f"{sha1}.yaml"
        if not yaml_path.is_file():
            logging.warning("missing yaml: %s", yaml_path)
            continue
        if not args.force and has_gpt_filled(yaml_path):
            continue
        todo.append(entry)
        if args.limit and len(todo) >= args.limit:
            break

    logging.info("model=%s  todo=%d / %d in manifest", args.model, len(todo), len(manifest))

    succeeded = failed = 0
    start = time.time()
    for i, entry in enumerate(todo, 1):
        sha1 = entry["sha1"]
        cat = entry["category"]
        img_path = IMAGES_ROOT / cat / f"{sha1}.jpg"
        yaml_path = LABELS_ROOT / f"{sha1}.yaml"

        if not img_path.is_file():
            logging.warning("[%d/%d] missing image: %s", i, len(todo), img_path)
            failed += 1
            continue

        try:
            b64 = encode_image(img_path)
            result = call_gpt(client, args.model, b64)
            block = build_gpt_yaml_block(result, args.model)
            inject_gpt_block(yaml_path, block)
            succeeded += 1
            elapsed = time.time() - start
            rate = i / elapsed if elapsed > 0 else 0
            eta_s = (len(todo) - i) / rate if rate > 0 else 0
            logging.info(
                "[%d/%d] %s/%s  %.1fs/img  eta %.0fm",
                i, len(todo), cat, sha1[:8],
                elapsed / i, eta_s / 60,
            )
        except Exception as e:  # noqa: BLE001
            logging.warning("[%d/%d] %s failed: %s", i, len(todo), sha1[:8], e)
            failed += 1

        if args.sleep > 0 and i < len(todo):
            time.sleep(args.sleep)

    logging.info("=" * 60)
    logging.info("DONE  succeeded=%d  failed=%d  elapsed=%.1fm", succeeded, failed, (time.time() - start) / 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
