from django.urls import path

from . import auth_views

urlpatterns = [
    path("login", auth_views.login_view),
    path("callback", auth_views.callback_view),
    path("logout", auth_views.logout_view),
    path("dev-login", auth_views.dev_login_view),  # DEBUG only, when Auth0 is not configured
]
