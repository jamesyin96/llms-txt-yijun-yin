from pathlib import Path

from app.db import Base
from app.models import Page, Scan
from app.services.crawler import CrawlResource, CrawlResult
from app.services.formatter import validate_llms_txt
from app.services.resource_classifier import ResourceType
from app.services.scanner import _run_scan


def test_run_scan_persists_crawl_resources_and_generated_file(tmp_path, monkeypatch):
    import app.config as config
    import app.services.scanner as scanner

    monkeypatch.setattr(config, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(scanner, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(
        scanner,
        "crawl_site",
        lambda root_url, crawl_config: CrawlResult(
            root_url=root_url,
            resources=(
                CrawlResource(
                    url=root_url,
                    resource_type=ResourceType.HTML,
                    title="Example Site",
                    description="Example site description.",
                    canonical_url=root_url,
                    h1="Example",
                    status_code=200,
                    content_hash="abc123",
                ),
                CrawlResource(
                    url="https://example.com/report.pdf",
                    resource_type=ResourceType.PDF,
                    link_text="Annual Report",
                ),
                CrawlResource(
                    url="https://example.com/chart.png",
                    resource_type=ResourceType.IMAGE,
                    description="Revenue chart",
                ),
            ),
        ),
    )

    db = _fresh_db_session(tmp_path)
    scan = Scan(
        root_url="example.com",
        normalized_root_url="https://example.com/",
        status="queued",
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    _run_scan(scan.id, db)

    db.refresh(scan)
    pages = db.query(Page).order_by(Page.id).all()
    generated = Path(tmp_path / scan.output_path).read_text(encoding="utf-8")

    assert scan.status == "complete"
    assert scan.pages_found == 3
    assert scan.pages_included == 3
    assert len(pages) == 3
    assert pages[0].title == "Example Site"
    assert pages[0].resource_type == "html"
    assert pages[1].section == "Documents"
    assert pages[2].section == "Images"
    assert generated.startswith("# Example Site")
    assert "> Example site description." in generated
    assert "## Key Pages" in generated
    assert "- [Example Site](https://example.com/): Example site description." in generated
    assert "## Documents" in generated
    assert "- [Annual Report](https://example.com/report.pdf): Annual Report" in generated
    assert "## Images" in generated
    assert "- [chart.png](https://example.com/chart.png): Revenue chart" in generated
    assert validate_llms_txt(generated).valid


def test_run_scan_groups_common_page_types_into_sections(tmp_path, monkeypatch):
    import app.config as config
    import app.services.scanner as scanner

    monkeypatch.setattr(config, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(scanner, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(
        scanner,
        "crawl_site",
        lambda root_url, crawl_config: CrawlResult(
            root_url=root_url,
            resources=(
                CrawlResource(url=root_url, resource_type=ResourceType.HTML, title="Home"),
                CrawlResource(url="https://example.com/docs/api", resource_type=ResourceType.HTML, title="API"),
                CrawlResource(url="https://example.com/guides/start", resource_type=ResourceType.HTML, title="Start"),
                CrawlResource(url="https://example.com/blog/update", resource_type=ResourceType.HTML, title="Update"),
                CrawlResource(url="https://example.com/about", resource_type=ResourceType.HTML, title="About"),
                CrawlResource(url="https://example.com/support", resource_type=ResourceType.HTML, title="Support"),
            ),
        ),
    )

    db = _fresh_db_session(tmp_path)
    scan = Scan(root_url="example.com", normalized_root_url="https://example.com/", status="queued")
    db.add(scan)
    db.commit()
    db.refresh(scan)

    _run_scan(scan.id, db)

    generated = Path(tmp_path / scan.output_path).read_text(encoding="utf-8")
    assert "## Key Pages" in generated
    assert "## Documentation" in generated
    assert "## Guides" in generated
    assert "## Articles" in generated
    assert "## Company" in generated
    assert "## Support" in generated


def test_run_scan_marks_scan_failed_when_crawler_raises(tmp_path, monkeypatch):
    import app.config as config
    import app.services.scanner as scanner

    monkeypatch.setattr(config, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(scanner, "STORAGE_DIR", tmp_path)

    def failing_crawler(root_url, crawl_config):
        raise RuntimeError("crawler exploded")

    monkeypatch.setattr(scanner, "crawl_site", failing_crawler)

    db = _fresh_db_session(tmp_path)
    scan = Scan(
        root_url="example.com",
        normalized_root_url="https://example.com/",
        status="queued",
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    _run_scan(scan.id, db)

    db.refresh(scan)
    assert scan.status == "failed"
    assert scan.error == "crawler exploded"


def _fresh_db_session(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()
