# LLMs.txt Generator

Python/FastAPI web app that accepts a website URL, scans it, and returns a downloadable `llms.txt` file.

## What Works Now

- Plain HTML frontend with a centered URL input, Go button, and expandable Advanced Settings.
- FastAPI backend.
- SQLite local database.
- Local generated file storage under `storage/`.
- Scan lifecycle endpoints:
  - `POST /api/scans`
  - `GET /api/scans?url=...`
  - `GET /api/scans/{scan_id}`
  - `GET /download/{scan_id}`
- SSRF-oriented URL safety checks.
- Safe HTTP fetcher with timeout, retry, redirect checks, and response-size limits.
- `robots.txt` fetching and allow/disallow handling.
- Sitemap-first discovery with `/sitemap.xml` fallback.
- Configurable crawl limits: 100 resources, depth 2, and a 30-second crawl budget by default.
- Homepage/internal HTML link extraction.
- Metadata extraction from title, meta description, canonical URL, headings, and link context.
- Heuristic page ranking and section assignment.
- PDF inclusion.
- Meaningful image inclusion with icon/static-asset filtering.
- Generated `llms.txt` validation before writing the downloadable file.
- Per-site version numbers for repeated scans of the same normalized URL.
- Versioned generated files, stored as `scan-{scan_id}-v{version_number}-llms.txt`.
- Version history display for repeated scans of the same website.
- Metadata-based change summaries for repeated scans.

## Local Setup

Using conda:

```bash
conda activate myenv
conda install -c conda-forge fastapi uvicorn jinja2 sqlalchemy pydantic httpx beautifulsoup4 pytest
uvicorn app.main:app --reload
```

Using `venv`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

If pyenv reports that `3.13.5` is unavailable on your machine, use any installed
Python 3.13.x version and create the venv with that interpreter (for example
`python3.13 -m venv .venv`).

Storage path behavior:

- Local default (no env var set): `./storage` in the repo.
- Hosted persistent mode: set `STORAGE_DIR=/var/data` (or your mounted disk path).

Then open:

```text
http://127.0.0.1:8000
```

## Run And Stop With Conda

Start the local server:

```bash
conda activate myenv
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Stop the local server:

```text
Press Ctrl+C in the terminal running uvicorn.
```

Leave the conda environment:

```bash
conda deactivate
```

Optional default crawl tuning:

```bash
export CRAWL_MAX_PAGES=100
export CRAWL_MAX_DEPTH=2
export CRAWL_MAX_DURATION_SECONDS=30
export CRAWL_MAX_CONCURRENCY=10
export CRAWL_MAX_SITEMAPS=10
export AUTO_REFRESH_LOOKBACK_HOURS=12
export AUTO_REFRESH_POLL_INTERVAL_SECONDS=3600
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The first three environment variables set the defaults shown in Advanced Settings. The user can still override them per scan in the browser. `CRAWL_MAX_CONCURRENCY` controls the bounded thread pool used to fetch subpages during a scan. `CRAWL_MAX_SITEMAPS` limits how many sitemap files are fetched before page crawling begins. `AUTO_REFRESH_LOOKBACK_HOURS` controls when a previous completed scan is considered stale. `AUTO_REFRESH_POLL_INTERVAL_SECONDS` controls how frequently the background auto-refresh poller runs; by default it checks once per hour.

Auto-refresh is an in-process background poller that starts with the FastAPI app. It runs one cycle immediately on startup, then checks once per `AUTO_REFRESH_POLL_INTERVAL_SECONDS`. A site is refreshed only when its latest scan is older than `AUTO_REFRESH_LOOKBACK_HOURS` and auto-refresh is enabled for that site. If a site already has a queued, crawling, or generating scan, the poller skips it to avoid duplicate refresh work. Runtime health is available at `/api/auto-refresh/status`.

Advanced Settings bounds:

- Max pages: 1 to 500.
- Max depth: 0 to 5.
- Time budget: 1 to 60 seconds.
- Crawl concurrency: 1 to 20 workers.
- Sitemap files fetched: 1 to 50 files.

## Testing

Run the test suite:

```bash
conda activate myenv
pip install -r requirements.txt
pytest -q
```

Run a syntax/import check:

```bash
python -m compileall app tests
```

## Manual Smoke Test

Start the app:

```bash
conda activate myenv
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open the app:

```text
http://127.0.0.1:8000
```

In the browser:

1. Enter a public website URL, such as `example.com`.
2. Optional: expand `Advanced Settings` and adjust max pages, max depth, or time budget.
3. Click `Go`.
4. Wait for the status to complete.
5. Click the versioned download link, such as `Download llms-v1.txt`.
6. Confirm the downloaded file starts with an H1 title, includes a blockquote summary when available, and contains Markdown links under section headings.
7. Confirm the Version History list shows the completed scan.
8. Enter the same website URL again and confirm the next completed scan shows the next version number while the older version remains downloadable in history.
9. Confirm the newer history row shows a compact change summary, such as `+0 added, -0 removed, 0 changed`.

Redirect note: the crawler stays within one website hostname for safety. Root and `www.` variants are treated as the same site, so redirects like `google.com` to `www.google.com` are allowed. Redirects to unrelated subdomains or different domains are blocked.

Optional API-only check:

```bash
curl -s -X POST http://127.0.0.1:8000/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"url":"example.com"}'
```

Use the returned `scan_id`:

```bash
curl -s http://127.0.0.1:8000/api/scans/1
curl -s 'http://127.0.0.1:8000/api/scans?url=example.com'
curl -s http://127.0.0.1:8000/download/1
```

The API status and history responses include both a global `scan_id` and a per-site `version_number`. The `scan_id` is the database primary key across all websites. The `version_number` increases only for scans with the same normalized root URL, so scanning `example.com`, then another site, then `example.com` again creates `example.com` versions 1 and 2 while preserving each scan row and generated file separately.

When a repeated scan completes, the app compares it with the previous completed scan for the same normalized URL. V1 change detection is metadata-based: it matches pages by canonical URL or URL and counts added, removed, changed, and unchanged pages based on title, description, resource type, and section.

V1 ranking is heuristic and explainable. The ranker prioritizes the homepage, documentation, guides, product/pricing pages, support pages, company pages, articles, meaningful PDFs, and meaningful images. It downranks or excludes low-value URLs such as login, checkout, search, tag/archive, feed, legal, privacy, and terms pages.

Large sites can still take longer than small sites because the crawler follows sitemaps and internal links within the configured limits. For quick smoke tests, `example.com` is the fastest known-good URL. Search engines and large multilingual sites may produce less useful output than product, docs, or company websites. Use Advanced Settings to reduce max pages, depth, or time budget for faster tests.

Recent verified state:

- Formatter-focused tests run successfully (`tests/test_formatter.py`).
- Manual ranking QA notes are tracked in `MANUAL_QA.md`.

## Remaining Work

- Tune ranking rules from manual tests across richer public websites.
- Add detailed change views with exact added, removed, and changed URLs.
- Run broader hosted smoke tests against more real-world sites on the live demo.

## Requirement Coverage And Gaps

Current status against the assignment:

- Web app where users submit a URL and download generated `llms.txt`: **implemented**.
- Website crawl + metadata extraction (titles/descriptions/URLs): **implemented**.
- llms.txt generation and validation pipeline: **implemented**.
- Re-scan awareness with version history + compact change summary: **implemented (V1)**.
- Clear setup/deploy instructions in README: **implemented**.

Items that are still partial or not fully implemented yet:

- Fully automated ongoing monitoring that periodically re-scans websites and refreshes outputs without manual user action (cron/worker/scheduler): **partially implemented (in-process poller)**.
- Broad conformance verification against the latest `llmstxt.org` spec across many real websites (including strict edge-case handling): **partially implemented, needs broader validation**.
- Rich change reporting UI/API with exact URL-level diffs and content-level deltas: **not implemented yet (only compact counts in V1)**.
- Large-variety production hardening (deeper benchmark corpus, stronger anti-bot handling, richer retries/backoff/observability): **partially implemented**.
- Deliverable artifacts for submissions (project screenshots/demo video and collaborator checklist guidance): **not documented as a dedicated checklist section yet**.

Auto-refresh current limitations:

- Scheduler runs in-process with the web app lifespan. If the web service is down, refresh jobs do not run.
- No distributed leader election/locking is implemented yet; multi-instance deployments may still trigger duplicate refresh work across instances.
- Refresh cadence is global via env vars, not per-site custom intervals.
- No dedicated admin UI for retry controls.

## Live Deployment

- Render public URL: `https://website-llms-txt-generator.onrender.com/`

## Codebase Tour For Newcomers

If you are onboarding to this repo, start with these files in order:

1. `app/main.py` for API endpoints, startup flow, and the scan lifecycle surface area.
2. `app/services/scanner.py` for the end-to-end scan pipeline (crawl -> rank -> format -> persist).
3. `app/services/crawler.py` plus helper services (`fetcher`, `robots`, `sitemap`, `html_parser`) for discovery and extraction behavior.
4. `app/services/ranker.py` and `app/services/formatter.py` for inclusion and output quality.

   Ranking algorithm (V1) in one paragraph: each discovered resource gets a heuristic score based on URL pattern and metadata signals. The ranker boosts likely high-value pages (homepage, docs, guides, product/pricing, support, company/about, articles, meaningful PDFs/images), downranks low-value utility/legal pages (login, checkout, search, tags, feeds, privacy/terms), then assigns surviving resources to output sections and marks whether to include them in the final `llms.txt`.

5. `app/models.py`, `app/schemas.py`, and `app/db.py` for persistence and API contracts.
6. `tests/` for expected behavior and edge-case coverage by module.

Recommended first learning tasks:

- Run `pytest -q` and read failures by temporarily breaking one rule in `app/services/ranker.py`.
- Trace one scan request from `POST /api/scans` through `run_scan` and into generated `storage/scan-*-llms.txt` output.
- Add one ranking heuristic with a matching unit test to get familiar with the development loop.

## Render Deployment

This repo includes `.python-version` to pin Render to Python 3.13. The dependency set uses packages with compiled wheels, including `pydantic-core`, so avoid deploying on a newer Python runtime until the pinned dependencies publish compatible wheels.

The hosted demo runs on Render. If you attach a persistent disk mounted at
`/var/data`, configure `STORAGE_DIR=/var/data` so SQLite data and generated
files persist across restarts/redeploys.

Recommended Render settings:

- Service type: Web Service.
- Runtime: Python.
- Build command: `pip install -r requirements.txt`.
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Instance type: choose any paid instance tier that supports your expected traffic and the attached persistent disk.
- Persistent disk: mount at `/var/data` for durable demo data.
- Database: `STORAGE_DIR/app.sqlite3` (for example `/var/data/app.sqlite3`).
- Generated files: local files under `STORAGE_DIR/`.
- Optional environment variables:
  - `CRAWL_MAX_PAGES=100`
  - `CRAWL_MAX_DEPTH=2`
  - `CRAWL_MAX_DURATION_SECONDS=30`
  - `CRAWL_MAX_CONCURRENCY=10`
  - `CRAWL_MAX_SITEMAPS=10`
  - `STORAGE_DIR=/var/data` (recommended when using a Render disk mount)

Render will provide the `$PORT` environment variable. The app creates `storage/` and SQLite tables at startup.

Operational caveats:

- Data durability depends on whether `STORAGE_DIR` points to persistent disk storage.
- If `STORAGE_DIR` is left at the default `storage/` path, previous scan history and download files may disappear after restart/redeploy.
- For a demo, open the app shortly before presenting and generate a fresh `llms.txt`.

Hosted demo smoke checklist:

1. Open the Render service URL.
2. Enter `example.com`.
3. Wait for the scan to complete.
4. Download the generated `llms.txt`.
5. Confirm the file starts with `# Example Domain` and contains a `## Key Pages` section.
6. Run `example.com` again.
7. Confirm the second scan has the next version number and a compact change summary.
