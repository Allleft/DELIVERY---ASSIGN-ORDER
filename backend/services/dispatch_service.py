"""Dispatch service placeholder module.

Phase 1 keeps business behavior unchanged and only introduces the skeleton.
"""

from typing import Any


def generate_dispatch_for_batch(batch_id: str) -> Any:
    raise NotImplementedError("Planned for Phase 2: load batch data and call DispatchEngine.")


def update_manual_assignment(assignment_id: str, payload: dict[str, Any]) -> Any:
    raise NotImplementedError("Planned for Phase 2: manual assignment workflow.")


def lock_dispatch_batch(batch_id: str, user_name: str) -> Any:
    raise NotImplementedError("Planned for Phase 2: lock workflow with audit logging.")

