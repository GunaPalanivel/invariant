# Demo recording (from this tree)

You record the two-minute video. Add the public URL to the README when it exists. The console is frozen evidence from off-camera runs. Injected AUT faults stay labeled. Slack/Linear/GitHub links on Publish are live object URLs from reread.

Live objects:

- Incident thread: https://invariantlab.slack.com/archives/C0C1H02UHEW/p1789306404361089
- Finding reply: https://invariantlab.slack.com/archives/C0C1H02UHEW/p1789306699812559?thread_ts=1789306404.361089&cid=C0C1H02UHEW
- Linear comment: https://linear.app/guna-palanivel/issue/GUN-5#comment-d94a2b69-a255-4f44-a3a8-7f94f72d9dca
- PR: https://github.com/GunaPalanivel/invariant-validation/pull/1
- CI: https://github.com/GunaPalanivel/invariant-validation/actions/runs/34765110314

| Time | Show | Takeaway |
| --- | --- | --- |
| 0–15s | Controlled lost-ack duplicate on original `blind_retry` (observer count 2) | The engineering cost is a second write under the same `operation_id` |
| 15–35s | Incident + Linear acceptance → grounded contract with source spans | Fields come from sources; invented values are ungrounded |
| 35–75s | Same generated file, hash `0154894c…`: original RED, incomplete empty-page RED, correct GREEN, shared-session new op GREEN | The regression rejects the bug and the incomplete fix without blocking legitimate work |
| 75–100s | PR 1, `execution-manifest.json`, Slack reply, Linear comment | Three-app evidence; CI binds an observed blob hash |
| 100–120s | Scope: injected notifier family; `scenario-compiler:model:groq`; `superiority_claim: false`; remaining: your review, this video, PR merge | Honest limits |

Backup: this document plus `results/workflow.json` and `docs/GENERATION_DIAGNOSIS.md` if a service is blocked.
