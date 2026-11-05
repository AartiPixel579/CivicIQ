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
APP_TAGLINE = "Your Edison Township Buddy"
APP_VERSION = "2.2.0"
MUNICIPALITY_NAME = "Township of Edison, New Jersey"
OFFICIAL_PORTAL_URL = "https://www.edisonnj.org/document_center/index.php"
OFFICIAL_DOCUMENT_CENTER_URL = "https://www.edisonnj.org/document_center/index.php"
MUNICIPAL_ADDRESS = "100 Municipal Blvd, Edison, NJ 08817"
ENGINEERING_PHONE = "(732) 248-7288"
ENGINEERING_EMAIL = "engineering@edisonnj.gov"

# Out-of-context response message
OUT_OF_CONTEXT_MESSAGE = (
    "Sorry, this information is out of our context. "
    "I'm currently focused on Township of Edison Engineering services. "
    "I can help with the Engineering-related permits and procedures available here. "
    "Please visit https://www.edisonnj.org/document_center/index.php for other municipal services."
)

# Unconfigured / Unimplemented Engineering service message
UNCONFIGURED_SERVICE_MESSAGE = (
    "I'm currently able to assist with the Engineering services available in CivicIQ. "
    "This service hasn't been configured yet."
)

# Active Department (Single focus: Engineering)
ACTIVE_DEPARTMENTS = ["engineering"]
PLANNED_DEPARTMENTS = []

# Environment & Deployment Mode
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower().strip()
IS_PRODUCTION = ENVIRONMENT == "production"

# Database & pgvector settings
DATABASE_URL = os.getenv("DATABASE_URL", "")
VECTOR_STORE_PROVIDER = os.getenv("VECTOR_STORE_PROVIDER", "pgvector")

# Allowed CORS Origins (comma-separated list for production)
_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# Vector & Embeddings Settings
EMBEDDING_DIM = 128
SIMILARITY_THRESHOLD = 0.075
TOP_K_RESULTS = 4
CHUNK_SIZE_WORDS = 130
CHUNK_OVERLAP_WORDS = 30

# Generated PDF Drafts Storage Directory
GENERATED_DRAFTS_DIR = DATA_DIR / "generated_drafts"
GENERATED_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

# LLM Configuration (Provider Priority: Gemini (Primary) -> Groq (Fallback) -> Transparent Fallback)
LLM_PRIMARY_PROVIDER = os.getenv("LLM_PRIMARY_PROVIDER", "gemini").lower().strip()
LLM_FALLBACK_PROVIDERS = [
    p.strip().lower() for p in os.getenv("LLM_FALLBACK_PROVIDERS", "groq").split(",") if p.strip()
]

# 1. Primary: Google Gemini API (Free tier supported models)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# 2. Fallback: Groq API (Free developer tier supported models)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", os.getenv("OPENAI_API_KEY", ""))
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Timeout & Retry settings
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

# Backward compatibility alias
LLM_PROVIDER = os.getenv("LLM_PROVIDER", LLM_PRIMARY_PROVIDER)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Security
# In production, require an explicit secret from the environment. In dev/test, fallback safely.
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "" if IS_PRODUCTION else "civiciq-dev-admin-key")
