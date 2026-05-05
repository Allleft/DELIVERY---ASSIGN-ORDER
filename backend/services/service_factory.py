"""Runtime service factory helpers for Office Dispatch backend."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from backend.db.sqlite_repository import SQLiteDispatchRepository
from backend.services.dispatch_service import DispatchBatchService
from backend.services.geocoding import StaticAddressGeocoder
from dispatch_optimizer.engine import DispatchEngineConfig

logger = logging.getLogger(__name__)

_DEFAULT_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS = 0.25


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
    candidate_route_time_limit_seconds = _resolve_candidate_route_time_limit_seconds_from_env()
    geocoder = StaticAddressGeocoder(
        mapping={},
        json_path=Path(static_geocoder_path.strip()) if static_geocoder_path and static_geocoder_path.strip() else None,
    )
    return DispatchBatchService(
        repository=repository,
        address_geocoder=geocoder,
        engine_config=DispatchEngineConfig(
            candidate_route_time_limit_seconds=candidate_route_time_limit_seconds,
        ),
    )


def _resolve_candidate_route_time_limit_seconds_from_env() -> float:
    raw_value = os.getenv("OFFICE_DISPATCH_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS")
    if raw_value is None:
        return _DEFAULT_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS

    stripped = raw_value.strip()
    if not stripped:
        return _DEFAULT_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS

    try:
        parsed = float(stripped)
    except ValueError:
        logger.warning(
            "Invalid OFFICE_DISPATCH_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS=%r; falling back to %.2f.",
            raw_value,
            _DEFAULT_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS,
        )
        return _DEFAULT_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS

    if parsed <= 0:
        logger.warning(
            "Non-positive OFFICE_DISPATCH_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS=%r; falling back to %.2f.",
            raw_value,
            _DEFAULT_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS,
        )
        return _DEFAULT_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS
    return parsed
