import io

from PIL import Image

from app.config import settings


def resize_for_analysis(image_data: bytes) -> bytes:
    """Resize image so the longest side is at most IMAGE_MAX_SIDE pixels.

    Returns JPEG bytes suitable for sending to Ollama.
    """
    img = Image.open(io.BytesIO(image_data))

    max_side = settings.image_max_side
    if max(img.size) > max_side:
        ratio = max_side / max(img.size)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    # Convert to RGB if necessary (e.g. RGBA, palette)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()
