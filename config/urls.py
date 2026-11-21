from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("design-studio/", include("design_studio.urls")),
    path("domain/", include("domain_kit.urls")),
    path("calendar/", include("cal_kit.urls")),
    path("ops/", include("ops_kit.urls")),
]

try:
    from ops_kit.runtime import get_runtime_urlpatterns
    urlpatterns += get_runtime_urlpatterns(settings.BASE_DIR, urlpatterns)
except ImportError:
    pass

urlpatterns += [
    path("", include("tracker.urls")),
]
