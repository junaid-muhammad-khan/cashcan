from django.urls import path

from . import views

urlpatterns = [
    path("me", views.me),
    path("profile", views.profile),
    path("onboarding/consent", views.onboarding_consent),
    path("onboarding/face", views.onboarding_face),
    path("onboarding/wallet", views.onboarding_wallet),
    path("dashboard", views.dashboard),
]
