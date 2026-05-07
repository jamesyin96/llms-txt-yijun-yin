# LLMs.txt Generator

Python/FastAPI web app that accepts a website URL, scans it, and returns a downloadable `llms.txt` file.

## What Works Now

- Plain HTML frontend with a centered URL input and Go button.
- FastAPI backend.
- SQLite local database.
- Local generated file storage under `storage/`.
- Scan lifecycle endpoints:
  - `POST /api/scans`
  - `GET /api/scans/{scan_id}`
  - `GET /download/{scan_id}`
- SSRF-oriented URL safety checks.
- Safe HTTP fetcher with timeout, retry, redirect checks, and response-size limits.
- `robots.txt` fetching and allow/disallow handling.
- Sitemap-first discovery with `/sitemap.xml` fallback.
- Homepage/internal HTML link extraction.
- Metadata extraction from title, meta description, canonical URL, headings, and link context.
- PDF inclusion.
- Meaningful image inclusion with icon/static-asset filtering.
- Generated `llms.txt` validation before writing the downloadable file.
- Per-site version numbers for repeated scans of the same normalized URL.
- Versioned generated files, stored as `scan-{scan_id}-v{version_number}-llms.txt`.

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

## Testing

Run the test suite:

```bash
conda activate myenv
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
2. Click `Go`.
3. Wait for the status to complete.
4. Click the versioned download link, such as `Download llms-v1.txt`.
5. Confirm the downloaded file starts with an H1 title, includes a blockquote summary when available, and contains Markdown links under section headings.
6. Enter the same website URL again and confirm the next completed scan shows the next version number.

Optional API-only check:

```bash
curl -s -X POST http://127.0.0.1:8000/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"url":"example.com"}'
```

Use the returned `scan_id`:

```bash
curl -s http://127.0.0.1:8000/api/scans/1
curl -s http://127.0.0.1:8000/download/1
```

The API status response includes both a global `scan_id` and a per-site `version_number`. The `scan_id` is the database primary key across all websites. The `version_number` increases only for scans with the same normalized root URL, so scanning `example.com`, then another site, then `example.com` again creates `example.com` versions 1 and 2 while preserving each scan row and generated file separately.

Recent verified state:

- `pytest -q` passes.
- Real generated `llms.txt` tested with `example.com` through the web app flow.
- Real crawler/formatter output tested with `https://www.djangoproject.com/`.

## Remaining Work

- Improve ranking beyond simple URL/category heuristics.
- Add a dedicated re-scan button/history view.
- Add change detection between stored versions.
- Add broader manual quality testing across docs, blogs, marketing sites, and PDF-heavy sites.
- Add deployment instructions after local testing is stable.

## Render Free Tier

The first hosted demo can use Render's free web service tier. SQLite data and generated files are stored on the regular filesystem, which is ephemeral on Render. Download links are best-effort and may disappear after restart or redeploy.

Render start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
