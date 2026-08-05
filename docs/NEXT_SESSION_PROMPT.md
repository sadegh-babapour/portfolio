# Next Session Prompt

Copy and paste this to start the next session:

> Resume work in `/home/god/Documents/bizqlab/portfolio`. Read `AGENTS.md`,
> `docs/PROJECT_STATE.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`,
> `docs/ROADMAP.md`, `docs/NEXT_ACTIONS.md`, and the latest entries in
> `docs/SESSION_LOG.md` before changing code. Confirm commit `ffdbfb0` or its
> documentation-only successor and a clean working tree. Phase 2 is complete:
> the legacy NiceGUI/public-schema runtime was removed and all three Railway
> services plus the production smoke matrix passed. Begin phase 3 by designing a
> validated source-controlled JSON/YAML model for the on-page résumé timeline
> (not the PDF) and recruiter-focused case studies. Preserve the accepted
> React/Express/standalone-poller behavior and update
> continuity docs after meaningful work. In every progress update, report
> `Overall: Step X/9` and `Current step: mini-step Y/N`.

Expected baseline:

- `portfolio`, `transit-api`, and `transit-poller` are deployed successfully at
  `f6f661e`.
- The production résumé is volume-backed and renders on mobile through the
  locally bundled PDF.js viewer.
- Sticky navigation, shared flash-free themes, and theme-aware ECharts are live.
- The Calgary React/Express/standalone-poller path is the only active source and
  production implementation.
- `docs/ROADMAP.md` records the agreed phase order and future product goals.
- The candidate TTC endpoint
  `https://bustime.ttc.ca/gtfsrt/vehicles?debug` is recorded for phase 8 but must
  not be investigated until the earlier phases are complete. At that point,
  compare Toronto with established realtime rail feeds internationally rather
  than assuming the final demonstration city.
