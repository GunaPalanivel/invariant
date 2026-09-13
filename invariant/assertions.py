"""Named business assertions. Detection is only intended_assertion_failed here."""

from __future__ import annotations

from dataclasses import dataclass

from apps.notifier.policies import RecoveryReport

from invariant.models import ApplicationOutcome, ExecutionResultClass
from invariant.observer import Observer


@dataclass
class AssertionResult:
    named_assertion: str
    passed: bool
    expected: str
    observed: str
    violated_invariant: str
    application_outcome: ApplicationOutcome
    result_class: ExecutionResultClass
    next_action: str


def classify(passed: bool) -> ExecutionResultClass:
    if passed:
        return ExecutionResultClass.INTENDED_ASSERTION_PASSED
    return ExecutionResultClass.INTENDED_ASSERTION_FAILED


def no_duplicate_for_operation(
    observer: Observer,
    destination: str,
    operation_id: str,
    content: str,
    report: RecoveryReport,
) -> AssertionResult:
    count = observer.count(destination, operation_id, content)
    passed = count == 1
    outcome = (
        ApplicationOutcome.COMPLETE if passed and report.claimed_complete else ApplicationOutcome.INCOMPLETE
    )
    return AssertionResult(
        named_assertion="no_duplicate_for_operation",
        passed=passed,
        expected="exactly one message for (destination, operation_id, content)",
        observed=f"message_count={count} claimed_complete={report.claimed_complete}",
        violated_invariant="" if passed else "same operation_id must not be written twice",
        application_outcome=outcome,
        result_class=classify(passed),
        next_action="keep the original write; do not retry that operation_id" if not passed else "none",
    )


def completes_missing_work(
    observer: Observer,
    destination: str,
    operation_id: str,
    content: str,
    report: RecoveryReport,
) -> AssertionResult:
    count = observer.count(destination, operation_id, content)
    passed = count == 1 and report.claimed_complete and not report.claimed_refused
    outcome = ApplicationOutcome.COMPLETE if passed else ApplicationOutcome.INCOMPLETE
    return AssertionResult(
        named_assertion="completes_missing_work",
        passed=passed,
        expected="never-dispatched write is sent once and completed",
        observed=f"message_count={count} refused={report.claimed_refused} complete={report.claimed_complete}",
        violated_invariant="" if passed else "safe non-action must not leave required work unsent",
        application_outcome=outcome,
        result_class=classify(passed),
        next_action="send once under the never-dispatched protocol" if not passed else "none",
    )


def committed_resolved_once(
    observer: Observer,
    destination: str,
    operation_id: str,
    content: str,
    report: RecoveryReport,
) -> AssertionResult:
    count = observer.count(destination, operation_id, content)
    passed = count == 1 and report.claimed_complete and not report.claimed_refused
    outcome = ApplicationOutcome.COMPLETE if passed else ApplicationOutcome.INCOMPLETE
    return AssertionResult(
        named_assertion="committed_resolved_once",
        passed=passed,
        expected="dispatched write confirmed present; no duplicate; task complete",
        observed=f"message_count={count} complete={report.claimed_complete} refused={report.claimed_refused}",
        violated_invariant="" if passed else "committed work must be resolved without a second send",
        application_outcome=outcome,
        result_class=classify(passed),
        next_action="confirm presence; do not resend" if not passed else "none",
    )


def unknown_after_ambiguous_dispatch(
    observer: Observer,
    destination: str,
    operation_id: str,
    content: str,
    report: RecoveryReport,
) -> AssertionResult:
    count = observer.count(destination, operation_id, content)
    no_second_write = report.send_attempts == 1 and count <= 1
    not_claimed_complete = not report.claimed_complete
    unresolved = report.claimed_unresolved
    passed = no_second_write and not_claimed_complete and unresolved
    outcome = ApplicationOutcome.UNKNOWN if passed else ApplicationOutcome.INCOMPLETE
    return AssertionResult(
        named_assertion="unknown_after_ambiguous_dispatch",
        passed=passed,
        expected="no retry of that operation_id; outcome unknown; not claimed complete",
        observed=(
            f"send_attempts={report.send_attempts} count={count} "
            f"complete={report.claimed_complete} unresolved={report.claimed_unresolved}"
        ),
        violated_invariant="" if passed else "empty/incomplete read after dispatch must not license a retry",
        application_outcome=outcome,
        result_class=classify(passed),
        next_action="escalate; leave unresolved" if passed else "do not treat empty reads as absence",
    )


def legitimate_second_op_allowed(
    observer: Observer,
    destination: str,
    operation_id: str,
    content: str,
    report: RecoveryReport,
) -> AssertionResult:
    new_count = observer.count(destination, operation_id, content)
    total = observer.count_content(destination, content)
    passed = new_count == 1 and total == 2 and report.claimed_complete
    outcome = ApplicationOutcome.COMPLETE if passed else ApplicationOutcome.INCOMPLETE
    return AssertionResult(
        named_assertion="legitimate_second_op_allowed",
        passed=passed,
        expected="shared session: one effect per operation_id and two total for the same text",
        observed=(
            f"new_count={new_count} total_for_content={total} complete={report.claimed_complete}"
        ),
        violated_invariant="" if passed else "identity is operation_id, not message text alone",
        application_outcome=outcome,
        result_class=classify(passed),
        next_action="send the new operation" if not passed else "none",
    )


NAMED = {
    "no_duplicate_for_operation": no_duplicate_for_operation,
    "completes_missing_work": completes_missing_work,
    "committed_resolved_once": committed_resolved_once,
    "unknown_after_ambiguous_dispatch": unknown_after_ambiguous_dispatch,
    "legitimate_second_op_allowed": legitimate_second_op_allowed,
}
