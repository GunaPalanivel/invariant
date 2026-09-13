"""Generate AUT-bound tests from a model-derived contract. Scoring keys are not read here."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from invariant.candidate_runner import evaluate_candidate_matrix
from invariant.hashing import ROOT, sha256_text
from invariant.interpret import interpret_incident, load_incident
from invariant.llm import LLMClient
from invariant.models import ModelDerivedContract

GENERATED_DIR = ROOT / "generated"
CANDIDATE_DIR = ROOT / "results" / "generation-candidates"

TEMPLATE = '''"""Generated AUT regression. test_origin: generated.

Imports the notifier entrypoint. Does not import scoring keys or grader checks.
Does not select a recovery policy; the runner selects the implementation.
"""
from __future__ import annotations

import unittest

from apps.notifier.notifier import ReleaseNotifier
from invariant.harness import make_session

DESTINATION = {destination!r}
OPERATION_ID = {operation_id!r}
CONTENT = {content!r}
CONTRACT_HASH = {contract_hash!r}


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

HARNESS_CONTRACT = """
Public test-support contract (injected transport, not live Slack):

- make_session() -> tuple[adapter, observer, store]
  Unpack: adapter, observer, _store = make_session()
  Do not treat the return value as a single object with .adapter.
- adapter.arm_send('commit_drop_ack' | 'block_before_dispatch' | None)
- adapter.arm_query('truncated_empty' | 'complete' | None)
- ReleaseNotifier(adapter).announce(destination, operation_id, content)
  Do not pass recovery=. The execution runner selects the implementation.
- observer.count(destination, operation_id, content) -> int
- observer.count_content(destination, content) -> int
"""

GENERATE_SYSTEM_PROMPT = """You write a Python unittest module against the release notifier
application under test. Import ReleaseNotifier from apps.notifier.notifier.
Use invariant.harness.make_session as the injected test transport (not live Slack).

""" + HARNESS_CONTRACT + """

The grounded contract fields destination, operation_id, and content are the
intended write. Write real regressions (assert observer counts / send_attempts),
not grader checks against result_class. Cover:
- lost ack after dispatch must not duplicate
- empty/truncated query after dispatch must not retry
- never-dispatched attempt must send once
- shared session: announce operation_id then operation_id-followup with the same
  text; one effect per operation_id and two total

Do not import scoring keys, gold patches, policies.py repairs, or evaluation answers.
Do not contact Slack, Linear, or GitHub.
Return ONLY Python source, no markdown fences."""

REPAIR_SYSTEM_PROMPT = GENERATE_SYSTEM_PROMPT + """

The previous candidate failed to execute. Fix the construction error using the
traceback. Keep the same behavioral assertions. Meaningful assertion failures
against a buggy implementation are not errors to 'fix' by weakening tests.
"""

SCENARIO_SYSTEM_PROMPT = """Return ONLY JSON for this incident family:
{"destination": str, "operation_id": str, "content": str,
 "cover_lost_ack": true, "cover_empty_page": true,
 "cover_never_dispatched": true, "cover_new_operation": true}
Use the grounded contract fields. Do not invent a different operation."""


@dataclass
class GenerationResult:
    text: str
    origin: str
    invalid_test: bool
    reason: str
    path: Path | None = None
    code_generation_origin: str = ""
    scenario_origin: str = ""


def persist_candidate(
    *,
    raw: str,
    extracted: str,
    prompt: str,
    extra: dict,
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    ident = f"{stamp}-{sha256_text(extracted or raw or prompt)[:12]}"
    path = CANDIDATE_DIR / ident
    path.mkdir(parents=True, exist_ok=True)
    (path / "prompt.txt").write_text(prompt, encoding="utf-8")
    (path / "raw.txt").write_text(raw or "", encoding="utf-8")
    (path / "extracted.py").write_text(extracted or "", encoding="utf-8")
    (path / "exec.json").write_text(json.dumps(extra, indent=2) + "\n", encoding="utf-8")
    return path


def aut_source_bundle() -> str:
    parts = []
    for name in ("adapter.py", "notifier.py"):
        path = ROOT / "apps" / "notifier" / name
        parts.append(f"# {name}\n{path.read_text(encoding='utf-8')}")
    parts.append("# harness/assertion signatures\n" + HARNESS_CONTRACT)
    return "\n\n".join(parts)


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:python)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def generated_pack_executes(text: str) -> tuple[bool, str]:
    """Run the candidate in isolated processes. In-process exec is not used."""
    matrix = evaluate_candidate_matrix(text)
    if matrix.ok:
        return True, "ok"
    prefix = "invalid_test" if matrix.invalid_test else "matrix"
    if matrix.construction_error:
        prefix = "construction"
    return False, f"{prefix}: {matrix.reason}"


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


def compile_scenario(spec: dict, contract: ModelDerivedContract) -> str:
    """Deterministic compiler for this family. Model must supply incident fields."""
    dest = spec.get("destination") or contract.destination
    op = spec.get("operation_id") or contract.operation_id
    content = spec.get("content") or contract.content
    if dest != contract.destination or op != contract.operation_id or content != contract.content:
        raise ValueError("scenario fields must match the grounded contract")
    if not all(
        [
            spec.get("cover_lost_ack"),
            spec.get("cover_empty_page"),
            spec.get("cover_never_dispatched"),
            spec.get("cover_new_operation"),
        ]
    ):
        raise ValueError("scenario must cover the full family")
    return render_generated_tests(contract)


def _contract_user_payload(contract: ModelDerivedContract) -> str:
    return (
        "GROUNDED CONTRACT JSON:\n"
        f"destination={contract.destination}\n"
        f"operation_id={contract.operation_id}\n"
        f"content={contract.content}\n"
        f"completion_rule={contract.completion_rule}\n"
        f"contract_hash={contract.contract_hash}\n\n"
        "AUT SOURCE (public interfaces only; no reference repairs):\n"
        f"{aut_source_bundle()}\n"
    )


def _try_blob(text: str, raw: str, prompt: str, origin_tag: str) -> tuple[bool, str, str]:
    persist_candidate(
        raw=raw,
        extracted=text,
        prompt=prompt,
        extra={"origin": origin_tag, "stage": "validate"},
    )
    ok, reason = validate_generated_python(text)
    if not ok:
        persist_candidate(
            raw=raw,
            extracted=text,
            prompt=prompt,
            extra={"origin": origin_tag, "ok": False, "reason": reason, "class": "construction"},
        )
        return False, reason, "construction"
    ok, reason = generated_pack_executes(text)
    persist_candidate(
        raw=raw,
        extracted=text,
        prompt=prompt,
        extra={"origin": origin_tag, "ok": ok, "reason": reason},
    )
    if ok:
        return True, reason, "ok"
    if reason.startswith("construction"):
        return False, reason, "construction"
    if reason.startswith("invalid_test"):
        return False, reason, "invalid_test"
    return False, reason, "matrix"


def generate_pack(contract: ModelDerivedContract, llm: LLMClient | None = None) -> GenerationResult:
    """Model-authored tests when llm is set; disclosed template otherwise."""
    if not contract.grounded:
        raise ValueError("refusing to generate tests from an ungrounded contract")
    template = render_generated_tests(contract)
    if llm is None:
        return GenerationResult(template, "disclosed_template", False, "no live model")
    user = _contract_user_payload(contract)
    last_reason = ""
    last_class = "construction"
    last_text = ""
    try:
        raw = llm.complete_text(GENERATE_SYSTEM_PROMPT, user, max_tokens=4000)
        text = _strip_fences(raw)
        last_text = text
        ok, last_reason, last_class = _try_blob(text, raw, GENERATE_SYSTEM_PROMPT + "\n" + user, "attempt-0")
        if ok:
            provider = getattr(llm, "origin_tag", None)
            origin = provider() if callable(provider) else (
                f"model:{getattr(llm, 'provider', 'model')}" if getattr(llm, "provider", None) else "model"
            )
            return GenerationResult(
                text, origin, False, "model-authored unittest", code_generation_origin=origin
            )
        if last_class in {"construction", "invalid_test"}:
            for attempt in (1, 2):
                repair_user = user + f"\n\nPREVIOUS TRACE/REASON:\n{last_reason}\n\nPREVIOUS SOURCE:\n{last_text}\n"
                raw = llm.complete_text(REPAIR_SYSTEM_PROMPT, repair_user, max_tokens=4000)
                text = _strip_fences(raw)
                last_text = text
                ok, last_reason, last_class = _try_blob(
                    text, raw, REPAIR_SYSTEM_PROMPT + "\n" + repair_user, f"attempt-{attempt}"
                )
                if ok:
                    provider = getattr(llm, "origin_tag", None)
                    origin = provider() if callable(provider) else (
                        f"model:{getattr(llm, 'provider', 'model')}" if getattr(llm, "provider", None) else "model"
                    )
                    return GenerationResult(
                        text,
                        origin,
                        False,
                        f"model-authored unittest after repair {attempt}",
                        code_generation_origin=origin,
                    )
        try:
            spec = llm.complete_json(SCENARIO_SYSTEM_PROMPT, user)
            compiled = compile_scenario(spec, contract)
            ok, reason = generated_pack_executes(compiled)
            persist_candidate(
                raw=json.dumps(spec),
                extracted=compiled,
                prompt=SCENARIO_SYSTEM_PROMPT,
                extra={"origin": "scenario-compiler", "ok": ok, "reason": reason},
            )
            if ok:
                provider = getattr(llm, "origin_tag", None)
                origin = provider() if callable(provider) else "model"
                return GenerationResult(
                    compiled,
                    f"scenario-compiler:{origin}",
                    False,
                    "compiled from model scenario spec",
                    code_generation_origin="deterministic_compiler",
                    scenario_origin=origin,
                )
            last_reason = f"{last_reason}; scenario compiler {reason}"
        except Exception as exc:
            last_reason = f"{last_reason}; scenario compiler {type(exc).__name__}"
        return GenerationResult(
            template,
            "disclosed_template",
            True,
            f"model blob invalid_test ({last_reason}); template used",
            code_generation_origin="disclosed_template",
        )
    except Exception as exc:
        persist_candidate(
            raw="",
            extracted="",
            prompt=user,
            extra={"origin": "model-error", "reason": type(exc).__name__},
        )
        return GenerationResult(
            template,
            "disclosed_template",
            True,
            f"model error ({type(exc).__name__}); template used",
            code_generation_origin="disclosed_template",
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
