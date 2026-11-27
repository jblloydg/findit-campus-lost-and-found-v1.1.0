import os

from django.core.exceptions import ValidationError

MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def validate_photo(file):
    # A photo already saved on an existing post was checked when it was
    # uploaded. Skip it so editing an old post never needs to reopen the file
    # (which would fail if the file is missing from MEDIA_ROOT).
    if getattr(file, "_committed", False):
        return
    if file.size > MAX_PHOTO_BYTES:
        raise ValidationError("Choose an image smaller than 5 MB.")
    extension = os.path.splitext(getattr(file, "name", "") or "")[1].lower()
    if extension and extension not in ALLOWED_PHOTO_EXTENSIONS:
        raise ValidationError("Upload a JPG, PNG, or WebP exterior photo.")
    content_type = getattr(file, "content_type", "")
    if content_type and content_type not in ALLOWED_PHOTO_TYPES:
        raise ValidationError("Upload a JPG, PNG, or WebP exterior photo.")
