# LLMs.txt Generator

Python/FastAPI web app that accepts a website URL, scans it, and returns a downloadable `llms.txt` file.

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

## Current Scope

- Plain HTML frontend with a centered URL input and Go button.
- FastAPI backend.
- SQLite local database.
- Local generated file storage under `storage/`.
- Initial scan lifecycle endpoints.

Crawler, robots handling, sitemap discovery, ranking, PDF/image handling, and re-scan change detection will be added in follow-up implementation phases from `IMPLEMENTATION_PLAN.md`.

## Render Free Tier

The first hosted demo can use Render's free web service tier. SQLite data and generated files are stored on the regular filesystem, which is ephemeral on Render. Download links are best-effort and may disappear after restart or redeploy.

Render start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
