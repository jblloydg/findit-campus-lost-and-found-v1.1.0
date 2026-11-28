import mimetypes

from django.apps import AppConfig

# BUG-010: on some Windows PCs, another program has changed the registry so that ".css" (or
# ".js") means "text/plain". Python reads those registry entries, so the local server sent
# the design file with the wrong type and browsers refused it: the pages showed with no
# design. Find-IT now always uses the standard types for its own files. On PCs that were
# already fine this changes nothing (these are the values they use anyway).
STANDARD_TYPES = {
    ".css": "text/css",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".webp": "image/webp",
    ".woff2": "font/woff2",
}


def use_standard_file_types():
    for extension, content_type in STANDARD_TYPES.items():
        mimetypes.add_type(content_type, extension, strict=True)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        use_standard_file_types()
        from . import signals  # noqa: F401
