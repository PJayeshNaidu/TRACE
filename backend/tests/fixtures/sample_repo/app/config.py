"""Application configuration settings."""

import os

from pydantic import BaseModel


class AppSettings(BaseModel):
    """Pydantic configuration settings."""

    app_name: str = "SampleApp"
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    debug_mode: bool = False


settings = AppSettings()
