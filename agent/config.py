import os
from dotenv import load_dotenv
from supabase import create_client
from google import genai

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
LLM_MODEL = "gemini-2.0-flash"

if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL missing")

if not SUPABASE_KEY:
    raise ValueError("SUPABASE_SERVICE_ROLE_KEY missing")


def get_supabase():
    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
    )


def get_gemini():
    return genai.Client()