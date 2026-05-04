from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from halo_bridge.models import Article, SyncResult

# Adapter registry
_ADAPTERS: dict[str, type[PlatformAdapter]] = {}


def register_adapter(cls: type[PlatformAdapter]) -> type[PlatformAdapter]:
    """Decorator to register a platform adapter."""
    _ADAPTERS[cls.name] = cls
    return cls


def get_adapter(name: str) -> type[PlatformAdapter]:
    if name not in _ADAPTERS:
        from halo_bridge.exceptions import UnknownTargetError

        raise UnknownTargetError(name)
    return _ADAPTERS[name]


def list_adapters() -> list[str]:
    return list(_ADAPTERS.keys())


class PlatformAdapter(ABC):
    """Base class for all platform adapters."""

    name: str

    @abstractmethod
    def __init__(self, config) -> None: ...

    @abstractmethod
    def publish(self, article: Article) -> SyncResult:
        """Publish a new article."""
        ...

    def update(self, article: Article, post_id: str) -> SyncResult:
        """Update an existing article (optional)."""
        raise NotImplementedError(f"{self.name} does not support updating")

    def validate_config(self) -> list[str]:
        """Return list of missing config fields. Empty = valid."""
        return []
