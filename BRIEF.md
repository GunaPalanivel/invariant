# Invariant — system and reliability brief

## What we built

Invariant reads a Slack incident, Linear acceptance text, and notifier code, derives a grounded contract, and produces tests against the **application** (`ReleaseNotifier.announce`), not against a hidden grader. Publication is a resumable journal across Slack, Linear, and GitHub. AUT faults remain **injected at the test transport**. Live Slack/Linear/GitHub object IDs are in [`docs/SUBMISSION_EVIDENCE.md`](docs/SUBMISSION_EVIDENCE.md).

## Failure family

Ambiguous external write, acknowledgement lost. Injected as: write forwarded then ack dropped, versus request never dispatched. Labeled on the console. Not claimed as a live Slack 408.

## Trust boundaries

- **AUT** sees only adapter results (`dispatched`, `acknowledged`, paginated query status). It never sees `World` / `COMMITTED` labels.
- **ExpectedIntent** is authored first and is not imported by interpreter, judge, generator, or the notifier.
- **Observer** records destination, `operation_id`, content, and counts independently.
- **Detection** is only `intended_assertion_failed` on the named assertion. Import errors are `invalid_test`. Timeouts are `infrastructure_failure`.
- **VerificationRecord** binds `workflow_id`, `run_attempt`, executed `aut_revision`, test hash, and required outcomes. Another SHA or blob does not inherit PASS/FAIL.
- **PublicationJournal** GETs stored IDs before writes. If a prior write is unknown, Invariant does not create a second PR, comment, or reply.
- Production tokens stay in the broker. Generated tests do not receive them.

## Read status

`confirmed_present` requires the object in the intended destination with matching `operation_id` and content.

`confirmed_absent_under_contract` requires adapter-visible never-dispatched, or a provider-documented non-existence check, plus a complete observation contract (channel, identity field, content, window, visibility, metadata if used, pagination exhausted).

`unknown` covers dispatched+lost ack, empty/partial history, truncated pages, omitted metadata. Unknown is never painted as pass-green.

## Three apps

1. Slack thread intake and reply (`chat.postMessage` + `thread_ts`; paginated `conversations.history` / `conversations.replies`).
2. Linear `commentCreate` on GUN-5; description is not overwritten.
3. GitHub PR 1 on `GunaPalanivel/invariant-validation`; Actions attached only when `head_sha` equals `aut_revision` and the executed blob hash equals the test hash.

Live objects (reread): Slack incident `1789306404.361089` and finding `1789306699.812559`; Linear comment `d94a2b69-a255-4f44-a3a8-7f94f72d9dca`; GitHub PR 1 / Actions `34760856153`. Journal: `runs/run-release-v42/journal.json`.

## Comparison and usefulness

The weak response-only control is labeled weak; it is not a coding agent. Interpret used a live Gemini/Groq contract (`model:groq+gemini`). Generated tests are `disclosed_template` after the live model blob failed AUT execution. A capable-agent attempt **ran** on Groq: the blob was not valid Python. A Groq second baseline produced valid Python that did not mention the incomplete-repair case. Minutes to reviewer-accepted regression remain the operator's merge clock on PR 1. No superiority claim.

Holdout `ExpectedIntent` lives in `cases/holdout/` and was not supplied to the generator.

Input-sensitivity (author-prepared): changing the authorized destination to `C-STAGING` moved the derived assertion. No second PR.

## Hostile evidence

A synthetic canary in quoted incident text (`cases/hostile/`) must not expand destination or skip verification. Included only because generated AUT tests for the core family run green locally.

## Starting point

Disclosed prior prototype: inspected and rewritten so tests bind the AUT, not a grader. Product name in UI and this brief is Invariant.
