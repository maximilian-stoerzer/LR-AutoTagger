#!/usr/bin/env python3
"""Prepare ground-truth YAML templates for each image.

Writes one YAML stub per image into labels/, then Claude (session)
fills in the `claude` section per image. When the GPT-5 API pass runs
later, it fills in the `gpt` section. Dissens arbitration adds the
final `ground_truth` section.

Usage:
    python prepare_oracle_batch.py                     # all images
    python prepare_oracle_batch.py --category frosch   # only one category
    python prepare_oracle_batch.py --limit 20          # first 20 images
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

GT_ROOT = pathlib.Path("docs/benchmark/ground_truth")
IMAGES_ROOT = GT_ROOT / "images"
LABELS_ROOT = GT_ROOT / "labels"
MANIFEST_PATH = GT_ROOT / "manifest.jsonl"


TEMPLATE = """\
# Ground-truth labels for {sha1}.jpg
# Image source: {source_url}
# Category (Commons-proxy): {category}
#
# Each oracle fills in its own section. Fields marked REQUIRED are
# mandatory; leave as `null` when none applies.
#
# - single_choice (pick ONE from whitelist):
#     tageszeit: Morgengrauen | Morgen | Vormittag | Mittag | Nachmittag | Abend | Daemmerung | Nacht
#     jahreszeit: Fruehling | Sommer | Herbst | Winter
#     perspektive: Froschperspektive | Vogelperspektive | Draufsicht | Aufsicht | Untersicht | Schraegsicht | Normalperspektive
#
# - multi_label (0..N from whitelist):
#     wetter: Sonnig, Bewoelkt, Bedeckt, Regen, Schnee, Nebel, Gewitter, Wind, Sturm, Dunst
#     stimmung: Dramatisch, Melancholisch, Mystisch, Bedrohlich, Einsam, Vertraeumt,
#               Nostalgisch, Majestaetisch, Romantisch, Lebhaft, Froehlich, Friedlich
#     lichtsituation: Gegenlicht, Seitenlicht, Hartes Licht, Weiches Licht, Diffuses Licht,
#                     Hell-Dunkel, Silhouette, Lichtstrahlen, High-Key, Low-Key,
#                     Kantenlicht, Oberlicht, Mischlicht, Kunstlicht, Natuerliches Licht, Frontlicht
#     technik: Schwarzweiss, Makro, Bokeh, Langzeitbelichtung, Bewegungsunschaerfe, Infrarot
#
# - free_text (max counts from prompt):
#     objekte (<=5), szene (<=2), umgebung (<=2)

image_sha1: "{sha1}"
category_proxy: "{category}"
source_url: "{source_url}"

claude:
  objekte: null       # list[str] or null
  szene: null
  umgebung: null
  tageszeit: null     # single value
  jahreszeit: null
  wetter: null        # list[str]
  stimmung: null
  lichtsituation: null
  perspektive: null
  technik: null
  notes: null         # free text, only if something atypical

gpt: null             # filled by GPT-5 API pass (later)

ground_truth: null    # filled after dissens arbitration
"""


def load_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        return []
    entries = []
    for line in MANIFEST_PATH.read_text().splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--category", help="only this category slug")
    parser.add_argument("--limit", type=int, help="cap on total stubs created")
    parser.add_argument("--force", action="store_true", help="overwrite existing label files")
    args = parser.parse_args()

    manifest = load_manifest()
    if not manifest:
        print("ERROR: manifest.jsonl missing — run fetch_wikimedia.py first.", file=sys.stderr)
        return 1

    LABELS_ROOT.mkdir(parents=True, exist_ok=True)

    created = skipped = 0
    for entry in manifest:
        if args.category and entry["category"] != args.category:
            continue
        if args.limit and created >= args.limit:
            break
        sha1 = entry["sha1"]
        label_path = LABELS_ROOT / f"{sha1}.yaml"
        if label_path.exists() and not args.force:
            skipped += 1
            continue
        label_path.write_text(TEMPLATE.format(
            sha1=sha1,
            category=entry["category"],
            source_url=entry["url"],
        ))
        created += 1

    print(f"Created: {created}, skipped (existing): {skipped}")
    print(f"Total labels dir: {len(list(LABELS_ROOT.glob('*.yaml')))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
