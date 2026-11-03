import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEPARTMENTS_DIR = BASE_DIR / "departments"
DATA_DIR = BASE_DIR / "backend" / "data"
VECTOR_DB_PATH = DATA_DIR / "vector_store.db"

# Ensure data dir exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Application metadata
APP_NAME = "Pixelvyne Smart Assistant API"
APP_VERSION = "1.0.0"
MUNICIPALITY_NAME = "City of Pixelvyne"

# Database & pgvector settings
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgrespassword@localhost:5432/civiciq")
VECTOR_STORE_PROVIDER = os.getenv("VECTOR_STORE_PROVIDER", "pgvector")

# RAG parameters
SIMILARITY_THRESHOLD = 0.10  # Strict minimum relevance threshold for grounded retrieval
TOP_K_RESULTS = 3
CHUNK_SIZE_WORDS = 120
CHUNK_OVERLAP_WORDS = 25
