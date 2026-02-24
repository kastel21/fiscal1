"""WebSocket URL routing for FDMS device groups."""

from django.urls import re_path

from fiscal.consumers import FDMSDashboardConsumer, FDMSDeviceConsumer

websocket_urlpatterns = [
    re_path(r"ws/fdms/device/(?P<device_id>\d+)/$", FDMSDeviceConsumer.as_asgi()),
    re_path(r"ws/fdms/dashboard/$", FDMSDashboardConsumer.as_asgi()),
]
