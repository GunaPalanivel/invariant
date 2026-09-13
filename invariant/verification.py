"""Verification binding: SHA + test hash + workflow + attempt + required outcomes."""

from __future__ import annotations

from invariant.models import VerificationRecord


def records_bind(expected: VerificationRecord, observed: VerificationRecord) -> bool:
    return (
        expected.workflow_id == observed.workflow_id
        and expected.run_attempt == observed.run_attempt
        and expected.aut_revision == observed.aut_revision
        and expected.generated_test_hash == observed.generated_test_hash
        and expected.required_outcomes == observed.required_outcomes
    )


def ci_may_inherit(*, head_sha: str, aut_revision: str, blob_hash: str, test_hash: str) -> bool:
    return head_sha == aut_revision and blob_hash == test_hash
