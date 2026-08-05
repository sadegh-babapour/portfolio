# Technical Decisions

Last reconciled: 2026-08-03

Statuses distinguish an accepted direction from a verified implementation.

## ADR-001: Keep NiceGUI/FastAPI as the portfolio shell

Date: 2026-04-22
Status: Accepted; currently implemented for the legacy site

### Context

The portfolio already used NiceGUI for its navigation, dashboard, résumé, and
other pages before the newer transit experience was developed.

### Decision

Keep NiceGUI/FastAPI as the main portfolio web application rather than
rewriting unrelated working pages.

### Reasons

- Existing portfolio pages and the cached dashboard already use NiceGUI.
- The transit work can be isolated without disrupting unrelated content.
- FastAPI can serve static assets and a built React application.

### Consequences

The repository contains more than one frontend technology, and integration
must handle subpath assets and API routing deliberately.

### Alternatives considered

- Rewrite the complete portfolio in React.
- Reimplement the interactive transit UI entirely in NiceGUI.

## ADR-002: Use React and Leaflet for the Calgary Transit page

Date: 2026-04-22
Status: Accepted; substantially implemented

### Context

The map requires responsive controls, vehicle playback, route layers, selected
vehicle state, animated paths, and mobile interaction.

### Decision

Build the Calgary Transit experience as a React/Vite application using Leaflet
and React Leaflet.

### Reasons

- The standalone prototype established the desired interaction before Railway
  integration.
- React is better suited to the map's client-side state and animation than the
  older NiceGUI prototype.
- The user explicitly allowed replacement of older polling/map/frontend code
  while preserving unrelated portfolio pages.

### Consequences

React needs its own build process and a compatible API. The NiceGUI mount must
serve subpath-safe asset URLs.

### Alternatives considered

- Continue the NiceGUI Leaflet implementation.
- Replace the portfolio shell as part of the map work.

## ADR-003: Keep database access behind a transit API

Date: 2026-04-22
Status: Accepted; implemented in the standalone stack

### Context

The React frontend needs vehicle history, route shapes, stops, and alerts from
PostgreSQL.

### Decision

React must call an HTTP API and must never connect directly to PostgreSQL.

### Reasons

- Database credentials remain server-side.
- SQL and response shaping have one owner.
- The API can evolve independently of map rendering.

### Consequences

The frontend, API, and database contracts must be versioned together and the
API must be deployed alongside the web application.

### Alternatives considered

- Browser-to-database access.
- Duplicating complex transit queries in frontend code.

## ADR-004: Retain Express as the initial transit API

Date: 2026-05-07
Status: Accepted target; not integrated into deployment

### Context

The standalone Express API was working and had already accumulated the SQL and
response contracts used by the React map.

### Decision

Keep and modularize Express for the first integrated deployment. Consider a
FastAPI port only after behavior is stable.

### Reasons

- Preserves the working standalone contract.
- Reduces risk during repository recovery and Railway integration.
- Avoids combining a backend rewrite with deployment work.

### Consequences

The target deployment has separate Python web and Node API processes.

### Alternatives considered

- Port all Express endpoints to FastAPI before deployment.
- Fold database queries into the NiceGUI process without first preserving the
  existing contract.

## ADR-005: Use PostgreSQL `transit` schema as the newer transit model

Date: 2026-04-22
Status: Accepted; bootstrap verified locally

### Context

Calgary's VehiclePositions feed is sparse and requires enrichment from static
GTFS, TripUpdates, Alerts, and route-category data.

### Decision

Use normalized static GTFS tables, current realtime tables, short raw history,
and frontend-ready views under the PostgreSQL `transit` schema.

### Reasons

- `trip_id` can connect sparse vehicle data to routes, shapes, and stops.
- Current tables make dashboard reads small and predictable.
- Raw history supports delayed playback and diagnostics.
- Views centralize Calgary-specific enrichment and classification.

### Consequences

Static GTFS loading and schema migrations are reproducible. The older
public-schema implementation cannot silently serve as the same data model.

### Alternatives considered

- Store only raw protobuf snapshots.
- Replace normalized shapes with GeoJSON blobs as the primary source of truth.
- Continue only with the older public-schema tables.

## ADR-006: Run realtime ingestion as a separate Python poller

Date: 2026-04-22
Status: Accepted target; code exists but worker deployment is unverified

### Context

The application needs three Calgary feeds refreshed on a schedule without
coupling ingestion to browser traffic.

### Decision

Use a separate Python process to ingest VehiclePositions, TripUpdates, and
Alerts. Configure its interval, operating hours, timezone, retention, and kill
switch through existing environment variables.

### Reasons

- Ingestion can be stopped, monitored, or restarted independently.
- API and web restarts do not define data freshness.
- Current-state upserts and short raw retention match dashboard needs.

### Consequences

Deployment requires a worker service and directly declared Python dependencies.

### Alternatives considered

- Poll only from NiceGUI startup.
- Trigger polling from frontend activity.
- Schedule every cleanup as a separate database cron job.

## ADR-007: Use delayed real observations for vehicle playback

Date: 2026-04-22
Status: Accepted and implemented in React

### Context

Calgary updates vehicle positions approximately every 30 seconds. Immediate
display creates jumps, while invented trajectories would misrepresent the
feed.

### Decision

Render about 75 seconds behind the latest observation and interpolate only
between real bounding observations. Use 20 meters as the initial stopped
threshold and 120 seconds as the stale threshold.

### Reasons

- Provides smoother movement without predicting beyond known points.
- Leaves enough buffer for normal polling and processing delay.
- Makes stopped and stale states explicit.

### Consequences

The page is intentionally delayed and needs a short raw history window.

### Alternatives considered

- Display each update immediately with marker jumps.
- Extrapolate future positions.
- Let users adjust the playback delay.

## ADR-008: Do not show Calgary LRT as live vehicle markers without positions

Date: 2026-04-22
Status: Accepted; implemented in page framing

### Context

The recorded feed investigation found LRT TripUpdates but no corresponding LRT
VehiclePositions.

### Decision

The Calgary vehicle map focuses on buses, BRT/MAX, Express, and featured bus
routes. LRT route/service information may be added separately, but the UI must
not imply live train coordinates it does not receive.

### Reasons

- Prevents fabricated or misleading live markers.
- Keeps the initial page aligned with available data.
- Leaves TTC/subway work as a separate future discussion.

### Consequences

This decision must be revisited if feed availability changes.

### Alternatives considered

- Infer train positions from TripUpdates.
- Show static LRT markers as if they were realtime.

## ADR-009: Track the React production bundle during deployment recovery

Date: 2026-08-03
Status: Temporary; accepted for recovery

### Context

The current Railway web process starts Python from the repository root and no
verified Railway build command regenerates `frontend/dist`. Ignoring the bundle
would remove the only artifact that NiceGUI can currently serve.

### Decision

Keep `frontend/dist` tracked until the Railway web service has a verified Node
install/build phase.

### Reasons

- The regenerated bundle has been smoke-tested at its production subpath.
- It keeps the existing web deployment model functional while Railway state is
  recovered.
- It avoids claiming an unobserved Railway build configuration works.

### Consequences

Source and generated bundle changes must be committed together temporarily.
Once Railway reliably runs `npm ci` and `npm run build` in `frontend`, remove
the bundle from source control and update this decision.

### Alternatives considered

- Ignore the bundle immediately and assume Railway builds it.
- Add unverified service-specific Docker or Railpack configuration.

## ADR-009: Mount the built transit page at `/calgary-transit-live`

Date: 2026-05-07
Status: Accepted; navigation and subpath wiring implemented locally

### Context

The React application is intended to appear as a portfolio page with a clear,
descriptive URL. Because FastAPI serves it as a standalone React bundle, it
does not inherit NiceGUI-rendered components.

### Decision

Serve the production React bundle through FastAPI at
`/calgary-transit-live`, expose that route in the NiceGUI navigation, and
render matching portfolio navigation within the React application.

### Reasons

- Preserves one portfolio-facing domain and navigation shell.
- Gives the feature a stable descriptive URL.

### Consequences

Vite must build subpath-safe assets. Portfolio navigation links are maintained
in both the NiceGUI shell and the standalone React bundle, so changes to the
link set must keep them synchronized.

### Alternatives considered

- Keep the opaque `/map` path.
- Host the frontend only as an unrelated standalone site.

## ADR-010: Target three Railway services from one repository

Date: 2026-05-07
Status: Accepted and implemented; final web smoke test pending

### Context

The chosen technologies require a web host, API, and continuously scheduled
ingestion process.

### Decision

Deploy one repository as three Railway services sharing PostgreSQL:

1. NiceGUI/FastAPI web service that builds and serves React.
2. Express transit API.
3. Python GTFS-Realtime poller worker.

### Reasons

- Preserves working component boundaries.
- Allows independent commands, restarts, and environment variables.
- Defers an unnecessary API rewrite.

### Consequences

Service-specific Railway commands and variables must remain synchronized with
the repository documentation and verified independently after changes.

### Alternatives considered

- One process running all three components.
- Port Express into FastAPI before the first recovered deployment.

## ADR-011: Do not track the large static GTFS stop-times export

Date: 2026-08-03
Status: Accepted and implemented

### Context

`data/stop_times.txt` is approximately 78.6 MB, exceeds GitHub's recommended
single-file size, and becomes stale as Calgary publishes schedule updates. The
database bootstrap already downloads Calgary's current static GTFS archive.

### Decision

Remove `data/stop_times.txt` from Git tracking and ignore future local copies.
Use `scripts/bootstrap_transit_db.py --load-static` as the production source of
static stop times.

### Consequences

Database initialization requires access to Calgary's GTFS download endpoint.
The deleted file remains recoverable from repository history, but new commits
and deployments no longer carry the oversized artifact.

## ADR-012: Serve the résumé from the portfolio service and attached volume

Date: 2026-08-03
Status: Accepted; code and Git policy implemented, production upload pending

### Context

The résumé page used an unrelated external sample PDF and a third-party PDF.js
viewer. A Railway volume is attached to the portfolio service for the actual
document, but its filesystem path cannot be exposed directly to browsers.

### Decision

Read the configured `RESUME_PDF_PATH` on the server and expose it through the
same-origin `/resume/document.pdf` route. Use the browser's native PDF renderer
in a full-width responsive holder on desktop and mobile, with explicit
open/download fallbacks.

### Consequences

The production service must mount the volume and provide the actual PDF at the
configured path. The application returns HTTP 404 if that configured file is
missing, without revealing the internal filesystem path.

The local `static/resume.pdf` and Railway volume copy are intentionally not
tracked by Git. Other runtime documents may follow this pattern only when they
have a narrowly configured server-side delivery route; source/build assets
remain version controlled.

## ADR-013: Keep NiceGUI and React portfolio navigation visually synchronized

Date: 2026-08-03
Status: Accepted and implemented

### Context

The React transit page cannot inherit NiceGUI components, but users should see
one consistent portfolio shell while moving between the two frontend stacks.

### Decision

Use the deployed React header as the visual reference for the NiceGUI header:
the same link order, color, spacing, typography, desktop navigation, mobile
menu, and current-page treatment.

### Consequences

The link list and styles still have two implementations. Any future navigation
change must update both `app/components/navbar.py` and
`frontend/src/PortfolioNav.jsx`/`frontend/src/App.css` in the same change.

## ADR-014: Share theme preference across the two frontend shells

Date: 2026-08-04
Status: Accepted and implemented

### Context

NiceGUI pages and the standalone React transit page render independently, but
users expect one site-wide light/dark preference when navigating between them.

### Decision

Both shells expose a theme button in the sticky portfolio header and persist
the selected `light` or `dark` value under the `portfolio-theme` local-storage
key. With no saved preference, each shell follows the browser's preferred color
scheme. A synchronous document-head initializer applies the preference before
the page renders so navigation between shells does not flash the light theme.

### Consequences

Theme styles remain implemented separately in the NiceGUI and React CSS, while
the preference name and values form a small shared browser contract. Future
theme changes must keep those values and accessible toggle behavior aligned.
NiceGUI's shared shell also owns dark overrides for Quasar page content and
form/data components so individual pages do not need one-off theme classes.

## ADR-015: Render the résumé with a locally bundled PDF.js viewer

Date: 2026-08-04
Status: Accepted and implemented

### Context

Desktop browsers displayed the same-origin résumé through native PDF embedding,
but mobile Chrome replaced `<object>` and `<iframe>` attempts with a filename
placeholder and an Open action. Native mobile PDF embedding is not consistent
enough for the portfolio's inline résumé requirement.

### Decision

Use Mozilla PDF.js's display layer and worker to render each résumé page into a
responsive canvas. Bundle the approved `pdfjs-dist` dependency as a second Vite
HTML entry point and serve it from the existing FastAPI-mounted transit bundle.
Keep the PDF itself behind `/resume/document.pdf` and retain full-screen and
download fallbacks.

### Consequences

- Mobile display no longer depends on the browser's native PDF plugin.
- The tracked production bundle gains a versioned PDF.js module and an
  approximately 2.2 MB worker asset.
- PDF parsing remains client-side and same-origin; no external viewer service
  or runtime CDN receives the document URL.
- Frontend dependency and security audits now include `pdfjs-dist`.
