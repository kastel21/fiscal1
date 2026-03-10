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
from django.urls import include, path, reverse

admin.site.site_header = "FiscalFlow Administration"
admin.site.site_title = "FiscalFlow Admin"
admin.site.index_title = "FiscalFlow Administration"

from device_identity.views import onboarding_register_device
from fiscal.views_devices import onboarding_device, register_device_page
from fiscal.views_health import fdms_health
from tenants.views import create_company, select_tenant
from tenants.views_auth import login_view, logout_view
from tenants.views_admin import create_company_with_user, create_tenant_onboarding, tenant_onboarding_wizard
from tenants.views_onboarding import onboarding_company

urlpatterns = [
    path("create-company/", create_company, name="create_company"),
    path("devices/register/", register_device_page, name="register_device_page"),
    path("onboarding/company/", onboarding_company, name="onboarding_company"),
    path("onboarding/device/", onboarding_device, name="onboarding_device"),
    path("onboarding/register-device/", onboarding_register_device, name="onboarding_register_device"),
    path("admin/create-company/", create_company_with_user, name="create_company_with_user"),
    path("admin/tenant-onboarding/", create_tenant_onboarding, name="tenant_onboarding"),
    path("admin/tenant-wizard/", lambda r: redirect(reverse("tenant_wizard", kwargs={"step": 1}))),
    path("admin/tenant-wizard/<int:step>/", tenant_onboarding_wizard, name="tenant_wizard"),
    path("admin/", admin.site.urls),
    path("select-tenant/", select_tenant, name="select_tenant"),
    path("health/fdms/", fdms_health),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("", lambda r: redirect("login")),
    path("dashboard/", lambda r: redirect("fdms_dashboard")),
    path("device/", include("device_identity.urls")),
    path("offline/", include("offline.urls")),
    path("legal/", include("legal.urls")),
    path("qb/", include("quickbooks.urls")),
    path("", include("fiscal.urls")),
]
