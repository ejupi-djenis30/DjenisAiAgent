import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# Load the API Key from the environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Load the Model Name from the environment, with a default value
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found. Make sure you have created a .env file in the root folder and added your API key.")
