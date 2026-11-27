"""Friendly error handling.

* Plain-text 403 responses from views (HttpResponseForbidden("...")) are shown inside the
  normal Find-IT layout, with the same short message and status code.
* Database errors that reach the top (for example "database is locked" or a lost
  PostgreSQL connection) are logged with a traceback and the user gets a clear
  503 page instead of a technical error. Nothing technical is shown to the user.
"""
import logging

from django.db import DatabaseError
from django.shortcuts import render

logger = logging.getLogger("findit.errors")


class FriendlyErrorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            response.status_code == 403
            and not getattr(response, "streaming", False)
            and response.get("Content-Type", "").startswith("text/html")
            and not getattr(response, "findit_rendered", False)
            and len(response.content) <= 300
            and b"<" not in response.content
        ):
            message = response.content.decode("utf-8", "replace").strip()
            friendly = render(request, "403.html", {"message": message}, status=403)
            friendly.findit_rendered = True
            return friendly
        return response

    def process_exception(self, request, exception):
        if isinstance(exception, DatabaseError):
            logger.exception("Database error on %s %s", request.method, request.path)
            return render(request, "503.html", status=503)
        return None


class StudentIdRequiredMiddleware:
    """v1.1.1: a student whose Student ID was cleared (another account verified it)
    must set a new one before using the rest of the site, unless an ID review is open."""

    ALLOWED_PREFIXES = (
        "/profile/student-id/", "/id-review/", "/logout/", "/verify-email/", "/notifications/", "/test-inbox/",
        "/static/", "/media/", "/captcha/", "/health/", "/profile/", "/ws/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None and user.is_authenticated
            and not request.path.startswith(self.ALLOWED_PREFIXES)
        ):
            from .verification import needs_student_id
            if needs_student_id(user):
                from django.shortcuts import redirect
                return redirect("change-student-id")
        return self.get_response(request)
