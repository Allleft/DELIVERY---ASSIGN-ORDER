"""Runtime service factory helpers for Office Dispatch backend."""

from __future__ import annotations

import os
from pathlib import Path

from backend.db.sqlite_repository import SQLiteDispatchRepository
from backend.services.dispatch_service import DispatchBatchService
from backend.services.geocoding import StaticAddressGeocoder


def build_runtime_dispatch_service_from_env() -> DispatchBatchService | None:
    """Build default runtime service from environment, if configured.

    Returns None when OFFICE_DISPATCH_DB_PATH is unset/blank so callers can
    preserve existing in-memory default behavior.
    """

    raw_path = os.getenv("OFFICE_DISPATCH_DB_PATH")
    if raw_path is None:
        return None
    db_path = raw_path.strip()
    if not db_path:
        return None
    repository = SQLiteDispatchRepository(Path(db_path))
    static_geocoder_path = os.getenv("OFFICE_DISPATCH_STATIC_GEOCODER_PATH")
    geocoder = StaticAddressGeocoder(
        mapping={},
        json_path=Path(static_geocoder_path.strip()) if static_geocoder_path and static_geocoder_path.strip() else None,
    )
    return DispatchBatchService(repository=repository, address_geocoder=geocoder)
