# Generation diagnosis

Measured locally after the eight-finding repair. Injected AUT transport. Not a live Slack outage.

## Recovered Groq blob

- Source: `GunaPalanivel/invariant-validation` commit `ef1a2325ef8f659838565b0101f130c715b0beb9`
- Path in that repo: `tests/test_generated_aut.py`
- Local copy: `results/generation-candidates/ef1a232-groq/`
- Class: **construction** / `invalid_test`
- First exception (original run): `AttributeError: 'tuple' object has no attribute 'adapter'` after `self.session = make_session()`
- `make_session()` returns `(adapter, observer, store)`

This blob is **not** the verified pack.

## Bounded repairs ($0)

Primary Gemini 3.7 Flash, fallback Groq `openai/gpt-oss-120b`. Scoring keys not in the prompt. `policies.py` repair implementations not in the prompt. Harness tuple contract is in the prompt.

Two repairs ran. Model Python still omitted the required regression names (`lost_ack_does_not_duplicate`, `empty_page_after_dispatch_does_not_retry`, `never_dispatched_sends_once`, `legitimate_new_operation`).

## Architecture gate

Construction/coverage remaining → live model **scenario spec** → deterministic compiler for this family only.

- `generation_origin`: `scenario-compiler:model:groq`
- `scenario_origin`: `model:groq`
- `code_generation_origin`: `deterministic_compiler`
- Compiled bytes match `generated/test_generated_aut.py`
- SHA-256: `0154894c447e76d3ff80105524bf5b9d3b4bf5732fff97ad6036eaca4e407a19`

Not labeled as free-form model-authored unittest.

## Independent matrix

Same candidate hash `H` against original / incomplete / correct / content-dedup mutant in isolated subprocesses (`results/execution-manifest.json`).

| Implementation | unittest | Required |
|---|---|---|
| original | fail lost-ack + empty-page | finding |
| incomplete | fail empty-page | finding |
| correct | pass all four | recovery |
| content_dedup | fail shared-session new op | mutant rejected |

`pack.valid` requires this matrix **and** the independent ExpectedIntent checker. A file of `assertTrue(True)` is `invalid_test`.

## Publication

Slack no longer retries on HTTP 500 after a committed write. Linear reread requires the comment in issue nodes. Timeout after create persists `unknown` so restart cannot create a second comment. Live publish is gated on `pack.valid`.

## CI

`wait_and_bind_ci` hashes `tests/test_generated_aut.py` at `head_sha` via GitHub contents and, when present, the Actions `execution-manifest` artifact. Caller-supplied hash is not compared to itself. `ci_bound` for a verification claim needs SHA association, completed run, observed hash match, and `conclusion=success`.

## Closure table

| Finding | Failing reproduction | Fix | Verification | Remaining |
| --- | --- | --- | --- | --- |
| F1 no-op pack | `tests/test_review_probes.py` | Isolated matrix; `pack.valid` needs matrix | probe + `results/execution-manifest.json` | Independent review |
| F2 env canary | same | Allowlisted subprocess env | probe | Not a full sandbox OS |
| F3 invented fields | same | Source-span evidence; judge cannot ground | probe | Heuristic path separate |
| F4 circular CI hash | same | `get_contents` blob hash | probe | Needs new Actions run on PR 1 |
| F5 Slack retry | same | No second `chat.postMessage` on 500 | probe | No live 500 observed |
| F6 Linear false reread | same | Comment must appear in reread nodes | probe | |
| F7 Linear restart | same | Persist unknown before return | probe | |
| F8 content-dedup | same | Shared-session A then B | probe + matrix mutant run | |

- Independent engineer review of PR 1 is still yours; not recorded here.
- Two-minute video is still yours; add the link to the README when it exists.
- PR 1 merge clock remains the operator of `invariant-validation`. Do not auto-merge.
- Groq coding-agent baseline is a finding (construction failure, then omitted required regression names), not an unfinished comparison.
