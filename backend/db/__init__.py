"""Database package for Office Dispatch backend."""

from .repository import DispatchRepository, InMemoryDispatchRepository

__all__ = ["DispatchRepository", "InMemoryDispatchRepository"]
