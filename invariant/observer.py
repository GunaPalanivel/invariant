"""Independent observer. AUT never sees this module."""

from __future__ import annotations

from dataclasses import dataclass, field

from invariant.models import ApplicationOutcome, EvidenceQuality, OutcomeRecord


@dataclass
class StoredMessage:
    destination: str
    operation_id: str
    content: str
    provider_id: str


@dataclass
class MessageStore:
    messages: list[StoredMessage] = field(default_factory=list)
    _seq: int = 0

    def append(self, destination: str, operation_id: str, content: str) -> StoredMessage:
        self._seq += 1
        msg = StoredMessage(
            destination=destination,
            operation_id=operation_id,
            content=content,
            provider_id=f"local.{self._seq}",
        )
        self.messages.append(msg)
        return msg

    def in_destination(self, destination: str) -> list[StoredMessage]:
        return [m for m in self.messages if m.destination == destination]

    def matching(
        self, destination: str, operation_id: str, content: str | None = None
    ) -> list[StoredMessage]:
        found = [
            m
            for m in self.messages
            if m.destination == destination and m.operation_id == operation_id
        ]
        if content is not None:
            found = [m for m in found if m.content == content]
        return found


class Observer:
    """Records destination, operation_id, content, and counts from the store."""

    def __init__(self, store: MessageStore, evidence_quality: EvidenceQuality) -> None:
        self.store = store
        self.evidence_quality = evidence_quality

    def count(self, destination: str, operation_id: str, content: str | None = None) -> int:
        return len(self.store.matching(destination, operation_id, content))

    def record(
        self,
        destination: str,
        operation_id: str,
        content: str,
        claimed_complete: bool,
        claimed_unresolved: bool,
        send_attempts: int,
        dispatched_then_lost: bool,
    ) -> OutcomeRecord:
        count = self.count(destination, operation_id, content)
        duplicate = count > 1
        if claimed_unresolved or (dispatched_then_lost and count <= 1 and not claimed_complete):
            outcome = ApplicationOutcome.UNKNOWN
        elif claimed_complete and count == 1 and not duplicate:
            outcome = ApplicationOutcome.COMPLETE
        else:
            outcome = ApplicationOutcome.INCOMPLETE
        accuracy = "matches_observer"
        if claimed_complete and count == 0:
            accuracy = "claimed_complete_with_zero_messages"
        elif claimed_complete and duplicate:
            accuracy = "claimed_complete_with_duplicate"
        return OutcomeRecord(
            destination=destination,
            operation_id=operation_id,
            content=content,
            message_count=count,
            duplicate=duplicate,
            application_outcome=outcome,
            communication_accuracy=accuracy,
            evidence_quality=self.evidence_quality,
            task_completion=outcome,
        )
