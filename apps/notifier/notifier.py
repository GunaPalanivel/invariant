"""Release notifier entrypoint. Tests import this module, not the grader."""

from __future__ import annotations

from apps.notifier.adapter import SlackAdapter
from apps.notifier.policies import POLICIES, RecoveryReport


class ReleaseNotifier:
    def __init__(self, adapter: SlackAdapter) -> None:
        self.adapter = adapter

    def announce(
        self,
        destination: str,
        operation_id: str,
        content: str,
        recovery: str = "reconcile",
    ) -> RecoveryReport:
        try:
            fn = POLICIES[recovery]
        except KeyError as exc:
            raise ValueError(f"unknown recovery policy: {recovery}") from exc
        return fn(self.adapter, destination, operation_id, content)
