"""Recovery strategies inside the notifier. They receive only adapter results."""

from __future__ import annotations

from dataclasses import dataclass

from apps.notifier.adapter import (
    READ_CONFIRMED_ABSENT,
    READ_CONFIRMED_PRESENT,
    READ_UNKNOWN,
    QueryResult,
    SendResult,
    SlackAdapter,
)


@dataclass
class RecoveryReport:
    """What the application believes it did. Observer state is independent."""

    send_attempts: int
    claimed_complete: bool
    claimed_refused: bool
    claimed_unresolved: bool
    last_send: SendResult | None
    last_query: QueryResult | None
    note: str = ""


def recover_blind_retry(
    adapter: SlackAdapter,
    destination: str,
    operation_id: str,
    content: str,
) -> RecoveryReport:
    """Original bug: resend the same operation_id after any lost ack."""
    first = adapter.send(destination, content, operation_id)
    if first.acknowledged:
        return RecoveryReport(1, True, False, False, first, None, "acked")
    second = adapter.send(destination, content, operation_id)
    return RecoveryReport(
        2, True, False, False, second, None, "resent without checking state"
    )


def recover_blanket_stop(
    adapter: SlackAdapter,
    destination: str,
    operation_id: str,
    content: str,
) -> RecoveryReport:
    """Never recover after a lost ack — including when the write never left."""
    first = adapter.send(destination, content, operation_id)
    if first.acknowledged:
        return RecoveryReport(1, True, False, False, first, None, "acked")
    return RecoveryReport(
        1, False, True, False, first, None, "stopped without reconciling"
    )


def recover_search_then_retry(
    adapter: SlackAdapter,
    destination: str,
    operation_id: str,
    content: str,
) -> RecoveryReport:
    """Incomplete repair: empty message list is treated as absence.

    An empty or truncated page after a dispatched write is unknown, not
    absence. Treating len(messages)==0 as a license to resend duplicates
    a committed write when pagination or metadata is incomplete.
    """
    first = adapter.send(destination, content, operation_id)
    if first.acknowledged:
        return RecoveryReport(1, True, False, False, first, None, "acked")
    query = adapter.query_operation(destination, operation_id, content)
    if len(query.messages) == 0:
        second = adapter.send(destination, content, operation_id)
        return RecoveryReport(
            2,
            True,
            False,
            False,
            second,
            query,
            "resent because the query returned no rows",
        )
    return RecoveryReport(1, True, False, False, first, query, "found a row")


def recover_reconcile(
    adapter: SlackAdapter,
    destination: str,
    operation_id: str,
    content: str,
) -> RecoveryReport:
    """Correct recovery for this failure family."""
    first = adapter.send(destination, content, operation_id)
    if first.acknowledged:
        return RecoveryReport(1, True, False, False, first, None, "acked")
    if not first.dispatched:
        second = adapter.send(destination, content, operation_id)
        if second.acknowledged:
            return RecoveryReport(
                2, True, False, False, second, None, "never dispatched; sent once"
            )
        if not second.dispatched:
            return RecoveryReport(
                2, False, False, True, second, None, "second send also not dispatched"
            )
        return RecoveryReport(
            2, False, False, True, second, None, "second send ack lost; unresolved"
        )

    query = adapter.query_operation(destination, operation_id, content)
    if query.status == READ_CONFIRMED_PRESENT:
        return RecoveryReport(
            1, True, False, False, first, query, "confirmed present; no resend"
        )
    if query.status == READ_CONFIRMED_ABSENT:
        second = adapter.send(destination, content, operation_id)
        return RecoveryReport(
            2, second.acknowledged, False, not second.acknowledged, second, query,
            "confirmed absent under contract; sent once",
        )
    if query.status == READ_UNKNOWN:
        return RecoveryReport(
            1,
            False,
            False,
            True,
            first,
            query,
            "dispatched write with inconclusive read; no second send",
        )
    return RecoveryReport(1, False, False, True, first, query, "unrecognized read")


POLICIES = {
    "blind_retry": recover_blind_retry,
    "blanket_stop": recover_blanket_stop,
    "search_then_retry": recover_search_then_retry,
    "reconcile": recover_reconcile,
}
