"""Fault injection at the test transport. World labels never reach the AUT."""

from __future__ import annotations

from apps.notifier.adapter import (
    READ_CONFIRMED_ABSENT,
    READ_CONFIRMED_PRESENT,
    READ_UNKNOWN,
    ObservationContract,
    PostedMessage,
    QueryResult,
    SendResult,
)

from invariant.models import EvidenceQuality
from invariant.observer import MessageStore, Observer, StoredMessage


class InjectedSlackAdapter:
    """Implements the AUT SlackAdapter protocol.

    Faults are one-shot on the next send/query:
    - commit_drop_ack: forward the write, then drop the acknowledgement
    - block_before_dispatch: do not forward the request
    - truncated_empty / omit_metadata: incomplete observation → unknown
    """

    def __init__(self, store: MessageStore) -> None:
        self._store = store
        self._send_fault: str | None = None
        self._query_fault: str | None = None
        self.last_send_dispatched: bool | None = None
        self.send_call_count = 0
        self.query_call_count = 0

    def arm_send(self, fault: str | None) -> None:
        self._send_fault = fault

    def arm_query(self, fault: str | None) -> None:
        self._query_fault = fault

    def send(self, destination: str, content: str, operation_id: str) -> SendResult:
        self.send_call_count += 1
        fault = self._send_fault
        self._send_fault = None
        if fault == "block_before_dispatch":
            self.last_send_dispatched = False
            return SendResult(
                dispatched=False,
                acknowledged=False,
                error_kind="not_started",
                detail="injected: request was not forwarded",
            )
        msg = self._store.append(destination, operation_id, content)
        self.last_send_dispatched = True
        if fault == "commit_drop_ack":
            return SendResult(
                dispatched=True,
                acknowledged=False,
                error_kind="ack_lost",
                provider_id=msg.provider_id,
                detail="injected: write forwarded, acknowledgement dropped",
            )
        return SendResult(
            dispatched=True,
            acknowledged=True,
            provider_id=msg.provider_id,
        )

    def query_operation(
        self,
        destination: str,
        operation_id: str,
        content: str,
    ) -> QueryResult:
        self.query_call_count += 1
        fault = self._query_fault
        self._query_fault = None
        matches = [
            m
            for m in self._store.messages
            if m.destination == destination
            and m.operation_id == operation_id
            and m.content == content
        ]
        if fault == "truncated_empty":
            observation = _observation(
                destination,
                metadata_included=False,
                pagination_exhausted=False,
                pages_fetched=1,
                has_more=True,
                next_cursor="injected-cursor",
            )
            return QueryResult(status=READ_UNKNOWN, messages=(), observation=observation)
        if fault == "omit_metadata":
            observation = _observation(
                destination,
                metadata_included=False,
                pagination_exhausted=True,
                pages_fetched=1,
                has_more=False,
            )
            return QueryResult(status=READ_UNKNOWN, messages=(), observation=observation)

        posted = tuple(_to_posted(m) for m in matches)
        observation = _observation(
            destination,
            metadata_included=True,
            pagination_exhausted=True,
            pages_fetched=max(1, (len(self._store.in_destination(destination)) + 99) // 100),
            has_more=False,
        )
        if posted:
            return QueryResult(
                status=READ_CONFIRMED_PRESENT,
                messages=posted,
                observation=observation,
            )
        # After a dispatched write, a complete empty page is still unknown.
        if self.last_send_dispatched:
            return QueryResult(status=READ_UNKNOWN, messages=(), observation=observation)
        return QueryResult(
            status=READ_CONFIRMED_ABSENT,
            messages=(),
            observation=observation,
        )


def _to_posted(msg: StoredMessage) -> PostedMessage:
    return PostedMessage(
        destination=msg.destination,
        operation_id=msg.operation_id,
        content=msg.content,
        provider_id=msg.provider_id,
    )


def _observation(
    destination: str,
    *,
    metadata_included: bool,
    pagination_exhausted: bool,
    pages_fetched: int,
    has_more: bool,
    next_cursor: str | None = None,
) -> ObservationContract:
    return ObservationContract(
        destination=destination,
        identity_field="metadata.event_payload.operation_id",
        content_predicate="message.text",
        time_window="attempt_window",
        visibility="channel_members",
        metadata_included=metadata_included,
        pagination_exhausted=pagination_exhausted,
        pages_fetched=pages_fetched,
        has_more=has_more,
        next_cursor=next_cursor,
    )


def make_session() -> tuple[InjectedSlackAdapter, Observer, MessageStore]:
    store = MessageStore()
    adapter = InjectedSlackAdapter(store)
    observer = Observer(store, EvidenceQuality.INJECTED)
    return adapter, observer, store
