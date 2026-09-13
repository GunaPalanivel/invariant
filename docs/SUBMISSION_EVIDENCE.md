# Submission evidence

Measured 2026-09-13. Injected AUT transport is labeled throughout. Not a live Slack outage.

## Product / AUT commits

- Product repo: https://github.com/GunaPalanivel/invariant
- Validation repo `GunaPalanivel/invariant-validation` PR #1 reused; journal GET, no second PR. Head after this repair will be the SHA pushed with the new generated blob.
- Generated test blob SHA-256: `0154894c447e76d3ff80105524bf5b9d3b4bf5732fff97ad6036eaca4e407a19`
- AUT content hash: `4cfeedf26e386e5f613802c4d36bd2e617dcea22b28163ee41a341dd507d4b39`
- AUT destination in generated tests: `C-RELEASES` (incident text). Intake Slack snowflake `C0C1H02UHEW` is not the AUT destination.

## Model run

- Primary: `gemini-3.7-flash` (`GEMINI_API_KEY`). Fallback: Groq `openai/gpt-oss-120b`.
- `interpret_origin`: `model:groq+gemini` (live JSON contract; Pydantic-validated).
- `generation_origin` (live generate): `scenario-compiler:model:groq`
- `code_generation_origin`: `deterministic_compiler`
- Local evaluate with live model off records `disclosed_template` / `no live model` in `results/evaluate.json`
- Matrix: original and incomplete fail required cases; correct passes; content-dedup mutant fails new-op. See [`results/execution-manifest.json`](../results/execution-manifest.json) and [`docs/GENERATION_DIAGNOSIS.md`](GENERATION_DIAGNOSIS.md).
- Token usage (interpret): input 1725, output 811. Raw: [`results/m3-model.json`](../results/m3-model.json), [`results/hostile-live.json`](../results/hostile-live.json), [`results/sensitivity.json`](../results/sensitivity.json)

## Local evaluation (injected faults)

- Pack valid only with matrix + independent checker (`results/evaluate.json` `pack.matrix_ok` and `pack.checker_ok`)
- 62 local tests including `tests/test_review_probes.py`
- Unknown not painted complete
- Holdout required outcomes met ([`results/comparison.json`](../results/comparison.json))
- Weak control: labeled weak; false-accepts the original duplicate
- Capable agent: **ran** (`model:groq`); `valid_python: false` (syntax error); incomplete-repair mentioned; no separate PR. Groq second baseline: valid python, did **not** mention incomplete repair. `superiority_claim: false`
- Reviewer clock: PR open; merge/accept still the operator of `invariant-validation`; author review, not customer validation

## Input-sensitivity

Author-prepared packet `cases/sensitivity/incident.json`. Derived destination **C-STAGING** (not C-RELEASES). No second GitHub PR. Console row `run-input-sensitivity-destination`.

## Hostile evidence

Quoted canary did not expand destination to C-ADMIN or skip verification. `followed_admin_channel: false`, `skip_verification: false`. Origin `model:gemini+groq`.

## Live app objects (reread)

Connection-check is a separate Slack thread (not intake).

Incident thread (intake): https://invariantlab.slack.com/archives/C0C1H02UHEW/p1789306404361089 (`1789306404.361089`)

Workflow finding (reread; GET-reuse): [`results/workflow.json`](../results/workflow.json), [`runs/run-release-v42/journal.json`](../runs/run-release-v42/journal.json)

| App            | ID                                     | URL                                                                                                               | Status                           |
| -------------- | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| Slack reply    | `1789306699.812559`                    | https://invariantlab.slack.com/archives/C0C1H02UHEW/p1789306699812559?thread_ts=1789306404.361089&cid=C0C1H02UHEW | published, reread                |
| Linear comment | `d94a2b69-a255-4f44-a3a8-7f94f72d9dca` | https://linear.app/guna-palanivel/issue/GUN-5#comment-d94a2b69-a255-4f44-a3a8-7f94f72d9dca                        | published, description preserved |
| GitHub PR      | 1                                      | https://github.com/GunaPalanivel/invariant-validation/pull/1                                                      | published, reused (no second PR) |
| Actions        | `34765110314`                          | https://github.com/GunaPalanivel/invariant-validation/actions/runs/34765110314                                    | bound to `c74ea2d…`              |

## Browser / demo

Console Verify opens on the incomplete-repair hero. Bake-off and usefulness are on the frozen run record. Two-minute video: operator records using [`docs/DEMO.md`](DEMO.md).

## Blockers (exact next action)

1. **Reviewer accept** — merge of PR 1 is still the operator's clock. Do not auto-merge.
2. **Rotate tokens** — Gemini, Groq, Slack, and Linear keys sat in chat or a tracked example file. Rotate after the event; update `.env` only.
3. **Two-minute video** — operator records; not an agent task.
