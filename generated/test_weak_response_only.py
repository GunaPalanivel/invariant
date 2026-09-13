"""Weak handwritten control: response-only. test_origin: weak_control.

Labeled weak. It does not inspect observer state. Do not treat this as a coding agent.
"""
from __future__ import annotations

import unittest

from apps.notifier.notifier import ReleaseNotifier
from invariant.harness import make_session

DESTINATION = 'C-RELEASES'
OPERATION_ID = 'release-note-v42'
CONTENT = 'Release v42 shipped to production.'


class WeakResponseOnlyControl(unittest.TestCase):
    def test_reports_completion_without_state(self):
        adapter, _observer, _store = make_session()
        adapter.arm_send("commit_drop_ack")
        report = ReleaseNotifier(adapter).announce(
            DESTINATION, OPERATION_ID, CONTENT, recovery="blind_retry"
        )
        self.assertTrue(report.claimed_complete)


if __name__ == "__main__":
    unittest.main()
