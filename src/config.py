import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# --- Gemini API Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# --- Agent Behavior Configuration ---
try:
    MAX_STEPS = int(os.getenv("MAX_STEPS", 15))
except (ValueError, TypeError):
    print("Warning: MAX_STEPS in .env is not a valid integer. Defaulting to 15.")
    MAX_STEPS = 15

# --- Sanity Checks ---
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found. Make sure you have created a .env file in the root folder and added your API key.")
