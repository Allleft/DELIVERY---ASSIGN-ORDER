from __future__ import annotations

"""Compatibility façade for preprocessing logic.

This module re-exports from `dispatch_optimizer.preprocess_core` so external
imports remain stable while internals are split.
"""

from .preprocess_core import *  # noqa: F401,F403
