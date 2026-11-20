from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("design-studio/", include("design_studio.urls")),
    path("ops/", include("ops_kit.urls")),
    path("", include("tracker.urls")),
]
