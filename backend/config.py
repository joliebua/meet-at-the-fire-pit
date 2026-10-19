"""Paths, keys, model and run limits shared by every agent."""
from pathlib import Path
import json
import os

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
PROMPTS = Path(__file__).resolve().parent / "prompts"

# .env in the repo folder first, then one level above it (where staff keys live).
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")

MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# "live" hits the internet (and records what it sees); "snapshot" replays data/samples/<SNAPSHOT>/ offline.
SOURCE_MODE = os.getenv("VILLA_SOURCE_MODE", "live")
SNAPSHOT = os.getenv("VILLA_SNAPSHOT", "love_island_usa_s8")

USER_AGENT = "fire-pit/0.1 (MGT 409 student project; Love Island fantasy league)"


def portkey_key() -> str:
    key = os.getenv("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError("PORTKEY_API_KEY not found. Put it in .env here or one folder up (see .env.example).")
    return key


def prices() -> dict:
    return json.loads((DATA / "prices.json").read_text())[MODEL_NAME]
