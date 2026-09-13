"""Pydantic gate for model contract JSON. Maps into existing dataclasses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from invariant.models import ModelDerivedContract, SourceSpan


class ContractSpanIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    field: str = ""
    source: str = ""
    excerpt: str = ""
    locator: str | None = None
    grounded: bool | None = None


class ContractPayloadIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    destination: str | None = None
    operation_id: str | None = None
    content: str | None = None
    completion_rule: str | None = None
    source_spans: list[ContractSpanIn] = Field(default_factory=list)
    grounded: bool | None = None
    ungrounded_fields: list[str] = Field(default_factory=list)
    contract_hash: str = ""


class JudgePayloadIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    grounded: bool = False
    reason: str = ""
    ungrounded_fields: list[str] = Field(default_factory=list)


def parse_contract_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("contract JSON must be an object")
    return ContractPayloadIn.model_validate(data).model_dump()


def parse_judge_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("judge JSON must be an object")
    return JudgePayloadIn.model_validate(data).model_dump()


def contract_from_payload(parsed: dict[str, Any], raw: str) -> ModelDerivedContract:
    payload = parse_contract_payload(parsed)
    spans = []
    for item in payload.get("source_spans") or []:
        excerpt = str(item.get("excerpt") or "")
        spans.append(
            SourceSpan(
                field=str(item.get("field") or ""),
                source=str(item.get("source") or ""),
                excerpt=excerpt,
                locator=item.get("locator"),
                grounded=bool(excerpt) and excerpt in raw,
            )
        )
    return ModelDerivedContract(
        destination=payload.get("destination"),
        operation_id=payload.get("operation_id"),
        content=payload.get("content"),
        completion_rule=payload.get("completion_rule"),
        source_spans=spans,
        grounded=False,
        ungrounded_fields=list(payload.get("ungrounded_fields") or []),
    )


def validation_error_name(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "ValidationError"
    return type(exc).__name__
