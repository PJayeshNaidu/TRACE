"""Unit tests for ItemService."""

from app.services import ItemService


def test_service_initialization():
    """Verify service initial state."""
    service = ItemService()
    assert service.ping() == "pong"
    assert len(service.get_items()) == 0


def test_create_item():
    """Verify item creation."""
    service = ItemService()
    item = service.create_item("Test Widget", "A widget for testing")
    assert item.title == "Test Widget"
    assert len(service.get_items()) == 1
