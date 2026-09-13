"""Generate AUT-bound tests from a model-derived contract. Scoring keys are not read here."""

from __future__ import annotations

import argparse
import ast
import os
import re
import unittest
from dataclasses import dataclass
from pathlib import Path

from invariant.hashing import ROOT, sha256_text
from invariant.interpret import interpret_incident, load_incident
from invariant.llm import LLMClient
from invariant.models import ModelDerivedContract

GENERATED_DIR = ROOT / "generated"

TEMPLATE = '''"""Generated AUT regression. test_origin: generated.

Imports the notifier entrypoint. Does not import scoring keys or grader checks.
"""
from __future__ import annotations

import unittest

from apps.notifier.notifier import ReleaseNotifier
from invariant.assertions import (
    committed_resolved_once,
    completes_missing_work,
    legitimate_second_op_allowed,
    no_duplicate_for_operation,
    unknown_after_ambiguous_dispatch,
)
from invariant.harness import make_session
from invariant.models import ExecutionResultClass

DESTINATION = {destination!r}
OPERATION_ID = {operation_id!r}
CONTENT = {content!r}
CONTRACT_HASH = {contract_hash!r}


def _run(policy: str, fault: str | None, query: str | None, operation_id: str = OPERATION_ID):
    adapter, observer, _store = make_session()
    adapter.arm_send(fault)
    adapter.arm_query(query)
    report = ReleaseNotifier(adapter).announce(DESTINATION, operation_id, CONTENT, recovery=policy)
    return adapter, observer, report


class GeneratedAutRegression(unittest.TestCase):
    def test_original_bug_duplicate_is_a_finding(self):
        _adapter, observer, report = _run("blind_retry", "commit_drop_ack", None)
        result = no_duplicate_for_operation(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_FAILED)

    def test_incomplete_repair_empty_page_is_a_finding(self):
        _adapter, observer, report = _run("search_then_retry", "commit_drop_ack", "truncated_empty")
        result = no_duplicate_for_operation(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_FAILED)

    def test_blanket_stop_leaves_missing_work(self):
        _adapter, observer, report = _run("blanket_stop", "block_before_dispatch", None)
        result = completes_missing_work(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_FAILED)

    def test_correct_committed_no_duplicate(self):
        _adapter, observer, report = _run("reconcile", "commit_drop_ack", "complete")
        result = committed_resolved_once(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)

    def test_correct_never_dispatched_send_once(self):
        _adapter, observer, report = _run("reconcile", "block_before_dispatch", None)
        result = completes_missing_work(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)

    def test_legitimate_new_operation_same_text(self):
        new_op = OPERATION_ID + "-followup"
        _adapter, observer, report = _run("reconcile", None, None, operation_id=new_op)
        result = legitimate_second_op_allowed(observer, DESTINATION, new_op, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)

    def test_unknown_after_dispatch_incomplete_read(self):
        _adapter, observer, report = _run("reconcile", "commit_drop_ack", "truncated_empty")
        result = unknown_after_ambiguous_dispatch(observer, DESTINATION, OPERATION_ID, CONTENT, report)
        self.assertEqual(result.result_class, ExecutionResultClass.INTENDED_ASSERTION_PASSED)
        self.assertEqual(result.application_outcome.value, "unknown")
        self.assertEqual(observer.count(DESTINATION, OPERATION_ID, CONTENT), 1)
        self.assertEqual(report.send_attempts, 1)


if __name__ == "__main__":
    unittest.main()
'''

WEAK_CONTROL = '''"""Weak handwritten control: response-only. test_origin: weak_control.

Labeled weak. It does not inspect observer state. Do not treat this as a coding agent.
"""
from __future__ import annotations

import unittest

from apps.notifier.notifier import ReleaseNotifier
from invariant.harness import make_session

DESTINATION = {destination!r}
OPERATION_ID = {operation_id!r}
CONTENT = {content!r}


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
'''


GENERATE_SYSTEM_PROMPT = """You write a Python unittest module against the release notifier
application under test. Import ReleaseNotifier from apps.notifier.notifier.
Use invariant.harness.make_session as the injected test transport (not live Slack).
You may use invariant.assertions helpers if they help: no_duplicate_for_operation,
completes_missing_work, committed_resolved_once, legitimate_second_op_allowed,
unknown_after_ambiguous_dispatch.

The grounded contract fields destination, operation_id, and content are the
intended write. Cover this family with adapter-visible faults only:
arm_send('commit_drop_ack' | 'block_before_dispatch' | None) and
arm_query('truncated_empty' | 'complete' | None). Policies: blind_retry,
search_then_retry, blanket_stop, reconcile.

Do not import scoring keys, gold patches, or evaluation answers.
Do not contact Slack, Linear, or GitHub.
Return ONLY Python source, no markdown fences."""


@dataclass
class GenerationResult:
    text: str
    origin: str
    invalid_test: bool
    reason: str
    path: Path | None = None


def aut_source_bundle() -> str:
    parts = []
    for name in ("adapter.py", "policies.py", "notifier.py"):
        path = ROOT / "apps" / "notifier" / name
        parts.append(f"# {name}\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:python)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def generated_pack_executes(text: str) -> tuple[bool, str]:
    """Run the generated unittest against the AUT. Syntax-only packs are not enough."""
    namespace: dict[str, object] = {"__name__": "generated_aut_candidate"}
    try:
        exec(compile(text, "generated_aut_candidate.py", "exec"), namespace)
    except Exception as exc:
        return False, f"exec failed ({type(exc).__name__})"
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for obj in namespace.values():
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase) and obj is not unittest.TestCase:
            suite.addTests(loader.loadTestsFromTestCase(obj))
    if suite.countTestCases() < 3:
        return False, "fewer than 3 executable tests"
    result = unittest.TextTestRunner(stream=__import__("io").StringIO(), verbosity=0).run(suite)
    if result.errors or result.failures:
        return False, "generated tests errored or failed on the AUT"
    return True, "ok"


def validate_generated_python(text: str) -> tuple[bool, str]:
    banned = ("Expect" + "edIntent", "expected_" + "intent.json", "required_result_class")
    for needle in banned:
        if needle in text:
            return False, "generated tests must not contain scoring keys"
    try:
        ast.parse(text)
    except SyntaxError as exc:
        return False, f"syntax error: {exc}"
    if "ReleaseNotifier" not in text:
        return False, "missing ReleaseNotifier AUT import"
    if "make_session" not in text:
        return False, "missing injected harness make_session"
    return True, "ok"


def render_generated_tests(contract: ModelDerivedContract) -> str:
    if not contract.grounded:
        raise ValueError("refusing to generate tests from an ungrounded contract")
    if not all([contract.destination, contract.operation_id, contract.content]):
        raise ValueError("contract is missing required fields")
    return TEMPLATE.format(
        destination=contract.destination,
        operation_id=contract.operation_id,
        content=contract.content,
        contract_hash=contract.contract_hash,
    )


def generate_pack(contract: ModelDerivedContract, llm: LLMClient | None = None) -> GenerationResult:
    """Model-authored tests when llm is set; disclosed template otherwise."""
    if not contract.grounded:
        raise ValueError("refusing to generate tests from an ungrounded contract")
    if llm is None:
        text = render_generated_tests(contract)
        return GenerationResult(text, "disclosed_template", False, "no live model")
    user = (
        "GROUNDED CONTRACT JSON:\n"
        f"destination={contract.destination}\n"
        f"operation_id={contract.operation_id}\n"
        f"content={contract.content}\n"
        f"completion_rule={contract.completion_rule}\n"
        f"contract_hash={contract.contract_hash}\n\n"
        "AUT SOURCE:\n"
        f"{aut_source_bundle()}\n"
    )
    try:
        raw = llm.complete_text(GENERATE_SYSTEM_PROMPT, user, max_tokens=4000)
        text = _strip_fences(raw)
        ok, reason = validate_generated_python(text)
        if ok:
            ok, reason = generated_pack_executes(text)
        if not ok:
            fallback = render_generated_tests(contract)
            return GenerationResult(
                fallback,
                "disclosed_template",
                True,
                f"model blob invalid_test ({reason}); template used",
            )
        provider = getattr(llm, "origin_tag", None)
        origin = provider() if callable(provider) else (
            f"model:{getattr(llm, 'provider', 'model')}" if getattr(llm, "provider", None) else "model"
        )
        return GenerationResult(text, origin, False, "model-authored unittest")
    except Exception as exc:
        fallback = render_generated_tests(contract)
        return GenerationResult(
            fallback,
            "disclosed_template",
            True,
            f"model error ({type(exc).__name__}); template used",
        )


def write_generated_tests(
    contract: ModelDerivedContract,
    path: Path | None = None,
    llm: LLMClient | None = None,
) -> GenerationResult:
    path = path or (GENERATED_DIR / "test_generated_aut.py")
    path.parent.mkdir(parents=True, exist_ok=True)
    result = generate_pack(contract, llm=llm)
    write = os.environ.get("INVARIANT_WRITE_GENERATED", "1").strip().lower() not in {"0", "false", "no"}
    if write:
        path.write_text(result.text, encoding="utf-8")
        result.path = path
    return result


def write_weak_control(contract: ModelDerivedContract, path: Path | None = None) -> Path:
    path = path or (GENERATED_DIR / "test_weak_response_only.py")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        WEAK_CONTROL.format(
            destination=contract.destination,
            operation_id=contract.operation_id,
            content=contract.content,
        ),
        encoding="utf-8",
    )
    return path


def generated_hash(text: str) -> str:
    return sha256_text(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate AUT tests from an incident packet.")
    parser.add_argument("--incident", type=Path, default=ROOT / "cases" / "e4" / "incident.json")
    parser.add_argument("--out", type=Path, default=GENERATED_DIR / "test_generated_aut.py")
    args = parser.parse_args(argv)
    from invariant.interpret import interpret_incident_auto

    packet = load_incident(args.incident)
    contract, origin, _usage = interpret_incident_auto(packet)
    if not contract.grounded:
        print("ungrounded contract; not fabricating a pack")
        print("ungrounded_fields:", contract.ungrounded_fields)
        return 2
    from invariant.model_runtime import try_live_client

    result = write_generated_tests(contract, args.out, llm=try_live_client())
    write_weak_control(contract)
    print(result.path)
    print("generation_origin:", result.origin)
    print("interpret_origin:", origin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
