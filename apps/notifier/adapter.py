"""Application-facing Slack adapter. No hidden world labels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


READ_CONFIRMED_PRESENT = "confirmed_present"
READ_CONFIRMED_ABSENT = "confirmed_absent_under_contract"
READ_UNKNOWN = "unknown"


@dataclass(frozen=True)
class SendResult:
    """What a real client would see after chat.postMessage (or equivalent)."""

    dispatched: bool
    acknowledged: bool
    error_kind: str | None = None
    provider_id: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ObservationContract:
    destination: str
    identity_field: str
    content_predicate: str
    time_window: str
    visibility: str
    metadata_included: bool
    pagination_exhausted: bool
    pages_fetched: int
    has_more: bool
    next_cursor: str | None = None


@dataclass(frozen=True)
class PostedMessage:
    destination: str
    operation_id: str
    content: str
    provider_id: str


@dataclass(frozen=True)
class QueryResult:
    status: str
    messages: tuple[PostedMessage, ...] = field(default_factory=tuple)
    observation: ObservationContract | None = None


class SlackAdapter(Protocol):
    def send(self, destination: str, content: str, operation_id: str) -> SendResult:
        """Forward a post. dispatched=False means the request never left the client."""

    def query_operation(
        self,
        destination: str,
        operation_id: str,
        content: str,
    ) -> QueryResult:
        """History lookup scoped to destination + operation_id + content."""
