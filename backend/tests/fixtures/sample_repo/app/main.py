"""FastAPI application entrypoint."""

from fastapi import FastAPI, HTTPException

from app.services import ItemService

app = FastAPI(title="SampleApp")
service = ItemService()


@app.get("/items")
def list_items():
    """List all available items."""
    return service.get_items()


@app.post("/items")
def create_item(title: str, description: str = ""):
    """Create a new item."""
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    return service.create_item(title, description)
