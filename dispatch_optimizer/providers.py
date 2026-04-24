from __future__ import annotations

"""Compatibility façade for travel-time/geocoder providers.

This module intentionally re-exports the public provider surface from
`dispatch_optimizer.providers_core` so existing imports remain stable while the
implementation is split into smaller files.
"""

from .providers_core import *  # noqa: F401,F403
