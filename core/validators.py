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


MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024


def validate_profile_photo(file):
    """Profile pictures: JPG, PNG, or WebP up to 2 MB."""
    if file.size > MAX_PROFILE_PHOTO_BYTES:
        raise ValidationError("Choose a profile picture smaller than 2 MB.")
    content_type = getattr(file, "content_type", "")
    if content_type and content_type not in ALLOWED_PHOTO_TYPES:
        raise ValidationError("Upload a JPG, PNG, or WebP profile picture.")


MAX_REPORT_ATTACHMENT_BYTES = 5 * 1024 * 1024
REPORT_ATTACHMENT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


def validate_report_attachment(file):
    """Report screenshots/attachments: JPG, PNG, WebP, or PDF up to 5 MB, checked by content."""
    import os

    if file.size > MAX_REPORT_ATTACHMENT_BYTES:
        raise ValidationError("Choose an attachment smaller than 5 MB.")
    extension = os.path.splitext(file.name)[1].lower()
    if extension not in REPORT_ATTACHMENT_EXTENSIONS:
        raise ValidationError("Attach a JPG, PNG, WebP screenshot, or a PDF file.")
    position = file.tell() if hasattr(file, "tell") else 0
    try:
        file.seek(0)
        if extension == ".pdf":
            if file.read(5) != b"%PDF-":
                raise ValidationError("That file is not a valid PDF.")
        else:
            from PIL import Image, UnidentifiedImageError

            try:
                with Image.open(file) as image:
                    image.verify()
                    kind = (image.format or "").upper()
            except (UnidentifiedImageError, OSError, SyntaxError):
                raise ValidationError("That file is not a valid image.")
            if kind not in {"JPEG", "PNG", "WEBP"}:
                raise ValidationError("Attach a JPG, PNG, or WebP screenshot.")
    finally:
        file.seek(position)
