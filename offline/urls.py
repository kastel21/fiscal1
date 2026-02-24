"""Offline app URLs."""

from django.urls import path

from . import views

urlpatterns = [
    path("retry/", views.retry_submit, name="offline_retry_submit"),
]