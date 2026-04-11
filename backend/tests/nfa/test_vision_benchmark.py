"""Opt-in end-to-end vision benchmark.

Runs the real production prompt against a running Ollama instance on
five diverse Wikimedia-sourced test images (sunset landscape, bee
macro, city skyline at night, black & white portrait, autumn forest).
For each (model, image) pair it asserts that our parser produced a
non-empty keyword list and prints wall-time + raw Ollama timings for
post-hoc analysis.

This test is **disabled by default** because it needs:
  - a reachable Ollama at ``OLLAMA_BASE_URL``
  - the requested model(s) pulled on that server
  - **a lot of wall-time** on CPU-only Ollama (several minutes per
    image for LLaVA 13B — easy to exceed normal pytest timeouts)

Run it explicitly:

    # Default: only the configured OLLAMA_MODEL
    RUN_VISION_BENCHMARK=1 pytest backend/tests/nfa/test_vision_benchmark.py -s

    # Multiple models (comma-separated)
    RUN_VISION_BENCHMARK=1 BENCHMARK_MODELS=llava:7b,llava:13b \\
        pytest backend/tests/nfa/test_vision_benchmark.py -s

The ``-s`` flag lets pytest show the per-image timings + keyword output
live; without it the benchmark numbers are only visible on failure.
"""
import asyncio
import os
import pathlib
import time

import pytest

from app.config import settings
from app.pipeline.image_processor import resize_for_analysis
from app.pipeline.ollama_client import OllamaClient

pytestmark = [pytest.mark.performance, pytest.mark.slow]

_BENCHMARK_ENABLED = bool(os.getenv("RUN_VISION_BENCHMARK"))

_IMAGE_DIR = pathlib.Path(__file__).parent / "fixtures" / "benchmark_images"
_IMAGES = sorted(_IMAGE_DIR.glob("*.jpg")) if _IMAGE_DIR.is_dir() else []


def _models_under_test() -> list[str]:
    raw = os.getenv("BENCHMARK_MODELS")
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return [settings.ollama_model]


@pytest.mark.skipif(
    not _BENCHMARK_ENABLED,
    reason="Set RUN_VISION_BENCHMARK=1 to run the vision benchmark",
)
@pytest.mark.skipif(
    not _IMAGES,
    reason=f"Benchmark images missing in {_IMAGE_DIR}",
)
@pytest.mark.parametrize("model", _models_under_test())
@pytest.mark.parametrize("image_path", _IMAGES, ids=lambda p: p.stem)
def test_vision_end_to_end(model: str, image_path: pathlib.Path) -> None:
    """Send one image through the real Ollama pipeline and sanity-check
    the parsed keyword list.

    Assertions are intentionally permissive: we cannot make hard quality
    claims about a vision model. All we verify is that our parser
    (ollama_client._parse_keywords) turned the model's response into at
    least a few keywords — catching regressions like the
    dict-vs-array format bug that silently dropped 80 % of categories.
    """
    client = OllamaClient()
    image_data = image_path.read_bytes()
    resized = resize_for_analysis(image_data)

    t0 = time.monotonic()
    keywords = asyncio.run(client.analyze_image(resized, model=model))
    elapsed = time.monotonic() - t0

    assert keywords, f"{model} on {image_path.name}: parser returned empty"
    assert len(keywords) >= 3, (
        f"{model} on {image_path.name}: only {len(keywords)} keyword(s) "
        f"parsed — parser likely dropped categories: {keywords}"
    )

    print(
        f"\n  {model:15s} {image_path.name:25s} "
        f"{elapsed:6.1f}s  {len(keywords):2d} kws: "
        f"{', '.join(keywords[:8])}{'...' if len(keywords) > 8 else ''}",
        flush=True,
    )
