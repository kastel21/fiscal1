"""URL configuration for legal app."""

from django.urls import path

from . import views

urlpatterns = [
    path("eula/", views.eula_view, name="eula"),
    path("eula/accept/", views.accept_eula_view, name="accept_eula"),
    path("terms/", views.terms_view, name="terms"),
    path("privacy/", views.privacy_view, name="privacy"),
    path("dpa/", views.dpa_view, name="dpa"),
    path("cookies/", views.cookies_view, name="cookies"),
]
