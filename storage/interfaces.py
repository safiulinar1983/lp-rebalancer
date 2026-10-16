"""Typing contracts for storage backends.

These are ``typing.Protocol`` definitions: they describe what a store must be
able to do and are checked structurally (``isinstance`` works because the
protocols are ``runtime_checkable``). They intentionally contain no logic.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventStore(Protocol):
    """Persistent event and decision history."""

    def record_event(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> int:
        """Store an event and return its row id."""
        ...

    def record_decision(
        self,
        decision: str,
        payload: dict[str, Any],
    ) -> int:
        """Store a decision and return its row id."""
        ...

    def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent events, newest first."""
        ...

    def list_decisions(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent decisions, newest first."""
        ...


@runtime_checkable
class WrongCaseStore(Protocol):
    """Tracking of failed or unexpected cases."""

    def record_wrong(
        self,
        category: str,
        payload: dict[str, Any],
    ) -> int:
        """Store a wrong case and return its row id."""
        ...

    def update_wrong_status(self, case_id: int, status: str) -> None:
        """Move a wrong case to another status."""
        ...


@runtime_checkable
class LearningStore(Protocol):
    """Candidate training examples."""

    def add_candidate(self, payload: dict[str, Any]) -> int:
        """Store a candidate example and return its row id."""
        ...


class VectorStore(Protocol):
    """Interface for future semantic retrieval (not implemented yet)."""

    def add(
        self,
        item_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> None:
        ...

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        ...
