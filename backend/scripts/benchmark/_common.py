"""Shared paths and helpers for the ground-truth benchmark scripts."""
from __future__ import annotations

import json
import pathlib
import re

GT_ROOT = pathlib.Path("docs/benchmark/ground_truth")
IMAGES_ROOT = GT_ROOT / "images"
LABELS_ROOT = GT_ROOT / "labels"
MANIFEST_PATH = GT_ROOT / "manifest.jsonl"


def load_manifest() -> list[dict]:
    """Load manifest.jsonl entries, empty list if file is missing."""
    if not MANIFEST_PATH.is_file():
        return []
    return [json.loads(line) for line in MANIFEST_PATH.read_text().splitlines() if line.strip()]


def has_section_filled(yaml_path: pathlib.Path, section: str) -> bool:
    """Return True if the YAML's `<section>:` block is filled (objekte != null).

    Handles both stub formats:
    - single-line `<section>: null  # comment` (e.g. unfilled `gpt:`)
    - multi-line block with `objekte: null` (e.g. unfilled `claude:`)
    """
    text = yaml_path.read_text()
    block_match = re.search(
        rf"^{section}:.*?(?=^\w|\Z)", text, re.MULTILINE | re.DOTALL
    )
    if not block_match:
        return False
    obj = re.search(r"^\s+objekte:\s*(.+?)(?:\s*#.*)?$", block_match.group(0), re.MULTILINE)
    return bool(obj) and obj.group(1).strip() != "null"


def has_claude_filled(yaml_path: pathlib.Path) -> bool:
    """Return True if the `claude:` block has been filled."""
    return has_section_filled(yaml_path, "claude")


def has_gpt_filled(yaml_path: pathlib.Path) -> bool:
    """Return True if the `gpt:` block has been filled."""
    return has_section_filled(yaml_path, "gpt")
