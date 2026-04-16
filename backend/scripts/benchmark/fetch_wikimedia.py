#!/usr/bin/env python3
"""Fetch Creative-Commons images from Wikimedia Commons for ground-truth benchmark.

Stratified sampling: each Commons category is the source for a specific
photographic Whitelist-value (e.g. 'Backlit photographs' → Gegenlicht).

Outputs:
    docs/benchmark/ground_truth/images/<category_slug>/<sha1>.jpg
    docs/benchmark/ground_truth/SOURCES.md

Idempotent: existing SHA1 files are kept, only new ones are added.
Rate-limited (0.5 s between API calls) to respect Wikimedia's usage guidelines.

Usage:
    python fetch_wikimedia.py --per-category 15 --max-total 500
    python fetch_wikimedia.py --dry-run   # only list category sizes
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import pathlib
import random
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from PIL import Image

USER_AGENT = "Mozilla/5.0 (compatible; LR-AutoTag-Benchmark/1.0; +https://github.com/maximilian-stoerzer/LR-AutoTagger)"
API_BASE = "https://commons.wikimedia.org/w/api.php"
RATE_LIMIT_S = 0.5
MAX_IMG_SIDE = 2000
JPEG_QUALITY = 85
DOWNLOAD_TIMEOUT_S = 60
API_TIMEOUT_S = 30
MAX_DOWNLOAD_BYTES = 25_000_000  # 25 MB per file hard cap

# Commons categories that act as proxy labels for our Whitelist-Werte.
# Key = output sub-folder (also used as coarse category marker in filename).
# Value = list of Commons categories to sample from (will be unioned).
CATEGORY_MAP: dict[str, list[str]] = {
    # --- Lichtsituation ---
    "gegenlicht": ["Backlighting"],
    "silhouette": ["Silhouettes"],
    "lichtstrahlen": ["Crepuscular rays"],
    "low_key": ["Low-key photography"],
    "high_key": ["High-key photography"],
    # --- Perspektive ---
    "frosch": ["Worm's-eye view"],
    "vogel": ["Bird's-eye view"],
    "draufsicht": ["Top-down photographs"],
    # --- Technik ---
    "makro": ["Macro photographs"],
    "bokeh": ["Bokeh"],
    "langzeit": ["Long exposure photography"],
    "schwarzweiss": ["Black and white photographs"],
    "bewegungsunschaerfe": ["Motion blur"],
    "infrarot": ["Infrared photography"],
    # --- Wetter ---
    "nebel": ["Fog"],
    "regen": ["Rainfall", "Photographs of rain"],
    "schnee": ["Snowfall", "Photographs of snow"],
    "gewitter": ["Thunderstorm photographs", "Lightning strikes"],
    "sonnig": ["Sunshine photographs", "Clear sky photographs"],
    # --- Jahreszeit ---
    "fruehling": ["Spring photographs", "Spring landscapes"],
    "sommer": ["Summer photographs", "Summer landscapes"],
    "herbst": ["Autumn landscapes"],
    "winter": ["Winter landscapes"],
    # --- Tageszeit / Lichtphase ---
    "goldene_stunde": ["Golden hour photography", "Golden hour photographs"],
    "blaue_stunde": ["Blue hour"],
    "nacht": ["Night photography"],
    "sonnenaufgang": ["Sunrises"],
    "sonnenuntergang": ["Sunsets"],
    # --- Coverage ---
    "portrait": ["Portrait photographs"],
    "landschaft": ["Landscapes", "Landscape photographs"],
    "strasse": ["Street photography"],
}


@dataclass
class FetchStats:
    by_category: dict[str, int] = field(default_factory=dict)
    skipped_license: int = 0
    skipped_duplicate: int = 0
    skipped_other: int = 0
    api_errors: int = 0
    total_downloaded: int = 0


@dataclass
class FetchedImage:
    sha1: str
    category: str
    title: str
    url: str
    author: str
    license: str
    license_url: str
    width: int
    height: int


def api_call(params: dict) -> dict:
    """Wikimedia API call with User-Agent and rate-limit."""
    params = {**params, "format": "json"}
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=API_TIMEOUT_S) as r:
            result = json.load(r)
    finally:
        time.sleep(RATE_LIMIT_S)
    return result


def fetch_category_members(cat_name: str, limit: int = 300) -> list[str]:
    """Return titles of File: members of a Commons category."""
    titles: list[str] = []
    cmcontinue = None
    while len(titles) < limit:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{cat_name}",
            "cmtype": "file",
            "cmlimit": min(500, limit - len(titles)),
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        try:
            result = api_call(params)
        except Exception as e:  # noqa: BLE001
            logging.warning("API error on category %r: %s", cat_name, e)
            return titles
        members = result.get("query", {}).get("categorymembers", [])
        titles.extend(m["title"] for m in members)
        cmcontinue = result.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
    return titles


def fetch_image_info(title: str) -> dict | None:
    """Return imageinfo dict with url + extmetadata for a given File: title."""
    try:
        result = api_call({
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|size|mime",
        })
    except Exception as e:  # noqa: BLE001
        logging.warning("API error on title %r: %s", title, e)
        return None
    pages = result.get("query", {}).get("pages", {})
    for page in pages.values():
        infos = page.get("imageinfo", [])
        if infos:
            return infos[0]
    return None


def parse_license(info: dict) -> tuple[str, str] | None:
    """Return (license_short, license_url) if CC-compatible, else None."""
    meta = info.get("extmetadata", {})
    short = (meta.get("LicenseShortName", {}) or {}).get("value", "")
    url = (meta.get("LicenseUrl", {}) or {}).get("value", "")
    short_lower = short.lower()
    if "cc" in short_lower or "public domain" in short_lower or "cc0" in short_lower:
        return short, url
    return None


def extract_author(info: dict) -> str:
    meta = info.get("extmetadata", {})
    raw = (meta.get("Artist", {}) or {}).get("value", "") or "unknown"
    # Commons often wraps Artist in <a> or <span> — strip tags crudely.
    import re
    cleaned = re.sub(r"<[^>]+>", "", raw).strip()
    return cleaned or "unknown"


def download_image_bytes(title: str) -> bytes:
    # Use Special:FilePath which 301-redirects to the CDN — more robust
    # than the direct upload.wikimedia.org URL (which 403s for some UAs).
    bare = title[len("File:"):] if title.startswith("File:") else title
    url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(bare)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_S) as r:
        data = r.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"file > {MAX_DOWNLOAD_BYTES} bytes")
    return data


def resize_and_encode(data: bytes) -> bytes:
    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if max(img.size) > MAX_IMG_SIDE:
        img.thumbnail((MAX_IMG_SIDE, MAX_IMG_SIDE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


def sha1_of(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def load_existing_sha1s(root: pathlib.Path) -> set[str]:
    return {p.stem for p in root.rglob("*.jpg")}


def process_category(
    slug: str,
    commons_cats: list[str],
    *,
    target: int,
    out_root: pathlib.Path,
    existing: set[str],
    stats: FetchStats,
) -> list[FetchedImage]:
    collected: list[FetchedImage] = []
    cat_dir = out_root / "images" / slug
    cat_dir.mkdir(parents=True, exist_ok=True)

    # Union of candidate titles from all mapped Commons categories.
    candidates: list[str] = []
    for cat in commons_cats:
        members = fetch_category_members(cat, limit=target * 4)
        candidates.extend(members)
    # Shuffle for variety, dedup.
    random.shuffle(candidates)
    seen_titles: set[str] = set()

    for title in candidates:
        if len(collected) >= target:
            break
        if title in seen_titles:
            continue
        seen_titles.add(title)
        info = fetch_image_info(title)
        if not info:
            stats.api_errors += 1
            continue
        if info.get("mime") not in ("image/jpeg", "image/png", "image/tiff"):
            stats.skipped_other += 1
            continue
        lic = parse_license(info)
        if lic is None:
            stats.skipped_license += 1
            continue
        url = info.get("url", "")
        if not url:
            stats.skipped_other += 1
            continue
        try:
            raw = download_image_bytes(title)
            jpg = resize_and_encode(raw)
        except Exception as e:  # noqa: BLE001
            logging.warning("download/resize failed for %r: %s", title, e)
            stats.skipped_other += 1
            continue

        sha1 = sha1_of(jpg)
        if sha1 in existing:
            stats.skipped_duplicate += 1
            continue
        existing.add(sha1)

        out_path = cat_dir / f"{sha1}.jpg"
        out_path.write_bytes(jpg)

        img_info = FetchedImage(
            sha1=sha1,
            category=slug,
            title=title,
            url=url,
            author=extract_author(info),
            license=lic[0],
            license_url=lic[1],
            width=info.get("width", 0),
            height=info.get("height", 0),
        )
        collected.append(img_info)
        stats.total_downloaded += 1
        stats.by_category[slug] = stats.by_category.get(slug, 0) + 1

    return collected


def write_sources_md(path: pathlib.Path, images: list[FetchedImage]) -> None:
    existing_header = ""
    existing_rows: list[str] = []
    if path.exists():
        text = path.read_text()
        # Simple split at our marker.
        marker = "<!-- AUTO-GENERATED BELOW — DO NOT EDIT -->"
        if marker in text:
            existing_header = text.split(marker)[0] + marker + "\n"
        else:
            existing_header = text.rstrip() + "\n\n" + marker + "\n"
    else:
        existing_header = (
            "# Ground-Truth Image Sources\n\n"
            "All images fetched from [Wikimedia Commons](https://commons.wikimedia.org) "
            "under Creative-Commons or Public-Domain licenses. Fetched via "
            "`backend/scripts/benchmark/fetch_wikimedia.py`.\n\n"
            "<!-- AUTO-GENERATED BELOW — DO NOT EDIT -->\n"
        )
    rows = [
        "\n| SHA1 | Kategorie | Commons-Titel | Autor | Lizenz |",
        "|---|---|---|---|---|",
    ]
    for img in sorted(images, key=lambda i: (i.category, i.sha1)):
        lic_cell = f"[{img.license}]({img.license_url})" if img.license_url else img.license
        title_cell = f"[{img.title}](https://commons.wikimedia.org/wiki/{urllib.parse.quote(img.title)})"
        rows.append(f"| `{img.sha1[:10]}…` | {img.category} | {title_cell} | {img.author[:50]} | {lic_cell} |")
    path.write_text(existing_header + "\n".join(rows) + "\n")


def write_manifest_jsonl(path: pathlib.Path, images: list[FetchedImage]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                try:
                    existing.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    new_shas = {i.sha1 for i in images}
    kept = [e for e in existing if e.get("sha1") not in new_shas]
    all_entries = kept + [i.__dict__ for i in images]
    all_entries.sort(key=lambda d: (d["category"], d["sha1"]))
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in all_entries) + "\n")


def dry_run() -> int:
    """Print category sizes without downloading."""
    print(f"{'Slug':<22} {'Commons':<40} Count")
    print("-" * 78)
    for slug, cats in CATEGORY_MAP.items():
        for cat in cats:
            members = fetch_category_members(cat, limit=500)
            print(f"{slug:<22} {cat:<40} {len(members):>5}")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-category", type=int, default=15, help="target images per category slug")
    parser.add_argument("--max-total", type=int, default=500, help="hard cap on total downloads")
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=pathlib.Path("docs/benchmark/ground_truth"),
        help="destination root",
    )
    parser.add_argument("--dry-run", action="store_true", help="print category sizes only, no download")
    parser.add_argument("--only", action="append", default=[], help="restrict to given category slug(s)")
    parser.add_argument("--seed", type=int, default=42, help="random seed for shuffle reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)

    if args.dry_run:
        return dry_run()

    out_root: pathlib.Path = args.output_dir
    out_root.mkdir(parents=True, exist_ok=True)
    images_root = out_root / "images"
    images_root.mkdir(exist_ok=True)

    existing = load_existing_sha1s(images_root)
    logging.info("existing files: %d (will be skipped via SHA1)", len(existing))

    stats = FetchStats()
    all_fetched: list[FetchedImage] = []

    slugs = args.only or list(CATEGORY_MAP.keys())
    for slug in slugs:
        if slug not in CATEGORY_MAP:
            logging.warning("unknown slug: %s (skipping)", slug)
            continue
        if stats.total_downloaded >= args.max_total:
            logging.info("reached --max-total=%d, stopping", args.max_total)
            break
        logging.info("=== %s (target %d) ===", slug, args.per_category)
        fetched = process_category(
            slug,
            CATEGORY_MAP[slug],
            target=args.per_category,
            out_root=out_root,
            existing=existing,
            stats=stats,
        )
        all_fetched.extend(fetched)
        logging.info("%s: %d fetched", slug, len(fetched))

    if all_fetched:
        write_sources_md(out_root / "SOURCES.md", all_fetched)
        write_manifest_jsonl(out_root / "manifest.jsonl", all_fetched)

    logging.info("=" * 60)
    logging.info("DONE. total downloaded: %d", stats.total_downloaded)
    logging.info("by category: %s", json.dumps(stats.by_category, indent=2))
    logging.info("skipped (license): %d", stats.skipped_license)
    logging.info("skipped (duplicate SHA1): %d", stats.skipped_duplicate)
    logging.info("skipped (other): %d", stats.skipped_other)
    logging.info("api errors: %d", stats.api_errors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
