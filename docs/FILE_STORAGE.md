# Runtime File Storage

Last updated: 2026-08-03

## Current policy

Personal or replaceable runtime documents should exist in two places:

1. A local ignored path for development, such as `static/resume.pdf`.
2. The persistent Railway volume attached to the `portfolio` service, such as
   `/data/resume.pdf`.

They should not be committed to GitHub. Environment variables map application
features to their runtime paths; currently the résumé uses `RESUME_PDF_PATH`.

Do not apply this policy blindly to source assets required to build the site.
Code, CSS, public design assets, migrations, and reproducible small reference
data still belong in Git. Database rows belong in PostgreSQL, not the file
volume.

## Confirm what “Storage 3” is

Open the Railway project canvas and select `Storage 3`.

- If its settings show a **mount path** and it is attached to `portfolio`, it
  is a Volume. Use the procedure below.
- If it shows S3-compatible credentials such as `BUCKET`, `ENDPOINT`, and
  access keys, it is a Bucket. Do not use `RESUME_PDF_PATH=/data/resume.pdf`;
  bucket support would require a separate application integration.

The current résumé implementation expects a Volume mounted at `/data`.

## Upload the résumé to the Railway volume

1. Install/login to the Railway CLI and link this repository to the existing
   Railway project:

   ```bash
   railway login
   railway link
   ```

2. Confirm `Storage 3` is attached to the `portfolio` service with mount path
   `/data`. A volume is available only at its configured absolute mount path.

3. Open the persistent directory in Railway's interactive file browser:

   ```bash
   railway service files browse /data --service portfolio
   ```

   Use the browser's upload action to place the local file at
   `/data/resume.pdf`.

   The equivalent non-interactive command is:

   ```bash
   railway service files upload ./static/resume.pdf /data/resume.pdf --service portfolio
   ```

4. In the `portfolio` service Variables tab, set:

   ```text
   RESUME_PDF_PATH=/data/resume.pdf
   ```

5. Redeploy/restart the `portfolio` service, then verify:

   ```text
   https://www.bizqlab.com/resume
   https://www.bizqlab.com/resume/document.pdf
   https://www.bizqlab.com/resume/document.pdf?download=true
   ```

Railway volumes are not mounted during pre-deploy commands. File upload and
access must target the running service/volume, not a pre-deploy step.

## Replacing the file later

Keep the filename stable (`resume.pdf`) and upload the new version over the
volume copy. Replace the local `static/resume.pdf` separately. The application
route remains unchanged, and no Git commit is needed for document-only
updates.

Before replacing any other runtime file, add a narrowly named environment
variable and a same-origin authenticated or intentionally public delivery
route. Never expose arbitrary volume paths or directory listings.
