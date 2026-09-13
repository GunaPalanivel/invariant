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
- **PublicationJournal** writes a pending intent before send. Ambiguous dispatch (timeout, HTTP 500) persists `unknown`. Restart does not create a second Slack reply, Linear comment, or GitHub PR.
- Generated tests run in an isolated subprocess with an environment allowlist. Broker tokens and a synthetic canary are not visible to the candidate.
- `pack.valid` requires the generated file's isolated matrix (original / incomplete / correct / content-dedup mutant) **and** the independent ExpectedIntent checker. The checker cannot alone make the pack valid.
- CI binding reads the test file at `head_sha` and compares that observed hash. A failed or unmatched job is not a verified execution.

## Read status

`confirmed_present` requires the object in the intended destination with matching `operation_id` and content.

`confirmed_absent_under_contract` requires adapter-visible never-dispatched, or a provider-documented non-existence check, plus a complete observation contract (channel, identity field, content, window, visibility, metadata if used, pagination exhausted).

`unknown` covers dispatched+lost ack, empty/partial history, truncated pages, omitted metadata. Unknown is never painted as pass-green.

## Three apps

1. Slack thread intake and reply (`chat.postMessage` + `thread_ts`; paginated `conversations.history` / `conversations.replies`).
2. Linear `commentCreate` on GUN-5; description is not overwritten.
3. GitHub PR 1 on `GunaPalanivel/invariant-validation`; Actions attached only when `head_sha` equals the published revision, the observed test blob hash matches, and the job completed successfully.

Live objects (reread): Slack incident `1789306404.361089` and finding `1789306699.812559`; Linear comment `d94a2b69-a255-4f44-a3a8-7f94f72d9dca`; GitHub PR 1 / Actions `34760856153`. Journal: `runs/run-release-v42/journal.json`.

## Comparison and usefulness

The weak response-only control is labeled weak; it is not a coding agent. Interpret can use a live Gemini/Groq contract. After two $0 repairs, Groq supplied a scenario spec that a deterministic compiler rendered (`scenario-compiler:model:groq`). That is not free-form model-authored unittest. The unguided Groq coding-agent blob failed construction and still omitted the required regression names after those repairs. Recorded live workflow wall time was **72 seconds** from Slack intake to mergeable PR 1 (`results/workflow.json`); the remaining clock is the operator's merge click. No superiority claim.

Holdout `ExpectedIntent` lives in `cases/holdout/` and was not supplied to the generator.

Input-sensitivity (author-prepared): changing the authorized destination to `C-STAGING` moved the derived assertion. No second PR.

## Hostile evidence

A synthetic canary in quoted incident text (`cases/hostile/`) must not expand destination or skip verification. Included only because generated AUT tests for the core family run green locally.

## Starting point

Disclosed prior prototype: inspected and rewritten so tests bind the AUT, not a grader. Product name in UI and this brief is Invariant.
