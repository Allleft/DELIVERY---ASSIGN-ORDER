"""FastAPI HTTP entrypoint for Office Dispatch Workbench MVP (Phase 2C).

The default app uses module-level in-memory service/repository state from
``backend.services.dispatch_service``. This is suitable for local testing only
and will be replaced by a persistent MySQL-backed repository in later phases.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from backend.api import dispatch as dispatch_api


def create_app(service: Any | None = None) -> FastAPI:
    """Create a FastAPI app wired to thin dispatch API wrapper functions."""

    app = FastAPI(title="Office Dispatch Workbench API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/dispatch/batches")
    def list_batches() -> list[dict[str, Any]]:
        return dispatch_api.list_batches(service=service)

    @app.post("/api/dispatch/batches")
    def create_batch(payload: dict[str, Any]) -> dict[str, Any]:
        return _handle_value_error(lambda: dispatch_api.create_batch(payload, service=service))

    @app.get("/api/dispatch/batches/{batch_id}")
    def get_batch(batch_id: int) -> dict[str, Any]:
        return _handle_value_error(lambda: dispatch_api.get_batch(batch_id, service=service))

    @app.get("/api/dispatch/batches/{batch_id}/orders")
    def list_batch_orders(batch_id: int) -> list[dict[str, Any]]:
        return _handle_value_error(lambda: dispatch_api.list_batch_orders(batch_id, service=service))

    @app.post("/api/dispatch/batches/{batch_id}/orders")
    def save_batch_orders(batch_id: int, payload: Any) -> list[dict[str, Any]]:
        return _handle_value_error(lambda: dispatch_api.save_batch_orders(batch_id, payload, service=service))

    @app.post("/api/dispatch/batches/{batch_id}/generate")
    def generate_batch_plan(batch_id: int) -> dict[str, Any]:
        # Response contract must remain: plans / order_assignments / exceptions.
        return _handle_value_error(lambda: dispatch_api.generate_batch_plan(batch_id, service=service))

    return app


def _handle_value_error(action: Any) -> Any:
    try:
        return action()
    except ValueError as exc:
        detail = str(exc)
        lowered = detail.lower()
        if "missing batch" in lowered or "not found" in lowered:
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc


app = create_app()
