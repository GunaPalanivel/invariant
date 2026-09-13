"""Release notifier entrypoint. Tests import this module, not the grader."""

from __future__ import annotations

import os

from apps.notifier.adapter import SlackAdapter
from apps.notifier.policies import POLICIES, RecoveryReport

_IMPLEMENTATION_POLICY = {
    "original": "blind_retry",
    "incomplete": "search_then_retry",
    "correct": "reconcile",
    "content_dedup": "content_dedup",
}


def _default_recovery() -> str:
    impl = os.environ.get("INVARIANT_AUT_IMPLEMENTATION", "correct")
    mapped = _IMPLEMENTATION_POLICY.get(impl, "reconcile")
    if mapped not in POLICIES:
        return "reconcile"
    return mapped


class ReleaseNotifier:
    def __init__(self, adapter: SlackAdapter) -> None:
        self.adapter = adapter

    def announce(
        self,
        destination: str,
        operation_id: str,
        content: str,
        recovery: str | None = None,
    ) -> RecoveryReport:
        chosen = recovery if recovery else _default_recovery()
        try:
            fn = POLICIES[chosen]
        except KeyError as exc:
            raise ValueError(f"unknown recovery policy: {chosen}") from exc
        return fn(self.adapter, destination, operation_id, content)
