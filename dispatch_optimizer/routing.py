from __future__ import annotations

"""Compatibility façade for routing logic.

This module re-exports from `dispatch_optimizer.routing_core` so existing
imports remain stable during incremental file splitting.
"""

from .routing_core import *  # noqa: F401,F403
