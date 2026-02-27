# -*- coding: utf-8 -*-
"""
Unit tests for Channel Registry
"""

import pytest

from connector.channel.adapter import ChannelAdapter
from connector.channel.gateway_adapter import GatewayAdapter
from connector.channel.polling_adapter import PollingAdapter
from connector.channel.registry import ChannelRegistry, channel_registry
from connector.channel.types import (
    ChannelCapabilities,
    DeliveryMode,
    MessageType,
    StandardMessage,
    UserInfo,
)


class MockAdapter(ChannelAdapter):
    """Mock adapter for testing."""

    def __init__(self, channel_id: str, delivery_mode: DeliveryMode):
        self._channel_id = channel_id
        self._delivery_mode = delivery_mode
        self._capabilities = ChannelCapabilities()

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def display_name(self) -> str:
        return f"Mock {self._channel_id}"

    @property
    def delivery_mode(self) -> DeliveryMode:
        return self._delivery_mode

    @property
    def capabilities(self) -> ChannelCapabilities:
        return self._capabilities

    def to_standard(self, raw_message):
        return StandardMessage(platform=self._channel_id)

    def from_standard(self, message: StandardMessage):
        return {"platform": self._channel_id, "content": message.content}

    async def send_message(self, message: StandardMessage) -> bool:
        return True

    async def resolve_user(self, platform_user_id: str):
        return UserInfo(platform_user_id=platform_user_id)


class MockPollingAdapter(PollingAdapter):
    """Mock polling adapter for testing."""

    def __init__(self, channel_id: str):
        super().__init__(poll_interval=1.0)
        self._channel_id = channel_id
        self._capabilities = ChannelCapabilities()

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def display_name(self) -> str:
        return f"Mock Polling {self._channel_id}"

    @property
    def capabilities(self) -> ChannelCapabilities:
        return self._capabilities

    def to_standard(self, raw_message):
        return StandardMessage(platform=self._channel_id)

    def from_standard(self, message: StandardMessage):
        return {"platform": self._channel_id, "content": message.content}

    async def send_message(self, message: StandardMessage) -> bool:
        return True

    async def resolve_user(self, platform_user_id: str):
        return UserInfo(platform_user_id=platform_user_id)

    async def poll_messages(self):
        return []

    async def poll_and_send(self) -> int:
        return 0


class MockGatewayAdapter(GatewayAdapter):
    """Mock gateway adapter for testing."""

    def __init__(self, channel_id: str):
        super().__init__()
        self._channel_id = channel_id
        self._capabilities = ChannelCapabilities()

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def display_name(self) -> str:
        return f"Mock Gateway {self._channel_id}"

    @property
    def capabilities(self) -> ChannelCapabilities:
        return self._capabilities

    def to_standard(self, raw_message):
        return StandardMessage(platform=self._channel_id)

    def from_standard(self, message: StandardMessage):
        return {"platform": self._channel_id, "content": message.content}

    async def send_message(self, message: StandardMessage) -> bool:
        return True

    async def resolve_user(self, platform_user_id: str):
        return UserInfo(platform_user_id=platform_user_id)

    async def connect(self):
        self._connected = True

    async def disconnect(self):
        self._connected = False


class TestChannelRegistry:
    """Test ChannelRegistry class."""

    def setup_method(self):
        """Clear registry before each test."""
        channel_registry.clear()

    def test_singleton(self):
        """Test that ChannelRegistry is a singleton."""
        registry1 = ChannelRegistry()
        registry2 = ChannelRegistry()
        assert registry1 is registry2

    def test_register_adapter(self):
        """Test registering an adapter."""
        adapter = MockAdapter("test", DeliveryMode.POLLING)
        channel_registry.register(adapter)

        assert "test" in channel_registry
        assert channel_registry.get("test") is adapter
        assert len(channel_registry) == 1

    def test_register_duplicate_adapter(self):
        """Test that registering duplicate adapter overwrites."""
        adapter1 = MockAdapter("test", DeliveryMode.POLLING)
        adapter2 = MockAdapter("test", DeliveryMode.GATEWAY)
        channel_registry.register(adapter1)
        channel_registry.register(adapter2)

        assert channel_registry.get("test") is adapter2
        assert len(channel_registry) == 1

    def test_unregister_adapter(self):
        """Test unregistering an adapter."""
        adapter = MockAdapter("test", DeliveryMode.POLLING)
        channel_registry.register(adapter)
        assert "test" in channel_registry

        channel_registry.unregister("test")
        assert "test" not in channel_registry
        assert channel_registry.get("test") is None

    def test_list_all(self):
        """Test listing all adapters."""
        adapter1 = MockAdapter("test1", DeliveryMode.POLLING)
        adapter2 = MockAdapter("test2", DeliveryMode.GATEWAY)
        channel_registry.register(adapter1)
        channel_registry.register(adapter2)

        adapters = channel_registry.list_all()
        assert len(adapters) == 2
        assert adapter1 in adapters
        assert adapter2 in adapters

    def test_list_by_mode_polling(self):
        """Test listing adapters by polling mode."""
        adapter1 = MockAdapter("poll1", DeliveryMode.POLLING)
        adapter2 = MockAdapter("poll2", DeliveryMode.POLLING)
        adapter3 = MockAdapter("gate1", DeliveryMode.GATEWAY)
        channel_registry.register(adapter1)
        channel_registry.register(adapter2)
        channel_registry.register(adapter3)

        polling_adapters = channel_registry.list_by_mode(DeliveryMode.POLLING)
        assert len(polling_adapters) == 2
        assert adapter1 in polling_adapters
        assert adapter2 in polling_adapters
        assert adapter3 not in polling_adapters

    def test_list_by_mode_gateway(self):
        """Test listing adapters by gateway mode."""
        adapter1 = MockAdapter("poll1", DeliveryMode.POLLING)
        adapter2 = MockAdapter("gate1", DeliveryMode.GATEWAY)
        adapter3 = MockAdapter("gate2", DeliveryMode.GATEWAY)
        channel_registry.register(adapter1)
        channel_registry.register(adapter2)
        channel_registry.register(adapter3)

        gateway_adapters = channel_registry.list_by_mode(DeliveryMode.GATEWAY)
        assert len(gateway_adapters) == 2
        assert adapter2 in gateway_adapters
        assert adapter3 in gateway_adapters
        assert adapter1 not in gateway_adapters

    def test_list_polling(self):
        """Test listing polling adapters using type check."""
        adapter1 = MockPollingAdapter("poll1")
        adapter2 = MockPollingAdapter("poll2")
        adapter3 = MockGatewayAdapter("gate1")
        channel_registry.register(adapter1)
        channel_registry.register(adapter2)
        channel_registry.register(adapter3)

        polling_adapters = channel_registry.list_polling()
        assert len(polling_adapters) == 2
        assert all(isinstance(a, PollingAdapter) for a in polling_adapters)

    def test_list_gateway(self):
        """Test listing gateway adapters using type check."""
        adapter1 = MockPollingAdapter("poll1")
        adapter2 = MockGatewayAdapter("gate1")
        adapter3 = MockGatewayAdapter("gate2")
        channel_registry.register(adapter1)
        channel_registry.register(adapter2)
        channel_registry.register(adapter3)

        gateway_adapters = channel_registry.list_gateway()
        assert len(gateway_adapters) == 2
        assert all(isinstance(a, GatewayAdapter) for a in gateway_adapters)

    def test_clear(self):
        """Test clearing all adapters."""
        adapter1 = MockAdapter("test1", DeliveryMode.POLLING)
        adapter2 = MockAdapter("test2", DeliveryMode.GATEWAY)
        channel_registry.register(adapter1)
        channel_registry.register(adapter2)

        assert len(channel_registry) == 2
        channel_registry.clear()
        assert len(channel_registry) == 0

    def test_contains(self):
        """Test the 'in' operator."""
        adapter = MockAdapter("test", DeliveryMode.POLLING)
        channel_registry.register(adapter)

        assert "test" in channel_registry
        assert "nonexistent" not in channel_registry
