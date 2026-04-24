from __future__ import annotations

"""Compatibility façade for run generation logic.

This module re-exports from `dispatch_optimizer.run_generation_core` to keep
import paths stable during incremental file splitting.
"""

from .run_generation_core import *  # noqa: F401,F403
