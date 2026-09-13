# Invariant

Turns a real incident into an application regression: reject the original bug and a plausible incomplete repair, accept correct recovery, and preserve legitimate work.

This workspace is the hackathon submission. Tests bind the **application under test** (`apps/notifier`) instead of a grader. A prior prototype was inspected and rewritten; it is not in this tree.

## What is local vs live

**Injected AUT transport** is still used for the lost-ack family. That is not a live Slack 408.

**Live GitHub:** regressions publish to [`GunaPalanivel/invariant-validation`](https://github.com/GunaPalanivel/invariant-validation) (notifier + testkit + CI only). The product workspace is not that repo.

**Live Slack / Linear:** incident thread and GUN-5 evidence comment are published and reread. Object IDs are in [`docs/SUBMISSION_EVIDENCE.md`](docs/SUBMISSION_EVIDENCE.md). AUT faults stay labeled injected. See [`docs/LIVE_APPS.md`](docs/LIVE_APPS.md).

**Model:** live Gemini 3.7 Flash is attempted when `GEMINI_API_KEY` is set; Groq `openai/gpt-oss-120b` is the fallback. If both fail, generation is labeled `disclosed_template`.

## Failure family

Ambiguous external write whose acknowledgement is lost.

| Adapter-visible fact                                       | Allowed action                                |
| ---------------------------------------------------------- | --------------------------------------------- |
| Confirmed present (destination + `operation_id` + content) | Do not send that operation again              |
| Never dispatched (request not forwarded)                   | Send once                                     |
| Dispatched, ack lost, empty or truncated read              | **Unknown** — no retry of that `operation_id` |

Empty reads do not license retry after an ambiguous dispatched write.

## Layout

- `apps/notifier` — AUT. No `World` / `COMMITTED` / `ExpectedIntent`.
- `invariant/` — observer, harness, interpret/judge, generator, publication broker, evaluation.
- `cases/e4/expected_intent.json` — scoring key, hidden from generation.
- `cases/holdout/` — independently authored holdout.
- `handwritten/` — labeled `test_origin: handwritten`.
- `generated/` — AUT-bound tests from a grounded contract.
- `console/` — two-route evidence UI over `runs/*.json` (and `runs-data.js` for `file://`).

## Run locally

```bash
python -m unittest discover -s tests -v
python -m invariant.connect_check
python -m invariant.incident_thread
python -m invariant.workflow
python -m invariant.compare
python -m invariant.sensitivity
python scripts/verify_console_browser.py
```

Open `console/index.html`. Evidence console **reads** `VerificationRecord` / journal IDs; it does not recompute verdicts.

## Integrations (when authorized)

Slack: `conversations.replies`, `chat.postMessage` + `thread_ts`, metadata `event_type` `invariant_operation`, paginated `conversations.history?include_all_metadata=true`. Linear: GraphQL `commentCreate` (description preserved). GitHub REST `2026-03-10`: PR + `actions/runs?head_sha=` bound to `aut_revision` and test hash.

Until then, M0 reports `deferred` in `results/m0-access.json`.

## Naming

Product and UI: **Invariant**. Package: `invariant`.
