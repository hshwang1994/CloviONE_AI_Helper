"""Provider interfaces for future extension (spec §7.3).

Initial implementations: Local HTTP Runner Provider (M6), Webhook
Provider (M5/M6), Local Account Identity Provider (built into auth),
In-app Notification Provider (M9),
File-based Secret Reference Provider (core.secret_refs).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RunnerProvider(ABC):
    @abstractmethod
    def health_check(self, runner: Any) -> dict:
        """Return {'status': 'up'|'down', 'latency_ms': float, 'detail': str|None}."""

    @abstractmethod
    def invoke(self, runner: Any, payload: dict, *, timeout: float) -> dict:
        """Send a request to the runner and return its parsed response."""


class WorkflowProvider(ABC):
    @abstractmethod
    def invoke(self, workflow: Any, payload: dict, *, timeout: float) -> dict:
        """Call a workflow webhook and return its parsed response."""

    @abstractmethod
    def test(self, workflow: Any) -> dict:
        """Lightweight reachability test without side effects."""


class IdentityProvider(ABC):
    @abstractmethod
    def authenticate(self, email: str, password: str) -> Any | None:
        """Return the authenticated principal or None."""


class NotificationProvider(ABC):
    @abstractmethod
    def notify(self, user_id: str, *, type_: str, title: str, body: str, related: tuple[str, str] | None = None) -> None:
        """Deliver a notification to a user."""


class DocumentProvider(ABC):
    @abstractmethod
    def create_document(self, config: dict, payload: dict, *, preview_only: bool) -> dict:
        """Create (or preview) a document; returns result metadata."""


class SecretReferenceProvider(ABC):
    @abstractmethod
    def status(self, name: str) -> str: ...

    @abstractmethod
    def get(self, name: str) -> Any | None: ...
