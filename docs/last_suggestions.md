Create a proper project-memory structure

I would use this:

your-repo/
├── AGENTS.md
├── README.md
├── docs/
│   ├── PROJECT_STATE.md
│   ├── ARCHITECTURE.md
│   ├── DECISIONS.md
│   ├── SESSION_LOG.md
│   ├── NEXT_ACTIONS.md
│   └── CHAT_HISTORY_RAW.md
└── ...

Each file has a separate purpose.

AGENTS.md

This is the instruction manual Codex automatically reads at the start of each session.

Keep it short. It should contain:

# Repository Instructions

## Project documentation

Before changing code, read:

- `docs/PROJECT_STATE.md`
- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md`
- `docs/NEXT_ACTIONS.md`

Read `docs/CHAT_HISTORY_RAW.md` only when the summarized documents do not
contain enough information.

## Working rules

- Inspect existing behavior before changing it.
- Do not replace working architecture without explaining why.
- Do not add production dependencies without approval.
- Preserve existing environment-variable names.
- Never commit secrets, tokens, passwords, database dumps, or `.env` files.
- Make focused changes rather than broad rewrites.
- Run the relevant tests, linting, and type checks after changes.
- Report commands run, files changed, and unresolved issues.

## Documentation maintenance

After meaningful work:

- Update `docs/PROJECT_STATE.md` when current behavior changes.
- Add architecture decisions to `docs/DECISIONS.md`.
- Update `docs/NEXT_ACTIONS.md`.
- Append a concise entry to `docs/SESSION_LOG.md`.

Do not copy entire chat transcripts into the regularly loaded files.

Codex automatically discovers AGENTS.md from the Git root down to the current directory. More-specific files deeper in the repo can override broader instructions. It loads that instruction chain once per launched session.

You can initially generate one inside Codex with:

/init

But I would still edit it afterward. OpenAI recommends keeping AGENTS.md practical and concise rather than turning it into a massive knowledge dump.

PROJECT_STATE.md

This answers: Where are we now?

# Current Project State

Last verified: YYYY-MM-DD

## Project purpose

Brief explanation.

## Working features

- Feature A
- Feature B

## Partially working features

- Feature C: current limitation

## Known broken behavior

- Issue and reproduction steps

## Current development environment

- Ubuntu version:
- Runtime versions:
- Database:
- Package manager:
- Startup command:

## External services

List service names without secrets.

## Unknown or unverified

- Items that still need investigation
ARCHITECTURE.md

This answers: How does it work?

# Architecture

## Overview

## Repository layout

## Application entry points

## Components and responsibilities

## Data flow

## Database structure

## External integrations

## Local development flow

## Deployment flow
DECISIONS.md

This answers: Why did we do it this way?

Use small ADR-style entries:

# Technical Decisions

## ADR-001: Use PostgreSQL for application storage

Date: YYYY-MM-DD
Status: Accepted

### Context

Why the decision was needed.

### Decision

What was selected.

### Reasons

Why it was selected.

### Consequences

Tradeoffs and limitations.

### Alternatives considered

Other options that were rejected.
NEXT_ACTIONS.md

This becomes your restart point:

# Next Actions

## Immediate

- [ ] Confirm the application starts locally.
- [ ] Investigate failing endpoint X.
- [ ] Verify database migrations.

## Later

- [ ] Improve tests.
- [ ] Clean up deployment configuration.

## Blocked

- [ ] Task — blocked by missing information.

## Current recommended next task

A single clearly defined task.
SESSION_LOG.md

Do not make it a full transcript. Keep each entry concise:

# Session Log

## YYYY-MM-DD — Repository recovery

### Goal

Recover understanding of the existing repository.

### Inspected

- Main application entry point
- Dependency configuration
- Database setup

### Changed

- Added project documentation
- No application code changed

### Verified

- Command and result

### Decisions

- Decision summary or reference to ADR

### Unresolved

- Remaining uncertainty

### Next

- Exact next task
5. Dumping your previous chats is useful—but isolate them

Yes, export or paste the old development chats, but do not put the entire transcript inside AGENTS.md.

Create:

mkdir -p docs
touch docs/CHAT_HISTORY_RAW.md

Paste the conversations there, ideally with headings:

# Historical Development Conversations

## Conversation 1 — Initial architecture

[pasted conversation]

---

## Conversation 2 — Database changes

[pasted conversation]

Before doing that, remove:

API keys
passwords
database credentials
private URLs containing tokens
.env contents
session cookies
personal data unrelated to the project

Then ask Codex:

Read docs/CHAT_HISTORY_RAW.md and compare it against the current repository.

The repository is the source of truth for what currently exists. The chat
history is evidence of intent, not proof that something was implemented.

Do not modify application code.

Create or update:

- docs/PROJECT_STATE.md
- docs/ARCHITECTURE.md
- docs/DECISIONS.md
- docs/NEXT_ACTIONS.md
- docs/SESSION_LOG.md

Separate findings into:

1. Confirmed by current code.
2. Stated in chat but not found in code.
3. Contradicted by current code.
4. Still uncertain.

Do not invent missing decisions. Mark uncertain items explicitly.

That distinction is extremely important. Chats often say “we implemented X,” while the actual files may contain an older, incomplete, or reverted version.

6. Ask Codex to establish how the repo runs

After the documentation pass, give it this task:

Do not make feature changes.

Determine the exact local startup procedure for this repository.

Inspect dependency files, environment examples, Docker configuration,
migration files, build scripts, and application entry points.

Then:

1. List required software.
2. Identify required environment variables without exposing secret values.
3. Install only existing declared dependencies.
4. Attempt the documented startup process.
5. Record every error exactly.
6. Fix only environment or documentation problems after explaining them.
7. Do not redesign the application.

Update docs/PROJECT_STATE.md and docs/NEXT_ACTIONS.md with verified results.

A good first recovery milestone is not “finish the app.” It is:

Fresh VM → install dependencies → start project → reproduce current state.

7. Use VS Codium and Codex together

Open the repo in VS Codium:

cd ~/path/to/your-repo
codium .

Then either use VS Codium’s integrated terminal:

codex

or use a separate terminal window.

My preference:

VS Codium: inspect files and review diffs.
Terminal 1: Codex.
Terminal 2: application server or tests.
Terminal 3: Git commands and logs.

You do not need separate shells for each purpose. Every terminal can use zsh.

A simple tmux setup is also possible:

tmux new -s project

But do not add tmux complexity yet unless you already like terminal multiplexers.

8. Your repeatable workflow from now on

At the beginning of a session:

cd ~/path/to/repo
git status
git log --oneline -5
codex

Then:

Read AGENTS.md and the project documents it references.

Summarize:
- current project state,
- last completed work,
- unresolved problems,
- recommended next task.

Do not change files yet.

For a coding task, use this structure:

Goal:
Implement [specific behavior].

Context:
Relevant files and current behavior.

Constraints:
Do not change [protected behavior].
Use existing architecture and dependencies.

Done when:
- The requested behavior works.
- Relevant tests pass.
- Lint/type checks pass.
- Documentation is updated.
- The final diff is reviewed.

OpenAI recommends prompts that state the goal, relevant context, constraints, and concrete completion criteria.

At the end:

Review the changes made in this session.

Run the relevant tests and checks.

Then update:
- docs/PROJECT_STATE.md
- docs/DECISIONS.md, only if a real decision was made
- docs/NEXT_ACTIONS.md
- docs/SESSION_LOG.md

Keep the summaries concise and factual. Distinguish verified facts from
assumptions. Do not commit anything.

Then manually inspect:

git status
git diff --stat
git diff

And inside Codex:

/review

Only then commit:

git add -A
git commit -m "document recovered project state"

The best immediate sequence for you is:

exec zsh
cd ~/path/to/repo
git status
git add -A
git commit -m "checkpoint before Codex repository recovery"
codex

Then use /plan and paste the read-only repository-inspection prompt above.
