"""FastAPI HTTP entrypoint for Office Dispatch Workbench MVP (Phase 2C).

The default app uses module-level in-memory service/repository state from
``backend.services.dispatch_service``. This is suitable for local testing only
and will be replaced by a persistent MySQL-backed repository in later phases.
"""

from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, HTTPException

from backend.api import dispatch as dispatch_api
from backend.services.service_factory import build_runtime_dispatch_service_from_env


def create_app(service: Any | None = None) -> FastAPI:
    """Create a FastAPI app wired to thin dispatch API wrapper functions."""
    app = FastAPI(title="Office Dispatch Workbench API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/dispatch/batches")
    def list_batches() -> list[dict[str, Any]]:
        return _resolve_and_call(service, lambda resolved_service: dispatch_api.list_batches(service=resolved_service))

    @app.post("/api/dispatch/batches")
    def create_batch(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return _handle_value_error(
            lambda: _resolve_and_call(
                service,
                lambda resolved_service: dispatch_api.create_batch(payload, service=resolved_service),
            )
        )

    @app.get("/api/dispatch/batches/{batch_id}")
    def get_batch(batch_id: int) -> dict[str, Any]:
        return _handle_value_error(
            lambda: _resolve_and_call(
                service,
                lambda resolved_service: dispatch_api.get_batch(batch_id, service=resolved_service),
            )
        )

    @app.get("/api/dispatch/batches/{batch_id}/orders")
    def list_batch_orders(batch_id: int) -> list[dict[str, Any]]:
        return _handle_value_error(
            lambda: _resolve_and_call(
                service,
                lambda resolved_service: dispatch_api.list_batch_orders(batch_id, service=resolved_service),
            )
        )

    @app.post("/api/dispatch/batches/{batch_id}/orders")
    def save_batch_orders(batch_id: int, payload: Any = Body(...)) -> list[dict[str, Any]]:
        return _handle_value_error(
            lambda: _resolve_and_call(
                service,
                lambda resolved_service: dispatch_api.save_batch_orders(batch_id, payload, service=resolved_service),
            )
        )

    @app.post("/api/dispatch/batches/{batch_id}/generate")
    def generate_batch_plan(batch_id: int) -> dict[str, Any]:
        # Response contract must remain: plans / order_assignments / exceptions.
        return _handle_value_error(
            lambda: _resolve_and_call(
                service,
                lambda resolved_service: dispatch_api.generate_batch_plan(batch_id, service=resolved_service),
            )
        )

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


def _resolve_and_call(explicit_service: Any | None, action: Any) -> Any:
    resolved_service = explicit_service
    should_close = False
    if resolved_service is None:
        resolved_service = build_runtime_dispatch_service_from_env()
        should_close = resolved_service is not None
    try:
        return action(resolved_service)
    finally:
        if should_close:
            _close_service(resolved_service)


def _close_service(service: Any) -> None:
    repository = getattr(service, "repository", None)
    close_fn = getattr(repository, "close", None)
    if callable(close_fn):
        close_fn()


app = create_app()
