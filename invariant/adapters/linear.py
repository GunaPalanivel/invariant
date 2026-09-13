"""Linear GraphQL broker. Append evidence with commentCreate, never overwrite description."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

LINEAR_ENDPOINT = "https://api.linear.app/graphql"

ISSUE_QUERY = """
query Issue($id: String!) {
  issue(id: $id) {
    id
    identifier
    title
    description
    url
    comments(first: 100) { nodes { id body } pageInfo { hasNextPage endCursor } }
  }
}
"""

COMMENT_CREATE = """
mutation CommentCreate($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) {
    success
    comment { id body }
  }
}
"""


class LinearError(RuntimeError):
    pass


from invariant.envload import load_env

load_env()


def _key() -> str | None:
    load_env()
    return os.environ.get("LINEAR_API_KEY")


def configured() -> bool:
    return bool(_key() and os.environ.get("LINEAR_ISSUE_ID"))


def issue_id() -> str | None:
    load_env()
    return os.environ.get("LINEAR_ISSUE_ID")


def graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    key = _key()
    if not key:
        raise LinearError("LINEAR_API_KEY is not set; live Linear is deferred")
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    headers = {
        "Authorization": key,
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(LINEAR_ENDPOINT, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LinearError(f"HTTP {exc.code} from Linear") from exc
    errors = body.get("errors") or []
    if errors:
        raise LinearError(f"Linear errors[]: {errors}")
    return body.get("data") or {}


def read_issue(issue_id: str) -> dict[str, Any]:
    data = graphql(ISSUE_QUERY, {"id": issue_id})
    issue = data.get("issue")
    if not issue:
        raise LinearError(f"issue not found: {issue_id}")
    return issue


def comment_create(issue_id: str, body: str) -> dict[str, Any]:
    data = graphql(COMMENT_CREATE, {"issueId": issue_id, "body": body})
    created = (data.get("commentCreate") or {}).get("comment")
    if not created:
        raise LinearError("commentCreate returned no comment")
    reread = read_issue(issue_id)
    if reread.get("description") is None:
        raise LinearError("issue description missing after commentCreate")
    return {"comment": created, "issue": reread}
