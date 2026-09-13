"""Run named AUT cases. ExpectedIntent is loaded here, not by the generator."""

from __future__ import annotations

from dataclasses import dataclass

from apps.notifier.notifier import ReleaseNotifier

from invariant.assertions import NAMED, AssertionResult
from invariant.harness import InjectedSlackAdapter, make_session
from invariant.hashing import aut_revision_hash
from invariant.models import (
    ApplicationOutcome,
    ExecutionResultClass,
    ExpectedIntent,
    OutcomeRecord,
    TestOrigin,
    VerificationRecord,
)
from invariant.observer import Observer


@dataclass
class CaseExecution:
    case_id: str
    assertion: AssertionResult
    outcome: OutcomeRecord
    verification: VerificationRecord
    report_note: str


def run_case(
    *,
    case_id: str,
    policy: str,
    fault: str | None,
    query: str | None,
    destination: str,
    operation_id: str,
    content: str,
    named_assertion: str,
    required_outcomes: dict,
    test_origin: TestOrigin,
    test_hash: str,
    workflow_id: str,
    run_attempt: int = 1,
    seed_decoy: bool = False,
) -> CaseExecution:
    adapter, observer, store = make_session()
    if seed_decoy:
        store.append("C-DECOY", operation_id, "unrelated decoy")
    adapter.arm_send(fault)
    adapter.arm_query(query)
    notifier = ReleaseNotifier(adapter)
    prior = required_outcomes.get("prior_operation_id")
    if prior:
        notifier.announce(destination, str(prior), content, recovery=policy)
    report = notifier.announce(destination, operation_id, content, recovery=policy)
    dispatched_lost = bool(report.last_send and report.last_send.dispatched and not report.last_send.acknowledged)
    outcome = observer.record(
        destination,
        operation_id,
        content,
        claimed_complete=report.claimed_complete,
        claimed_unresolved=report.claimed_unresolved,
        send_attempts=report.send_attempts,
        dispatched_then_lost=dispatched_lost,
    )
    assertion_fn = NAMED[named_assertion]
    assertion = assertion_fn(observer, destination, operation_id, content, report)
    verification = VerificationRecord(
        workflow_id=workflow_id,
        run_attempt=run_attempt,
        aut_revision=aut_revision_hash(),
        generated_test_hash=test_hash,
        required_outcomes=required_outcomes,
        result_class=assertion.result_class,
        named_assertion=named_assertion,
        test_origin=test_origin,
        application_outcome=assertion.application_outcome,
        case_id=case_id,
    )
    return CaseExecution(case_id, assertion, outcome, verification, report.note)


def run_expected_cases(
    intent: ExpectedIntent,
    *,
    test_origin: TestOrigin,
    test_hash: str,
    workflow_id: str,
    run_attempt: int = 1,
) -> list[CaseExecution]:
    results = []
    for case_id, spec in intent.cases.items():
        results.append(
            run_case(
                case_id=case_id,
                policy=spec["policy"],
                fault=spec.get("fault"),
                query=spec.get("query"),
                destination=intent.destination,
                operation_id=spec.get("operation_id", intent.operation_id),
                content=intent.content,
                named_assertion=spec["named_assertion"],
                required_outcomes={
                    "result_class": spec["required_result_class"],
                    "application_outcome": spec["required_application_outcome"],
                    **(
                        {"prior_operation_id": spec["prior_operation_id"]}
                        if spec.get("prior_operation_id")
                        else {}
                    ),
                },
                test_origin=test_origin,
                test_hash=test_hash,
                workflow_id=workflow_id,
                run_attempt=run_attempt,
                seed_decoy=bool(spec.get("seed_decoy")),
            )
        )
    return results


def result_matches_required(execution: CaseExecution) -> bool:
    required = execution.verification.required_outcomes
    return (
        execution.verification.result_class.value == required["result_class"]
        and execution.verification.application_outcome is not None
        and execution.verification.application_outcome.value == required["application_outcome"]
    )
