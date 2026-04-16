"""Shared paths and helpers for the ground-truth benchmark scripts."""
from __future__ import annotations

import json
import pathlib

GT_ROOT = pathlib.Path("docs/benchmark/ground_truth")
IMAGES_ROOT = GT_ROOT / "images"
LABELS_ROOT = GT_ROOT / "labels"
MANIFEST_PATH = GT_ROOT / "manifest.jsonl"


def load_manifest() -> list[dict]:
    """Load manifest.jsonl entries, empty list if file is missing."""
    if not MANIFEST_PATH.is_file():
        return []
    return [json.loads(line) for line in MANIFEST_PATH.read_text().splitlines() if line.strip()]
