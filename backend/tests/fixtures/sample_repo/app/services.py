"""Business services module."""

from app.models import ItemOrm


class BaseService:
    """Base service abstraction."""

    def __init__(self) -> None:
        self._initialized = True

    def ping(self) -> str:
        """Ping base method."""
        return "pong"


class ItemService(BaseService):
    """Domain service managing items."""

    def __init__(self) -> None:
        super().__init__()
        self._items: list[ItemOrm] = []

    def create_item(self, title: str, description: str = "") -> ItemOrm:
        """Create a new item instance."""
        self.ping()
        item = ItemOrm(title=title, description=description)
        self._items.append(item)
        return item

    def get_items(self) -> list[ItemOrm]:
        """Retrieve list of items."""
        return list(self._items)
