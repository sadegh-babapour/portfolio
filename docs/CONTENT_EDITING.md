# Editing Portfolio Content

The on-page résumé timeline and project case studies are source-controlled JSON.
They are independent from the résumé PDF stored on the Railway volume.

## Timeline

Edit `content/resume_timeline.json`. Keep `schema_version` at `1` and give every
entry a stable, unique `id`.

Required entry fields:

- `period`: display text such as `2022–2024` or `2025–Present`;
- `title` and `organization`;
- `kind`: `work`, `education`, `project`, or `milestone`;
- `summary`;
- `highlights` and `skills`: JSON lists, which may be empty;
- `icon` and `color`: NiceGUI/Material icon and Quasar color names.

The committed entries are explicitly marked placeholders. Replace or remove
them rather than publishing unconfirmed history.

## Projects

Edit `content/projects.json`. Every project needs a unique `id` and the following
content:

- title, status, summary, and business problem;
- architecture, data sources, and ordered pipeline steps;
- technology stack, outcomes, and honest limitations;
- `visibility`: `public` or `registered`;
- `data_mode`: `static_content`, `static_snapshot`, `scheduled_snapshot`, or
  `live_database`;
- links using either a root-relative path or an `https://` URL.

`registered` is content metadata only until the authentication phase enforces
access. Do not place private material in these committed JSON files.

## Validate before publishing

Run:

```bash
.venv/bin/python -m unittest discover -s test -v
```

The loader rejects invalid JSON, unsupported versions, duplicate IDs, invalid
enums, missing required values, and unsafe link schemes. A page displays a safe
unavailable message and logs the validation error if invalid content reaches a
runtime environment.

## Future admin editing

The admin console will not rewrite these files on Railway: container filesystem
changes are not a reliable source of truth and would bypass Git review. When
admin content editing is implemented, editable records will live in a dedicated
ORM-owned `portfolio` schema in the existing PostgreSQL database. These JSON
documents can seed/import that schema and remain the portable fallback.

Service health, API checks, job runs, cache refreshes, and audit events are
dynamic operational data. They belong in PostgreSQL and the future admin/task
monitor, never in these static content files.
