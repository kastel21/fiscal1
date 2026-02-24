"""WebSocket consumers for real-time FDMS updates."""

import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger("fiscal")


class FDMSDeviceConsumer(AsyncJsonWebsocketConsumer):
    """Consumes device group fdms_device_<device_id>. Staff only."""

    async def connect(self):
        self.device_id = self.scope["url_route"]["kwargs"]["device_id"]
        self.room_group_name = f"fdms_device_{self.device_id}"
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not getattr(user, "is_staff", False):
            await self.close()
            return
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive_json(self, content):
        pass

    async def fdms_event(self, event):
        await self.send_json(event.get("data", {}))


class FDMSDashboardConsumer(AsyncJsonWebsocketConsumer):
    """Consumes fdms_dashboard group for real-time KPI metrics. Staff only."""

    async def connect(self):
        self.room_group_name = "fdms_dashboard"
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not getattr(user, "is_staff", False):
            await self.close()
            return
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive_json(self, content):
        pass

    async def fdms_event(self, event):
        await self.send_json(event.get("data", {}))
