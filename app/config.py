"""Central application settings.

The project is intentionally small for V1, so configuration lives in this
module instead of a larger settings framework. Values here are imported by the
web app, database setup, and scanner services.
"""

from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))).expanduser()
DATABASE_URL = f"sqlite:///{STORAGE_DIR / 'app.sqlite3'}"

APP_NAME = "LLMs.txt Generator"
USER_AGENT = "llms-txt-generator/0.1"


def int_setting(name: str, default: int) -> int:
    """Read a positive integer environment setting with a safe fallback."""

    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def float_setting(name: str, default: float) -> float:
    """Read a positive float environment setting with a safe fallback."""

    try:
        value = float(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


CRAWL_MAX_PAGES = min(int_setting("CRAWL_MAX_PAGES", 100), 500)
CRAWL_MAX_DEPTH = min(int_setting("CRAWL_MAX_DEPTH", 2), 5)
CRAWL_MAX_DURATION_SECONDS = min(float_setting("CRAWL_MAX_DURATION_SECONDS", 30.0), 60.0)
CRAWL_MAX_CONCURRENCY = min(int_setting("CRAWL_MAX_CONCURRENCY", 10), 20)
