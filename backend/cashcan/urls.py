from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # Django only serves the API and auth routes, so opening this origin (localhost:8000) used to
    # return a bare 404. Send the browser to the React app instead.
    path("", RedirectView.as_view(url=settings.FRONTEND_URL, permanent=False)),
    path("admin/", admin.site.urls),
    path("auth/", include("core.auth_urls")),
    path("api/", include("core.urls")),
]
