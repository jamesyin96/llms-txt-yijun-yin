# Manual QA Notes

## 2026-05-09 Ranking Quality Pass

Goal: test generated `llms.txt` quality across different public website shapes and tune obvious ranking issues found during the pass.

Method:

- Used the real crawler, ranker, formatter, and validator.
- Used bounded crawl settings for speed: `max_pages=20`, `max_depth=1`.
- Wrote temporary generated files to `/private/tmp/llms-qa/`.
- Checked section distribution, top-ranked URLs, validation result, and obvious low-value inclusions.

## Sites Tested

| Site type | URL | Result |
| --- | --- | --- |
| Simple marketing | `https://example.com/` | Valid output with one `Key Pages` entry. |
| Framework/docs/blog | `https://www.djangoproject.com/` | Valid output with homepage plus weblog pages grouped under `Articles`. |
| Documentation | `https://docs.python.org/3/` | Valid output with documentation pages grouped under `Documentation`; image output capped. |
| Product/docs | `https://www.sqlite.org/` | Valid output with product, documentation, guide, support, company, and image sections. |
| Policy/government | `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm` | Valid output; feed/sitemap/subscribe pages removed after tuning; image output capped. |
| Research/archive | `https://arxiv.org/list/cs.AI/recent` | Query-heavy pagination pages removed after tuning; actual list/article pages remain. |

## Findings And Fixes

- **Too many images in documentation/policy sites.**
  - Finding: Python docs and Federal Reserve scans included many image resources.
  - Fix: cap `Images` output to three resources per generated file.

- **HTML filenames were not tokenized well enough for section assignment.**
  - Finding: SQLite pages like `quickstart.html` and `lang.html` stayed in generic `Key Pages`.
  - Fix: tokenize filename stems in URL paths, so `quickstart.html` contributes `quickstart` and `lang.html` contributes `lang`.

- **Utility pages were still included.**
  - Finding: feed, sitemap, subscribe, copyright, and license-style pages were allowed in some outputs.
  - Fix: add plural/feed/sitemap/subscribe/copyright/license terms to low-value URL filtering.

- **Query-heavy archive/list pagination crowded out useful pages.**
  - Finding: arXiv pagination URLs like `?skip=100&show=50` were included.
  - Fix: strengthen query-string penalty so query-heavy list pages fall below the include threshold.

## Remaining Tuning Ideas

- Add a small language-route filter or lower ranking for paths like `/es`, `/ru`, `/ko`, `/vi`, and `/zh-hans` when the root page is English.
- Improve detection of site logos and institution badges that pass image classification because they have alt text.
- Add richer PDF-oriented testing with a site where PDF links are discoverable inside the bounded crawl.
- Consider a small per-section cap for `Articles` so news-heavy sites do not dominate the output.
- Add optional detailed QA snapshots for generated files if we want persistent fixtures later.
