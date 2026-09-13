"""CI from another SHA or test blob does not inherit a verdict."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invariant.models import ExecutionResultClass, TestOrigin, VerificationRecord
from invariant.verification import ci_may_inherit, records_bind


def _record(**kwargs) -> VerificationRecord:
    base = dict(
        workflow_id="wf-1",
        run_attempt=1,
        aut_revision="aaa",
        generated_test_hash="bbb",
        required_outcomes={"x": 1},
        result_class=ExecutionResultClass.INTENDED_ASSERTION_FAILED,
        named_assertion="no_duplicate_for_operation",
        test_origin=TestOrigin.GENERATED,
    )
    base.update(kwargs)
    return VerificationRecord(**base)


class TestVerificationBind(unittest.TestCase):
    def test_matching_records_bind(self):
        a = _record()
        b = _record()
        self.assertTrue(records_bind(a, b))

    def test_other_sha_does_not_bind(self):
        self.assertFalse(records_bind(_record(), _record(aut_revision="other")))

    def test_other_test_hash_does_not_bind(self):
        self.assertFalse(records_bind(_record(), _record(generated_test_hash="other")))

    def test_ci_bind_requires_sha_and_blob(self):
        self.assertTrue(ci_may_inherit(head_sha="a", aut_revision="a", blob_hash="t", test_hash="t"))
        self.assertFalse(ci_may_inherit(head_sha="a", aut_revision="b", blob_hash="t", test_hash="t"))
        self.assertFalse(ci_may_inherit(head_sha="a", aut_revision="a", blob_hash="t", test_hash="u"))
