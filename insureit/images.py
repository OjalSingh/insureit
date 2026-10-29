"""Image loading: downscale and re-encode so one claim stays cheap."""
import base64
import hashlib
import io
from pathlib import Path

from PIL import Image, ImageOps

MAX_EDGE = 1568


def load_image(path: Path) -> tuple[str, str]:
    """Return (base64 JPEG, sha256 of the original bytes)."""
    raw = Path(path).read_bytes()
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode(), hashlib.sha256(raw).hexdigest()
