from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RUNTIME = ROOT / "runtime"
PILOT = DATA / "pilot.json"

load_dotenv(ROOT / ".env")
# The shared repo-root .env (GEMINI_API_KEY, GROQ_API_KEY, ...); never overrides what's set
load_dotenv(ROOT.parent / ".env")
