# Repository Instructions

## Project documentation

Before changing code, read:

- `docs/PROJECT_STATE.md`
- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md`
- `docs/NEXT_ACTIONS.md`

Read `docs/CHAT_HISTORY_RAW.md` only when the summarized documents do not
contain enough information. Treat the repository as the source of truth and
the chat history as evidence of intent, not proof of implementation.

## Working rules

- Inspect existing behavior before changing it.
- Do not replace working architecture without explaining why.
- Do not add production dependencies without approval.
- Preserve existing environment-variable names unless a migration is agreed.
- Never commit secrets, tokens, passwords, database dumps, or `.env` files.
- Make focused changes rather than broad rewrites.
- Run relevant tests, linting, builds, and type checks after changes.
- Report commands run, files changed, and unresolved issues.

## Documentation maintenance

After meaningful work:

- Update `docs/PROJECT_STATE.md` when current behavior changes.
- Add genuine architecture decisions to `docs/DECISIONS.md`.
- Update `docs/NEXT_ACTIONS.md`.
- Append a concise entry to `docs/SESSION_LOG.md`.

Do not copy entire chat transcripts into the regularly loaded files.
