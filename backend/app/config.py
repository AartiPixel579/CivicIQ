import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEPARTMENTS_DIR = BASE_DIR / "departments"
DATA_DIR = BASE_DIR / "backend" / "data"
VECTOR_DB_PATH = DATA_DIR / "vector_store.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Application & Municipality Metadata
APP_NAME = "CivicIQ - Edison Township Resident Services Assistant"
APP_VERSION = "2.0.0"
MUNICIPALITY_NAME = "Township of Edison, New Jersey"
OFFICIAL_PORTAL_URL = "https://www.edisonnj.org/document_center/index.php"
OFFICIAL_DOCUMENT_CENTER_URL = "https://www.edisonnj.org/document_center/index.php"
MUNICIPAL_ADDRESS = "100 Municipal Blvd, Edison, NJ 08817"
ENGINEERING_PHONE = "(732) 248-7230"
ENGINEERING_EMAIL = "zoning@edisonnj.gov"

# Supported vs Planned Departments (MVP Focus: Engineering)
ACTIVE_DEPARTMENTS = ["engineering"]
PLANNED_DEPARTMENTS = ["healthcare", "animal_shelter", "clerk", "public_works", "code_enforcement"]

# Database & pgvector settings
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgrespassword@localhost:5432/civiciq")
VECTOR_STORE_PROVIDER = os.getenv("VECTOR_STORE_PROVIDER", "pgvector")

# Vector & Embeddings Settings
EMBEDDING_DIM = 128
SIMILARITY_THRESHOLD = 0.08  # Balanced for high recall on municipal terminology
TOP_K_RESULTS = 4
CHUNK_SIZE_WORDS = 130
CHUNK_OVERLAP_WORDS = 30

# LLM Configuration (OpenAI, Gemini, or Retrieval-Only Fallback)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto") # "openai", "gemini", "none", or "auto"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# Security
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "civiciq-edison-admin-2026")
