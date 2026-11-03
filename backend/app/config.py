import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEPARTMENTS_DIR = BASE_DIR / "departments"
DATA_DIR = BASE_DIR / "backend" / "data"
VECTOR_DB_PATH = DATA_DIR / "vector_store.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Application & Municipality Metadata
APP_NAME = "CivicIQ"
APP_TAGLINE = "Your civic intelligence buddy"
APP_VERSION = "2.1.0"
MUNICIPALITY_NAME = "Township of Edison, New Jersey"
OFFICIAL_PORTAL_URL = "https://www.edisonnj.org/document_center/index.php"
OFFICIAL_DOCUMENT_CENTER_URL = "https://www.edisonnj.org/document_center/index.php"
MUNICIPAL_ADDRESS = "100 Municipal Blvd, Edison, NJ 08817"
ENGINEERING_PHONE = "(732) 248-7288"
ENGINEERING_EMAIL = "engineering@edisonnj.gov"

# Out-of-context response message
OUT_OF_CONTEXT_MESSAGE = "Sorry, this information is out of our context. Please visit https://www.edisonnj.org/document_center/index.php for more information."

# Active Department (Single focus: Engineering)
ACTIVE_DEPARTMENTS = ["engineering"]
PLANNED_DEPARTMENTS = []

# Database & pgvector settings
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgrespassword@localhost:5432/civiciq")
VECTOR_STORE_PROVIDER = os.getenv("VECTOR_STORE_PROVIDER", "pgvector")

# Vector & Embeddings Settings
EMBEDDING_DIM = 128
SIMILARITY_THRESHOLD = 0.075
TOP_K_RESULTS = 4
CHUNK_SIZE_WORDS = 130
CHUNK_OVERLAP_WORDS = 30

# LLM Configuration (Google Gemini preferred, Groq / OpenAI as alternative)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto") # "gemini", "groq", "openai", "none", or "auto"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# Groq / OpenAI Alternative
GROQ_API_KEY = os.getenv("GROQ_API_KEY", os.getenv("OPENAI_API_KEY", ""))
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Security
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "civiciq-edison-admin-2026")
