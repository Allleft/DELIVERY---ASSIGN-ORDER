from __future__ import annotations

"""Compatibility façade for dispatch engine orchestration.

This module re-exports from `dispatch_optimizer.engine_core` so existing imports
do not change while internals are being split.
"""

from .engine_core import *  # noqa: F401,F403
