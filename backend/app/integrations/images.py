"""Photo scrubbing: verify it is really an image, drop EXIF (GPS!), cap size, re-encode."""

from __future__ import annotations

import io

from PIL import Image, ImageOps

MAX_EDGE = 1600
THUMB_EDGE = 480
# Decompression-bomb guard: refuse absurd pixel counts before decoding.
Image.MAX_IMAGE_PIXELS = 40_000_000


def scrub(data: bytes) -> tuple[bytes, bytes]:
    """Return (full_jpeg, thumb_jpeg). Raises ValueError for non-images."""
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)  # respect orientation before dropping EXIF
    except Exception as e:  # PIL raises many types
        raise ValueError("not a valid image") from e

    img = img.convert("RGB")  # also strips alpha + any embedded metadata
    full = img.copy()
    full.thumbnail((MAX_EDGE, MAX_EDGE))
    thumb = img.copy()
    thumb.thumbnail((THUMB_EDGE, THUMB_EDGE))

    def enc(im: Image.Image, q: int) -> bytes:
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True, progressive=True)  # no exif= arg
        return buf.getvalue()

    return enc(full, 85), enc(thumb, 75)
