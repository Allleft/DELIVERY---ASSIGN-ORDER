from __future__ import annotations

"""Compatibility façade for shared model definitions.

This module re-exports from `dispatch_optimizer.models_core` to keep public
imports unchanged during incremental refactors.
"""

from .models_core import *  # noqa: F401,F403
