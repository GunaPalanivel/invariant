# Live apps — configure one service at a time

Do not paste secrets into chat. Put them only in a local `.env` (gitignored).
Generated tests never receive production tokens.

Until a service is configured, Invariant records that step as **deferred** and does not invent object URLs.

## 1. GitHub (authorized)

Repo: `GunaPalanivel/invariant-validation` (AUT + CI only; not the product workspace).

- Fine-grained or classic PAT with: contents write, pull requests write, actions read — **or** use `gh auth login` so the broker can call `gh auth token`.
- `GITHUB_REPO=GunaPalanivel/invariant-validation`

## 2. Slack — workspace Invariant Lab, channel `C0C1H02UHEW`

Dedicated channel: https://invariantlab.slack.com/archives/C0C1H02UHEW

Bot token scopes (see also `docs/slack-manifest.yaml`):

- `chat:write`
- `channels:history` for a public channel, or `groups:history` for a private channel
- Bot must be **in** the channel (`not_in_channel` otherwise)

Register metadata event type `invariant_operation` (payload field `operation_id`). Metadata is workspace-visible, not a secret, not an idempotency key.

`.env`:

- `SLACK_BOT_TOKEN`
- `SLACK_TEST_CHANNEL_ID` (channel id, currently `C0C1H02UHEW`)
- `SLACK_TEST_THREAD_TS` (parent `ts` of the **incident** thread, not a join or connection-check)

Seed the incident thread as a **controlled demonstration** with injected-fault labeling. Invariant will `conversations.replies` for intake and `chat.postMessage` with `thread_ts` for the finding. `internal_error` / `fatal_error` after a write is treated as **unknown** — no second reply.

## 3. Linear — workspace guna-palanivel, team GUN, issue GUN-5

Issue: https://linear.app/guna-palanivel/issue/GUN-5/release-notifier-prevent-duplicate-delivery-without-dropping-valid

Create a personal API key. GraphQL endpoint `https://api.linear.app/graphql`. Header: `Authorization: <key>` (no `Bearer`).

The key must be able to **read issues** and **create comments**. Invariant uses `commentCreate` only. It does **not** overwrite `description`.

`.env`:

- `LINEAR_API_KEY`
- `LINEAR_ISSUE_ID` — `GUN-5` or the issue UUID (`issue(id:)` accepts both)

After you add these, re-run `python -m invariant.workflow`. The broker GETs stored journal IDs, rereads the comment/issue, then writes if the prior step is not unknown.
