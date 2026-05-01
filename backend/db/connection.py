"""Database connection placeholder.

Phase 1 intentionally avoids introducing runtime DB dependencies.
"""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    database: str


def load_db_config() -> DbConfig:
    """Load DB connection settings from environment variables."""
    return DbConfig(
        host=os.getenv("OFFICE_DISPATCH_DB_HOST", "localhost"),
        port=int(os.getenv("OFFICE_DISPATCH_DB_PORT", "3306")),
        user=os.getenv("OFFICE_DISPATCH_DB_USER", "root"),
        database=os.getenv("OFFICE_DISPATCH_DB_NAME", "office_dispatch"),
    )


def get_connection() -> None:
    """Return DB connection in later phases."""
    raise NotImplementedError("Database runtime connection is planned for Phase 2+.")

