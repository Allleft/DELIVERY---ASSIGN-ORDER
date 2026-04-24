from __future__ import annotations

"""Compatibility façade for assignment logic.

This module re-exports from `dispatch_optimizer.assignment_core` so downstream
imports keep using `dispatch_optimizer.assignment` during incremental refactors.
"""

from .assignment_core import *  # noqa: F401,F403
