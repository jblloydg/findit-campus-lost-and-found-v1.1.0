"""Photo compression (v1.1.1, PERF-003) — Messenger style.

The uploaded original is never stored or sent. When a photo is uploaded, Find-IT saves:
* a compressed photo  (longest side at most 1600 px, about 300 KB at most), and
* a small preview      (longest side at most 480 px, about 40 KB at most) for lists,
  cards and chat-sized views.
Both are JPEG. Re-saving also removes hidden photo data (EXIF), such as the GPS
location some phones store in pictures.

Pages load text first; photos load by themselves afterwards ("lazy" loading), so a slow
photo never holds up the rest of the page.
"""
import io
import os
import uuid

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 60_000_000   # refuse absurdly large pictures ("decompression bombs")

FULL = {"max_side": 1600, "max_bytes": 300 * 1024}
PREVIEW = {"max_side": 480, "max_bytes": 40 * 1024}
AVATAR = {"max_side": 256, "max_bytes": 30 * 1024}


def _flatten(image):
    """JPEG has no transparency: put transparent pictures on white."""
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1])
        return background
    return image.convert("RGB")


def compress(source, max_side, max_bytes):
    """Return JPEG bytes no larger than max_side px and (as far as possible) max_bytes."""
    source.seek(0)
    with Image.open(source) as opened:
        image = _flatten(ImageOps.exif_transpose(opened))
    image.thumbnail((max_side, max_side), Image.LANCZOS)
    quality = 82
    while True:
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=quality, optimize=True, progressive=True)
        if buffer.tell() <= max_bytes or (quality <= 45 and min(image.size) <= 200):
            return buffer.getvalue()
        if quality > 45:
            quality -= 8
        else:
            image = image.resize((max(1, int(image.width * 0.8)), max(1, int(image.height * 0.8))), Image.LANCZOS)


def jpeg_file(data, folder_hint=""):
    return ContentFile(data, name=f"{folder_hint}{uuid.uuid4().hex}.jpg")


def replace_with_compressed(field_file, preset, preview_field=None, preview_preset=PREVIEW):
    """Compress a just-uploaded file in place (the original is dropped) and, optionally,
    fill a preview field. Returns True when something changed."""
    if not field_file or getattr(field_file, "_committed", True):
        return False
    upload = field_file.file
    full = compress(upload, **preset)
    preview = compress(io.BytesIO(full), **preview_preset) if preview_field is not None else None
    full_file = jpeg_file(full)
    field_file.save(full_file.name, full_file, save=False)
    if preview_field is not None:
        preview_file = jpeg_file(preview)
        preview_field.save(preview_file.name, preview_file, save=False)
    return True


def compress_existing(field_file, preset):
    """For photos saved before v1.1.1: compress the stored file and remove the original."""
    old_name = field_file.name
    with field_file.open("rb") as handle:
        data = compress(io.BytesIO(handle.read()), **preset)
    storage = field_file.storage
    new_name = storage.save(os.path.join(os.path.dirname(old_name), f"{uuid.uuid4().hex}.jpg"), ContentFile(data))
    if old_name != new_name:
        storage.delete(old_name)
    return new_name, data
