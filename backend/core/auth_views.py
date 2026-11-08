from urllib.parse import urlencode

from authlib.integrations.django_client import OAuth
from django.conf import settings
from django.contrib.auth import login, logout
from django.http import Http404, HttpResponseRedirect, JsonResponse

from .models import User

oauth = OAuth()
if settings.AUTH0_ENABLED:
    oauth.register(
        "auth0",
        client_id=settings.AUTH0_CLIENT_ID,
        client_secret=settings.AUTH0_CLIENT_SECRET,
        client_kwargs={"scope": "openid profile email"},
        server_metadata_url=f"https://{settings.AUTH0_DOMAIN}/.well-known/openid-configuration",
    )


def login_view(request):
    if not settings.AUTH0_ENABLED:
        return JsonResponse({"error": "Auth0 not configured. Use /auth/dev-login in DEBUG."}, status=501)
    return oauth.auth0.authorize_redirect(request, settings.AUTH0_CALLBACK_URL)


def callback_view(request):
    if not settings.AUTH0_ENABLED:
        raise Http404
    token = oauth.auth0.authorize_access_token(request)
    info = token.get("userinfo") or {}
    sub = info["sub"]
    user, created = User.objects.get_or_create(
        auth0_sub=sub,
        defaults={"username": sub[:150], "email": info.get("email", ""),
                  "display_name": (info.get("nickname") or info.get("name") or "")[:40]},
    )
    if created:
        user.set_unusable_password()
        user.save()
    login(request, user)
    return HttpResponseRedirect(settings.FRONTEND_URL)


def logout_view(request):
    logout(request)
    if settings.AUTH0_ENABLED:
        qs = urlencode({"returnTo": settings.FRONTEND_URL, "client_id": settings.AUTH0_CLIENT_ID})
        return HttpResponseRedirect(f"https://{settings.AUTH0_DOMAIN}/v2/logout?{qs}")
    return HttpResponseRedirect(settings.FRONTEND_URL)


def dev_login_view(request):
    """Local-only shortcut so the UI works before Auth0 is set up. Never enabled when Auth0 is configured."""
    if not settings.DEBUG or settings.AUTH0_ENABLED:
        raise Http404
    # ?user=new -> a fresh user with no onboarding (to try the signup flow); default -> seeded demo user.
    name = "new" if request.GET.get("user") == "new" else "demo"
    user, created = User.objects.get_or_create(
        auth0_sub=f"dev|{name}", defaults={"username": f"dev-{name}", "email": f"{name}@example.com",
                                           "display_name": name})
    if created:
        user.set_unusable_password()
        user.save()
    login(request, user)
    return HttpResponseRedirect(settings.FRONTEND_URL)
