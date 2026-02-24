"""
URL configuration for fdms_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

from fiscal.views_health import fdms_health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/fdms/", fdms_health),
    path("", lambda r: redirect("fdms_dashboard")),
    path("dashboard/", lambda r: redirect("fdms_dashboard")),
    path("device/", include("device_identity.urls")),
    path("offline/", include("offline.urls")),
    path("legal/", include("legal.urls")),
    path("", include("fiscal.urls")),
]
