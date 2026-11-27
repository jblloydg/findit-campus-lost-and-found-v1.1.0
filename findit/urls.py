from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Find-IT administration"
admin.site.site_title = "Find-IT"
admin.site.index_title = "Manage campus lost and found"


def _developer_only(request):
    """v1.1.1: the Django back-office (it can change any role) is for the Developer only."""
    from core.permissions import is_developer
    return request.user.is_active and request.user.is_staff and is_developer(request.user)


admin.site.has_permission = _developer_only

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("captcha/", include("captcha.urls")),
    path("", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
