from typing import Any, Protocol


class EventStore(Protocol):
    """Interface for persistent event and operation history."""

    def record_event(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        ...


class WrongCaseStore(Protocol):
    """Interface for tracking failed or unexpected cases."""

    def record_wrong(
        self,
        category: str,
        payload: dict[str, Any],
    ) -> None:
        ...


class LearningStore(Protocol):
    """Interface for collecting candidate training examples."""

    def add_candidate(
        self,
        payload: dict[str, Any],
    ) -> None:
        ...


class VectorStore(Protocol):
    """Interface for future semantic retrieval."""

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
