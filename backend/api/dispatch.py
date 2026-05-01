"""Dispatch API placeholder endpoints (Phase 1 schema/bootstrap only)."""

from typing import Any


def list_batches() -> Any:
    raise NotImplementedError("Planned for Phase 2: GET /api/dispatch/batches")


def create_batch() -> Any:
    raise NotImplementedError("Planned for Phase 2: POST /api/dispatch/batches")


def get_batch(batch_id: str) -> Any:
    raise NotImplementedError("Planned for Phase 2: GET /api/dispatch/batches/{batch_id}")


def generate_batch_plan(batch_id: str) -> Any:
    raise NotImplementedError("Planned for Phase 2: POST /api/dispatch/batches/{batch_id}/generate")


def lock_batch(batch_id: str) -> Any:
    raise NotImplementedError("Planned for Phase 2: POST /api/dispatch/batches/{batch_id}/lock")

