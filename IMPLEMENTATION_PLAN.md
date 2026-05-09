# LLMs.txt Generator Implementation Plan

## Goal

Build a web application where a user enters a website URL and receives a generated `llms.txt` file that summarizes the site's structure and links to important pages in the format described by [llmstxt.org](https://llmstxt.org/).

This plan intentionally skips external submission and collaborator-sharing steps while the project is still in development. Deployment, GitHub repo sharing, screenshots, and demo packaging can be handled after local functionality and testing are complete.

## Requirements Summary

From `LLMs.txt Generator - Version 3.pdf`:

- User can visit a web app directly and enter a website URL.
- App crawls the website to identify key pages.
- App extracts metadata such as page titles, descriptions, and URLs.
- App generates a valid `llms.txt` file.
- App follows the `llms.txt` specification.
- App includes an automated update or monitoring mechanism to detect website changes and refresh generated output.
- App includes clear setup, configuration, and usage documentation.
- Solution should work across a large variety of websites.
- Code should be readable, maintainable, and explainable.
- Product thinking and useful UX improvements are encouraged.

## Scope For Development Stage

### In Scope

- Local web application.
- Simple URL input and Go button.
- Website crawling with sensible limits.
- Metadata extraction.
- Generated `llms.txt` file download.
- Change detection for previously analyzed sites.
- Local persistence for generated projects and crawl snapshots.
- README with local setup and usage instructions.
- Tests for crawler, parser, formatter, and update detection.

### Deferred Until After Testing

- Public deployment.
- Sharing GitHub repo with external collaborators.
- Submission-specific screenshots or demo video.
- Production authentication.
- Multi-user billing or account management.
- Paid hosting resources or persistent disks.

## Proposed Tech Stack

- Backend framework: Python with FastAPI.
- Frontend: Plain server-rendered HTML template with minimal CSS and vanilla JavaScript.
- Template engine: Jinja2.
- Crawler: Python async HTTP crawler using `httpx`, `beautifulsoup4`, and standard URL parsing.
- Persistence: SQLite for local storage.
- Database access: SQLAlchemy or SQLModel.
- Background execution: FastAPI background task for the first version; upgradeable to a worker later.
- Generated files: Store generated `llms.txt` files under a local `storage/` directory and expose a download URL.
- Tests: Pytest for unit and integration tests.

This stack keeps the project Python-first and avoids React. The frontend can stay intentionally small: one centered URL input, one Go button, a progress/status area, and a download link when generation finishes.

## V1 Product Decisions

- Keep the frontend intentionally minimal.
- Do not build a React app.
- Do not show an editable `llms.txt` preview in V1.
- Do not build include/exclude controls in V1.
- Generate descriptions from metadata, headings, link text, alt text, filenames, and surrounding context only.
- Do not add AI-generated summaries in V1.
- Generate the file server-side and show a download link when ready.
- Use SQLite and local file storage.
- Use manual re-scan with diff/change summary as the V1 update mechanism.
- Treat scheduled monitoring as a future upgrade.

## Hosting Plan

Use Render's free web service tier for the initial demo.

- Deploy the FastAPI app as one Render web service.
- Use the regular filesystem for SQLite and generated `llms.txt` files during the demo.
- Accept that Render's free filesystem is ephemeral: data can be lost when the service restarts or redeploys.
- This is acceptable for the current demo because users only need the generated file during the active session.
- Generated download links are best-effort on the free tier and may stop working after a restart, redeploy, or cold-start replacement.
- Demo prep should include opening the app shortly before presenting and generating a fresh file if needed.
- If the project needs more reliable persistence later, upgrade to a paid Render instance with a persistent disk or move storage to Postgres/object storage.
- Keep the app start command Render-friendly: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

## llms.txt Format Target

The generator should output Markdown in this shape:

```md
# Site or Project Name

> Short summary of the website.

Optional additional context about the site and how to interpret the linked resources.

## Key Pages

- [Page title](https://example.com/page): Brief description or inferred page purpose.

## Optional

- [Secondary page](https://example.com/secondary): Less central but potentially useful resource.
```

Rules to preserve:

- The H1 site name is required.
- The blockquote summary is optional but strongly preferred.
- H2 sections should group file lists.
- File list items should use markdown links.
- Link descriptions should be concise and useful.
- The `Optional` section should contain secondary pages that can be skipped for shorter context.

## Product Shape

### Primary User Flow

1. User opens the app.
2. User enters a website URL.
3. User clicks Go.
4. Frontend calls the Python backend to start a scan.
5. App shows a simple loading/status state.
6. Backend crawls the site, extracts metadata, generates `llms.txt`, and stores the result.
7. Frontend shows a download link when generation is complete.
8. User clicks the link to download the generated file.

### Useful UX Details

- Validate and normalize URLs before crawling.
- Show crawl status: queued, crawling, generating, complete, failed.
- Show a friendly error if a site cannot be fetched or produces no useful pages.
- Keep the first screen quiet and simple: centered URL input, Go button, and result area.
- Save scan history locally so a generated file can be downloaded again.
- Defer richer controls like include/exclude pages, editable sections, and preview editing until after the basic flow works.

## System Architecture

### Frontend

- One centered URL input form.
- Go button.
- Status message while the backend scans.
- Download link after generation completes.
- Optional basic change summary after a re-scan.

### Backend

- URL normalization and validation.
- Security checks for user-submitted URLs.
- HTTP fetching with timeout, retry, redirect, and response-size controls.
- Robots.txt parsing and sitemap hint extraction.
- Sitemap parsing and URL discovery.
- HTML link discovery.
- Crawler orchestration.
- Metadata extraction.
- Page scoring and categorization.
- `llms.txt` formatting.
- Persistence layer.
- File storage and download endpoint.
- Monitoring/update checks.

### Data Flow

1. `GET /` returns the simple HTML page.
2. `POST /api/scans` receives a URL.
3. Backend creates a scan record and starts work.
4. Crawler discovers pages using sitemap, robots hints, internal links, and canonical URLs.
5. Extractor fetches page metadata and readable content signals.
6. Scorer ranks pages by likely importance.
7. Formatter creates a spec-conforming `llms.txt`.
8. Backend writes the generated file to local storage and updates the scan record.
9. Frontend polls `GET /api/scans/{id}` until the scan is complete.
10. Frontend displays `GET /download/{id}` as the download link.
11. Monitoring re-fetches known URLs and checks content hashes or metadata changes.

## Modularization Plan

Keep implementation components small and independently testable. The scanner should orchestrate modules; it should not contain all crawling, parsing, ranking, formatting, and persistence logic in one file.

Suggested service layout:

- `app/services/url_utils.py`: URL normalization, canonicalization, same-host checks, and URL type helpers.
- `app/services/security.py`: SSRF protection, DNS/IP validation, redirect safety checks, and blocked network ranges.
- `app/services/fetcher.py`: Shared HTTP client with timeout, retry/backoff, user-agent, content-type detection, max response size, and safe redirect handling.
- `app/services/robots.py`: `robots.txt` fetching/parsing, allow/disallow decisions, crawl-delay if supported later, and sitemap hints.
- `app/services/sitemap.py`: Sitemap index and URL-set parsing.
- `app/services/html_parser.py`: HTML metadata extraction, canonical URL extraction, heading extraction, internal link discovery, image discovery, and link context.
- `app/services/resource_classifier.py`: Resource type detection and PDF/image/icon/static-asset inclusion rules.
- `app/services/crawler.py`: Crawl queue, depth/page limits, deduplication, sitemap-first discovery, homepage/internal-link fallback, and crawl result assembly.
- `app/services/ranker.py`: Page scoring, low-value filtering, and section assignment.
- `app/services/formatter.py`: Markdown-only `llms.txt` rendering.
- `app/services/scanner.py`: Scan lifecycle orchestration, database writes, file writes, and error handling.
- `app/services/change_detector.py`: Manual re-scan comparison and added/changed/removed summaries.

Module boundaries:

- Network requests must go through `fetcher.py`.
- Fetch safety checks must go through `security.py`.
- Parsing modules should not write to the database.
- Ranking should operate on plain crawl result objects, not ORM models.
- Formatting should accept plain resource objects and return Markdown text.
- Persistence should stay in `scanner.py` or a small repository layer if the scanner grows too large.
- Tests should target modules directly before relying on end-to-end tests.

## V1 API Contract

### `GET /`

Returns the single-page HTML UI.

### `POST /api/scans`

Starts a scan.

Request:

```json
{
  "url": "https://example.com"
}
```

Response:

```json
{
  "scan_id": 1,
  "status": "queued"
}
```

### `GET /api/scans/{scan_id}`

Returns current scan status.

Response:

```json
{
  "scan_id": 1,
  "status": "complete",
  "root_url": "https://example.com",
  "pages_found": 42,
  "pages_included": 31,
  "download_url": "/download/1",
  "error": null
}
```

### `GET /download/{scan_id}`

Downloads the generated `llms.txt` file for a completed scan.

### `POST /api/scans/{scan_id}/rescan`

Runs the same URL again and compares the new crawl with the prior scan.

Response:

```json
{
  "scan_id": 2,
  "previous_scan_id": 1,
  "status": "queued"
}
```

## Core Modules

### URL Normalization

Responsibilities:

- Accept user input like `example.com` and normalize to `https://example.com`.
- Resolve relative URLs.
- Remove fragments.
- Normalize trailing slashes consistently.
- Keep crawling limited to the same hostname by default.
- Reject unsupported schemes such as `file:`, `ftp:`, `data:`, and `javascript:`.

### Security Checks

Responsibilities:

- Block localhost URLs.
- Block private, loopback, link-local, and multicast IP addresses.
- Resolve hostnames before fetching and reject blocked IP ranges.
- Re-check redirects so a public URL cannot redirect to a blocked internal address.
- Limit redirects.
- Enforce the same-hostname crawl rule.
- Enforce request timeout and response size limits.

### Crawler

Responsibilities:

- Start from the homepage.
- Obey `robots.txt`.
- Fetch sitemap URLs first when allowed.
- Crawl homepage links after sitemap discovery.
- Respect page limits, depth limits, timeouts, and content types.
- Discover internal links from HTML.
- Include PDF URLs when discovered.
- Include image URLs when discovered if the image appears content-like rather than icon-like.
- Avoid duplicate URLs and crawl traps.
- Capture crawl errors without failing the whole run.

Initial crawl settings:

- Max pages: 100.
- Max depth: 2.
- Request timeout: 10 seconds.
- Retries: 3 attempts with backoff.
- Same host only.
- HTML pages are fetched for metadata and link discovery.
- PDF and qualifying image URLs are included in output but not deeply parsed in V1.

PDF and image handling:

- Include same-host PDF URLs found in sitemaps or crawled pages.
- Include same-host image URLs when they are likely meaningful content images.
- Skip likely icons and decorative assets using filename/path hints such as `favicon`, `icon`, `logo`, `sprite`, `apple-touch-icon`, and tiny image dimensions when available.
- Skip generic static assets such as CSS, JavaScript, fonts, videos, archives, and source maps.
- Use link text, `alt`, filename, or surrounding page title as the description source for non-HTML URLs.

### Metadata Extractor

Extract:

- URL.
- Title.
- Meta description.
- Canonical URL.
- Open Graph title and description.
- Headings, especially H1.
- Main text excerpt or page summary signal.
- HTTP status.
- Content hash.
- Last crawled timestamp.

### Page Scoring

V1 uses a transparent heuristic ranker, not ML or AI. The goal is to make the
generated `llms.txt` useful and explainable across common website shapes while
keeping the rules easy to tune after manual testing.

Ranker inputs:

- `CrawlResource.url` and URL path tokens.
- `resource_type`, especially HTML, PDF, and meaningful image.
- `title`, `description`, `h1`, `link_text`, and `headings`.
- Whether the resource is the normalized homepage.
- Whether the resource came from the sitemap or from a crawled page.

Ranker output:

- `resource`: the original crawl resource.
- `score`: numeric importance score.
- `section`: display section for `llms.txt`.
- `include`: whether the resource should appear in the generated file.
- `reason`: short explanation for tests/debugging.

Positive scoring signals:

- Homepage: strongest signal; always included as `Key Pages`.
- Documentation, API, reference, developer, docs paths/titles: high score, section `Documentation`.
- Guides, tutorials, learn, getting-started paths/titles: high score, section `Guides`.
- Product, features, solutions, pricing paths/titles: medium-high score, section `Products or Services`.
- About, company, team, careers paths/titles: medium score, section `Company`.
- Support, help, contact, FAQ paths/titles: medium score, section `Support`.
- Blog, news, articles, changelog paths/titles: medium score, section `Articles`.
- PDFs: medium score when link text/title/filename looks meaningful, section `Documents`.
- Images: lower score than pages, included only when the crawler has already classified them as meaningful, section `Images`.
- Descriptive title, description, H1, or link text: small positive boosts.

Negative scoring signals:

- Login, signup, auth, account, dashboard, admin.
- Cart, checkout, payment, billing.
- Search result pages and query-heavy URLs.
- Tag/category/archive/page pagination URLs.
- Feed, RSS, Atom, print, share, embed.
- Terms, privacy, cookie, legal, license pages.
- Very thin metadata, except for the homepage.

V1 inclusion rules:

- Keep the homepage even when metadata is thin.
- Include resources with score at or above the V1 threshold.
- Exclude strongly low-value pages even if discovered by sitemap.
- Cap image resources so image-heavy sites do not dominate `llms.txt`.
- Sort by section priority, then score descending, then URL.
- Keep the output cap aligned with crawler max pages: 100 included resources.

### Section Builder

Suggested default sections:

- `Key Pages`
- `Products or Services`
- `Documentation`
- `Guides`
- `Articles`
- `Company`
- `Support`
- `Documents`
- `Images`
- `Optional`

The section builder should only include sections with matching pages. For smaller sites, a simple `Key Pages` section is acceptable.

### llms.txt Formatter

Responsibilities:

- Produce clean Markdown.
- Escape problematic markdown characters in titles.
- Use absolute URLs.
- Keep descriptions short.
- Preserve required section order.
- Include `Optional` only for secondary resources.

### Monitoring And Updates

Development-stage monitoring can be local and manual-first:

- Store each crawl snapshot.
- Provide a "Check for updates" button.
- Re-fetch known URLs and optionally discover new sitemap/internal links.
- Compare content hashes, titles, descriptions, and discovered URL set.
- Show changed, added, removed, and unchanged pages.
- Regenerate `llms.txt` after user confirmation.

Later production options:

- Scheduled background checks.
- Email/webhook notifications.
- Queue-backed crawl workers.

## V1 Data Model

### Scan

- `id`
- `rootUrl`
- `normalizedRootUrl`
- `status`
- `pagesFound`
- `pagesIncluded`
- `outputPath`
- `previousScanId`
- `changeSummary`
- `error`
- `createdAt`
- `finishedAt`

### Page

- `id`
- `scanId`
- `url`
- `canonicalUrl`
- `title`
- `description`
- `resourceType`
- `section`
- `score`
- `statusCode`
- `contentHash`
- `lastCrawledAt`
- `included`

### Change

- `id`
- `scanId`
- `previousScanId`
- `url`
- `changeType`
- `before`
- `after`
- `createdAt`

`Change` can be added in the monitoring phase. The first generator flow only requires `Scan` and `Page`.

## Implementation Phases

### Phase 1: Project Setup

- Initialize Python app with FastAPI.
- Add `requirements.txt` or `pyproject.toml`.
- Add pytest and formatting/linting.
- Create app structure: `app/main.py`, `app/templates/`, `app/static/`, `app/services/`, `app/models.py`, `app/db.py`.
- Create local `storage/` directory for generated files.
- Add README skeleton.

### Phase 2: Basic Generator

- Build URL input form.
- Implement URL normalization.
- Add SSRF/security checks for submitted URLs.
- Add scan creation and status endpoints.
- Fetch homepage.
- Extract homepage title and description.
- Generate minimal valid `llms.txt`.
- Store generated file locally.
- Display download link when complete.

### Phase 3: Crawler

- Add `robots.txt` fetching and allow/disallow checks.
- Add sitemap discovery and crawl sitemap URLs first.
- Add homepage/internal link discovery after sitemap URLs.
- Add crawl limits and timeout handling.
- Add 3-attempt retry with backoff.
- Add duplicate filtering.
- Add PDF URL inclusion.
- Add non-icon image URL inclusion.
- Show crawl progress and errors.

### Phase 4: Metadata And Ranking

- Extract richer metadata.
- Score pages by importance.
- Filter low-value pages.
- Categorize pages into sections.
- Generate descriptions for HTML, PDF, and image resources from available metadata, link text, alt text, filenames, and surrounding context.

### Phase 5: Persistence

- Add SQLite database.
- Save scans, pages, generated output path, and errors.
- Save scan status and output path.

### Phase 6: Monitoring

- Add manual "Check for updates" flow.
- Re-crawl saved site.
- Compare page hashes and metadata.
- Show added, changed, removed pages.
- Regenerate `llms.txt` from updated crawl data.

### Phase 7: Polish And Documentation

- Improve empty, loading, and error states.
- Add README setup and usage instructions.
- Document Render free-tier caveats for ephemeral SQLite/files.
- Document architecture and trade-offs.
- Add sample generated outputs.

### Phase 8: Testing

- Unit test URL normalization.
- Unit test security blocking for localhost and private IP ranges.
- Unit test robots.txt allow/disallow behavior.
- Unit test metadata extraction using fixture HTML.
- Unit test `llms.txt` formatting.
- Unit test change detection.
- Unit test retry/backoff behavior with mocked transient failures.
- Integration test crawl against local fixture site.
- End-to-end test primary user flow in browser.

## Testing Strategy

### Unit Tests

- URL normalization handles missing protocol, fragments, relative links, duplicate slashes, and trailing slash consistency.
- Security checks block unsafe schemes, localhost, private IP ranges, and redirects to blocked hosts.
- Robots handling skips disallowed URLs and allows permitted URLs.
- Formatter always emits valid Markdown structure.
- Extractor handles missing title, missing description, Open Graph fallback, canonical URLs, and malformed HTML.
- Crawler includes same-host PDFs and qualifying content images.
- Crawler skips icons, decorative images, and generic static assets.
- Retry logic makes up to 3 attempts and respects the 10-second per-page timeout.
- Scorer deprioritizes low-value paths.

### Integration Tests

- Fixture website with sitemap.
- Fixture website without sitemap.
- Fixture website with `robots.txt` rules.
- Fixture website with PDFs, content images, icons, and static assets.
- Fixture website with duplicate/canonical URLs.
- Fixture website with broken links.
- Fixture website with changed content between runs.

### Manual Tests

Try a mix of websites:

- Small marketing site.
- Documentation site.
- Blog.
- E-commerce-like site.
- Site with sitemap.
- Site without sitemap.
- Site with public PDFs or media resources.
- Site with many irrelevant pages.

## Risks And Mitigations

- Some sites block crawlers: show clear errors and support user-agent configuration later.
- JavaScript-rendered content may be sparse with plain fetch: start with HTML metadata, then consider Playwright rendering for selected pages.
- Large sites can explode crawl size: enforce strict limits and expose settings.
- Generated descriptions may be weak from metadata alone: use metadata/link text/filenames first and consider optional LLM-assisted summaries later.
- Free Render services can restart or replace ephemeral storage: clearly state generated links are temporary and regenerate before demos.
- Some meaningful images may be misclassified as icons or decorative assets: start with conservative filename/path/dimension heuristics and improve after manual testing.
- `llms.txt` spec is lightweight and evolving: isolate formatter logic and document assumptions.

## Open Product Decisions

- Should the first version support authenticated/private sites?
- Should image inclusion use only heuristics in V1, or should we add a richer image classifier later?
- Should scheduled monitoring be added after manual re-scan works?

## Initial Milestone Target

The first meaningful milestone is a local app that can:

- Accept a URL.
- Obey `robots.txt`.
- Crawl sitemap URLs first, then homepage/internal links.
- Crawl up to 100 same-host URLs at max depth 2.
- Include same-host PDFs and non-icon images in generated output.
- Extract titles, descriptions, canonical URLs, headings, status codes, and content hashes.
- Rank and group key pages.
- Generate a valid downloadable `llms.txt`.
- Save the result locally.
- Re-run analysis manually and show a basic change summary.
