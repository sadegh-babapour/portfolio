# Next Session Prompt

Copy and paste this to start the next session:

> Resume work in `/home/god/Documents/bizqlab/portfolio`. Read `AGENTS.md`,
> `docs/PROJECT_STATE.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`,
> `docs/NEXT_ACTIONS.md`, and the latest entries in `docs/SESSION_LOG.md` before
> changing code. Also use `docs/FILE_STORAGE.md` for the résumé upload workflow.
> First inspect the committed NiceGUI navbar, responsive PDF viewer, résumé
> volume delivery, and documentation changes; do not overwrite them. Confirm
> the local commit and working-tree state, then help me push/deploy it. After
> deployment, walk me step by step through uploading `static/resume.pdf` to the
> `portfolio` Railway volume at `/data/resume.pdf`, setting
> `RESUME_PDF_PATH=/data/resume.pdf`, and testing `/resume` on desktop and
> mobile. Then verify the transit poller freshness, live vehicle markers,
> route/vehicle selection, history, stops, alerts, and browser console during
> Calgary operating hours. Update the continuity docs after meaningful work.

Expected baseline before that session:

- Public transit frontend/API deploy is healthy at commit `f58763f`.
- NiceGUI navbar and résumé changes are committed locally but not yet pushed or
  deployed.
- The résumé PDF remains at local ignored path `static/resume.pdf` and is staged
  for removal from Git tracking; it must never be re-added to GitHub.
- `Storage 3` must be confirmed as the Volume attached to `portfolio` at
  `/data` before uploading.
