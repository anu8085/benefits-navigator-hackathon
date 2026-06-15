from __future__ import annotations
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_DIR = PROJECT_ROOT / "sample_data"
LOCAL_STATE_DIR = PROJECT_ROOT / ".local_state"
LOCAL_STATE_DIR.mkdir(exist_ok=True)
SQLITE_PATH = LOCAL_STATE_DIR / "benefitbridge_local.db"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")
CLAUDE_AVAILABLE = bool(ANTHROPIC_API_KEY)
