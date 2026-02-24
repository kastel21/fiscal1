"""Device identity URL configuration."""

from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register_device_view, name="device_identity_register"),
]
