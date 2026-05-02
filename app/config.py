"""Central application settings.

The project is intentionally small for V1, so configuration lives in this
module instead of a larger settings framework. Values here are imported by the
web app, database setup, and scanner services.
"""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
DATABASE_URL = f"sqlite:///{STORAGE_DIR / 'app.sqlite3'}"

APP_NAME = "LLMs.txt Generator"
USER_AGENT = "llms-txt-generator/0.1"
