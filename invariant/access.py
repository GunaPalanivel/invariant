"""M0 access check. Never fakes live Slack/Linear/GitHub writes."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from invariant.adapters import github, linear, slack
from invariant.envload import load_env
from invariant.hashing import ROOT

load_env()

RESULTS = ROOT / "results"


def probe() -> dict:
    from invariant.model_runtime import gemini_configured, groq_configured

    model_key = gemini_configured() or groq_configured()
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "live_apps": {
            "slack": {
                "configured": slack.configured(),
                "status": "ready" if slack.configured() else "deferred",
                "reason": None if slack.configured() else "SLACK_BOT_TOKEN missing; local fixtures only",
            },
            "linear": {
                "configured": linear.configured(),
                "status": "ready" if linear.configured() else "deferred",
                "reason": None if linear.configured() else "LINEAR_API_KEY missing; local fixtures only",
            },
            "github": {
                "configured": github.configured(),
                "status": "ready" if github.configured() else "deferred",
                "reason": None if github.configured() else "GITHUB_TOKEN missing; local journal only, no git init",
            },
        },
        "model": {
            "configured": model_key,
            "primary": os.environ.get("INVARIANT_MODEL", "gemini-3.7-flash"),
            "fallback": os.environ.get("INVARIANT_FALLBACK_MODEL", "openai/gpt-oss-120b"),
            "gemini_configured": gemini_configured(),
            "groq_configured": groq_configured(),
            "pinned": os.environ.get("INVARIANT_MODEL", "gemini-3.7-flash"),
            "status": "ready" if model_key else "deferred",
            "note": "Keys stay in the broker. Generated tests do not receive production tokens.",
        },
        "version_control": "local git initialized; product workspace is not published to invariant-validation",
        "three_app_eligibility": "blocked" if not (slack.configured() and linear.configured() and github.configured()) else "credentials_present_not_yet_authorized",
    }
    return report


def write_report(path: Path | None = None) -> dict:
    path = path or (RESULTS / "m0-access.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    report = probe()
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_report()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
