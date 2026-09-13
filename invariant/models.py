"""Frozen contracts. AUT code must not import ExpectedIntent or fault labels."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ReadStatus(str, Enum):
    CONFIRMED_PRESENT = "confirmed_present"
    CONFIRMED_ABSENT_UNDER_CONTRACT = "confirmed_absent_under_contract"
    UNKNOWN = "unknown"


class ExecutionResultClass(str, Enum):
    INTENDED_ASSERTION_PASSED = "intended_assertion_passed"
    INTENDED_ASSERTION_FAILED = "intended_assertion_failed"
    INVALID_TEST = "invalid_test"
    SKIPPED = "skipped"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"


class ApplicationOutcome(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"


class TestOrigin(str, Enum):
    HANDWRITTEN = "handwritten"
    GENERATED = "generated"
    WEAK_CONTROL = "weak_control"


class EvidenceQuality(str, Enum):
    LIVE = "live"
    INJECTED = "injected"
    SIMULATED = "simulated"


class PublicationStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceSpan:
    field: str
    source: str
    excerpt: str
    grounded: bool
    locator: str | None = None


@dataclass(frozen=True)
class ExpectedIntent:
    schema_version: str
    family: str
    destination: str
    operation_id: str
    content: str
    completion_rule: str
    cases: dict[str, dict[str, Any]]

    @classmethod
    def from_path(cls, path: Path) -> "ExpectedIntent":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            schema_version=data["schema_version"],
            family=data["family"],
            destination=data["destination"],
            operation_id=data["operation_id"],
            content=data["content"],
            completion_rule=data["completion_rule"],
            cases=data["cases"],
        )


@dataclass
class ModelDerivedContract:
    destination: str | None
    operation_id: str | None
    content: str | None
    completion_rule: str | None
    source_spans: list[SourceSpan]
    grounded: bool
    ungrounded_fields: list[str] = field(default_factory=list)
    contract_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass
class OutcomeRecord:
    destination: str
    operation_id: str
    content: str
    message_count: int
    duplicate: bool
    application_outcome: ApplicationOutcome
    communication_accuracy: str
    evidence_quality: EvidenceQuality
    task_completion: ApplicationOutcome | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["application_outcome"] = self.application_outcome.value
        data["evidence_quality"] = self.evidence_quality.value
        if self.task_completion is not None:
            data["task_completion"] = self.task_completion.value
        return data


@dataclass
class VerificationRecord:
    workflow_id: str
    run_attempt: int
    aut_revision: str
    generated_test_hash: str
    required_outcomes: dict[str, Any]
    result_class: ExecutionResultClass
    named_assertion: str
    test_origin: TestOrigin
    application_outcome: ApplicationOutcome | None = None
    case_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["result_class"] = self.result_class.value
        data["test_origin"] = self.test_origin.value
        if self.application_outcome is not None:
            data["application_outcome"] = self.application_outcome.value
        return data


@dataclass
class PublicationJournal:
    run_id: str
    slack_channel_id: str | None = None
    slack_thread_ts: str | None = None
    slack_reply_ts: str | None = None
    slack_reply_status: str | None = None
    linear_issue_id: str | None = None
    linear_comment_id: str | None = None
    linear_comment_status: str | None = None
    github_branch: str | None = None
    github_pr_number: int | None = None
    github_head_sha: str | None = None
    github_pr_status: str | None = None
    ci_run_id: str | None = None
    ci_bound: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PublicationJournal":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})
