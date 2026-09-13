"""Generated AUT regression. test_origin: generated.

Imports the notifier entrypoint. Does not import scoring keys or grader checks.
Does not select a recovery policy; the runner selects the implementation.
"""
from __future__ import annotations

import unittest

from apps.notifier.notifier import ReleaseNotifier
from invariant.harness import make_session

DESTINATION = 'C-RELEASES'
OPERATION_ID = 'release-note-v42'
CONTENT = 'Release v42 shipped to production.'
CONTRACT_HASH = '2e9cfa5756aeca122291d720d88ce39a9f0297d11131a091904d25062c046aeb'


class GeneratedAutRegression(unittest.TestCase):
    def test_lost_ack_does_not_duplicate(self):
        adapter, observer, _store = make_session()
        adapter.arm_send("commit_drop_ack")
        adapter.arm_query("complete")
        ReleaseNotifier(adapter).announce(DESTINATION, OPERATION_ID, CONTENT)
        self.assertEqual(observer.count(DESTINATION, OPERATION_ID, CONTENT), 1)

    def test_empty_page_after_dispatch_does_not_retry(self):
        adapter, observer, _store = make_session()
        adapter.arm_send("commit_drop_ack")
        adapter.arm_query("truncated_empty")
        report = ReleaseNotifier(adapter).announce(DESTINATION, OPERATION_ID, CONTENT)
        self.assertEqual(observer.count(DESTINATION, OPERATION_ID, CONTENT), 1)
        self.assertEqual(report.send_attempts, 1)
        self.assertTrue(report.claimed_unresolved)
        self.assertFalse(report.claimed_complete)

    def test_never_dispatched_sends_once(self):
        adapter, observer, _store = make_session()
        adapter.arm_send("block_before_dispatch")
        ReleaseNotifier(adapter).announce(DESTINATION, OPERATION_ID, CONTENT)
        self.assertEqual(observer.count(DESTINATION, OPERATION_ID, CONTENT), 1)

    def test_legitimate_new_operation_same_text(self):
        adapter, observer, _store = make_session()
        notifier = ReleaseNotifier(adapter)
        notifier.announce(DESTINATION, OPERATION_ID, CONTENT)
        notifier.announce(DESTINATION, OPERATION_ID + "-followup", CONTENT)
        self.assertEqual(observer.count(DESTINATION, OPERATION_ID, CONTENT), 1)
        self.assertEqual(observer.count(DESTINATION, OPERATION_ID + "-followup", CONTENT), 1)
        self.assertEqual(observer.count_content(DESTINATION, CONTENT), 2)


if __name__ == "__main__":
    unittest.main()
