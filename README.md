# CivicIQ - Your Civic Intelligence Buddy

CivicIQ is an AI-powered municipal resident services assistant built for the **Township of Edison, New Jersey**. It guides citizens through official municipal procedures, permits, and engineering regulations using verified data from the official Edison Township Document Center ([edisonnj.org/document_center/index.php](https://www.edisonnj.org/document_center/index.php)).

CivicIQ is engineered under strict municipal standards:
1. **Official Link & Document Grounding (RAG)**: Answers inquiries strictly using verified municipal text retrieved from official Edison documents and codes. Zero hallucinations.
2. **Deterministic Flowcharts**: Guided step-by-step decision trees with mandatory prerequisite checks (e.g. verified property survey, Schedule A setbacks, NJ 811 utility ticket, restoration bonds).
3. **Official PDF Form Delivery (No AI-Generated Forms)**: Directly serves authentic, standardized municipal PDFs downloaded from Edison Township's official document repository. No synthetic form fields. Includes in-app document preview, download links, fill-in instructions, and attachment checklists.
4. **Departmental Routing & Graceful Referral**: Routes citizens to the verified submission desk (Division of Zoning, Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817). For inquiries regarding other municipal branches (e.g., cat adoption at the Edison Animal Shelter), CivicIQ provides exact departmental contacts and hours.

---

## 🏛️ Scope: Edison Township Department of Engineering

- **Municipality**: Township of Edison, Middlesex County, New Jersey
- **Active Department**: **Department of Engineering** (Engineering, DPW Road Openings, and Sewer Utility)
- **Official Source**: `https://www.edisonnj.org/document_center/index.php`
- **Submission Desk**: Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817 | (732) 248-7288 | `engineering@edisonnj.gov`
- **Supported Engineering Services**:
  1. Road opening & right-of-way street excavation permits (`RoadOpenApp.pdf`)
  2. Tree removal clearances & forestry preservation guidelines
  3. Municipal sanitary sewer connection & tap applications (`Sewer_Connection_Charge_Applications.pdf`)
  4. Residential building setbacks, plot plan requirements, and permits (`Zoning_Permit_Application_Edison.pdf`)

---

## 🐘 pgvector Setup & Storage Architecture

CivicIQ natively supports **pgvector (PostgreSQL)** for vector similarity search and comes with a built-in local SQLite fallback for seamless development without external dependencies.

### 1. Launch pgvector via Docker Compose
```bash
docker compose up -d
```
This starts PostgreSQL 16 with the native `pgvector` extension on port `5432` and runs [init_pgvector.sql](init_pgvector.sql).

### 2. Configure Environment (`.env`)
```env
DATABASE_URL=postgresql://postgres:postgrespassword@localhost:5432/civiciq
VECTOR_STORE_PROVIDER=pgvector
EMBEDDING_DIM=128
ADMIN_API_KEY=civiciq-edison-admin-2026

# LLM Configuration (Google Gemini preferred; Groq / OpenAI as alternative)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash

# Optional Groq alternative
GROQ_API_KEY=your_groq_api_key_here
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=llama-3.3-70b-versatile
```

### 3. Native pgvector Operations
- **Vector Column**: `embedding vector(128)`
- **HNSW Cosine Index**:
  ```sql
  CREATE INDEX idx_chunks_hnsw ON municipal_knowledge_chunks USING hnsw (embedding vector_cosine_ops);
  ```
- **Cosine Similarity Search**:
  ```sql
  SELECT id, department_id, url, title, category, content,
         (1.0 - (embedding <=> %s::vector)) AS similarity
  FROM municipal_knowledge_chunks
  WHERE (%s IS NULL OR department_id = %s)
    AND (1.0 - (embedding <=> %s::vector)) >= %s
  ORDER BY (embedding <=> %s::vector) ASC
  LIMIT %s;
  ```
- **Automatic Fallback**: If PostgreSQL is offline, CivicIQ automatically operates on its local SQLite vector store (`backend/data/vector_store.db`). When PostgreSQL starts, it routes queries to pgvector without restarting the application.

---

## 📂 Modular Department File Organization

Municipal staff can configure or expand departments modularly by dropping assets into `/departments/<dept_id>`:

```plaintext
departments/
  ├── engineering/
  │     ├── config.json                 # Counter desk, hours, contacts (100 Municipal Blvd)
  │     ├── metadata.json               # Department status (active MVP)
  │     ├── flows.json                  # Deterministic decision trees & prerequisites
  │     ├── knowledge_links.json        # Authoritative links to Edison official documents
  │     ├── document_inventory.json     # Extracted document inventory & OCR status
  │     ├── services/
  │     │     └── services.json         # Structured service catalog
  │     └── forms/                      # Authentic static Edison Township PDFs
  │           ├── Zoning_Permit_Application_Edison.pdf
  │           ├── ZONING_PERMIT_REQUIREMENT_SHEET.pdf
  │           ├── RoadOpenApp.pdf
  │           ├── Sewer_Connection_Charge_Applications.pdf
  │           ├── Zoning_Permit_Fees_2022.pdf
  │           ├── Pool_Setbacks.pdf
  │           ├── Deck_Coverage.pdf
  │           ├── Schedule_A_Yard_Requirements.pdf
  │           └── Minor_Subdivision_Packet_2024.pdf
  ├── animal_shelter/
  │     └── config.json                 # Edison Animal Shelter (125 Municipal Blvd, Referral)
  └── healthcare/
        ├── config.json                 # Edison Health & Human Services (Referral)
        └── flows.json
```

---

## 📥 Ingestion Pipeline & Document Inventory

The ingestion pipeline (`backend/scripts/ingest.py`) discovers, inspects, extracts, classifies, and indexes official Edison Township documents:

```bash
python backend/scripts/ingest.py
```

Features:
- **PDF Text Extraction**: Uses `pypdf` to extract high-fidelity text from official Edison PDFs.
- **Scanned Image PDF Handling**: Scanned documents without text layers (e.g. `RoadOpenApp.pdf`) are safely categorized with `extraction_status: "scanned_pdf_needs_ocr"` and flagged `needs_manual_verification: true`. Their official links, titles, and summaries are preserved.
- **Classification**: Categorizes every document as `Application form`, `Permit form`, `Procedure/guideline`, `Fee schedule`, `Zoning map`, or `Application packet`.
- **Document Inventory**: Generates `departments/engineering/document_inventory.json` with document titles, department, document types, official URLs, local paths, extraction statuses, file sizes, and page counts.
- **Protected Re-ingestion**: Admin endpoint `/api/ingest` requires header `X-Admin-Key: <ADMIN_API_KEY>`.

---

## 🚀 Quick-Start Instructions

### 1. Prerequisites
- **Python**: 3.10+ (tested on Python 3.14)
- **Node.js**: v18+ or v20+
- **npm**: 9+

---

### 2. Backend Setup & Ingestion

From the project root (`d:\CivicIQ`):

```bash
# 1. Install backend dependencies
pip install fastapi uvicorn pydantic requests beautifulsoup4 scikit-learn numpy pypdf psycopg2-binary pgvector

# 2. Run the Official Edison Document Ingestion Pipeline
python backend/scripts/ingest.py

# 3. Launch the FastAPI backend server (Runs on port 8000)
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

### 3. Frontend Setup & Launch

In a second terminal:

```bash
cd frontend

# 1. Install frontend dependencies
npm install

# 2. Run the Next.js development server (Runs on port 3000)
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

### 4. Running Automated Tests

Run the full test suite covering the 8 realistic resident questions, API endpoints, flowchart logic, and pgvector:

```bash
python -m unittest discover -s backend/tests -p "test_*.py"
```

All 24 unit and integration tests pass cleanly.

---

## 🧪 8 Verified Resident Inquiry Scenarios

| # | Resident Question | Expected Behavior | Verification Status |
|---|---|---|---|
| **1** | *"I want to construct a new house on my property. Which permit do I need?"* | Launches `residential_zoning_permit_flow`, validates survey & setbacks, issues `Zoning_Permit_Application_Edison.pdf` | ✅ Passed |
| **2** | *"I need to remove a tree on my property. What is the procedure?"* | Launches `tree_removal_flow` based on Chapter 37 DBH size thresholds | ✅ Passed |
| **3** | *"How do I apply for a sewer connection in Edison?"* | Launches `sewer_connection_flow`, calculates fixture units, issues `Sewer_Connection_Charge_Applications.pdf` | ✅ Passed |
| **4** | *"I need a street excavation permit to connect underground utilities."* | Launches `street_opening_flow`, verifies NJ 811 ticket & $5,000 restoration bond | ✅ Passed |
| **5** | *"What documents do I need to attach for a residential zoning permit?"* | Grounded RAG retrieves Edison Zoning Requirement Sheet (2 survey copies, scale 1"=20', setback plot plan) | ✅ Passed |
| **6** | *"Can I download the official Edison zoning permit application form?"* | Delivers in-chat official PDF download card for `Zoning_Permit_Application_Edison.pdf` with desk routing | ✅ Passed |
| **7** | *"Where and when can I submit my engineering permit application in Edison?"* | Directs to Division of Zoning, Municipal Complex, 100 Municipal Blvd, Mon–Fri 8:00 AM – 4:30 PM | ✅ Passed |
| **8** | *"I want to adopt a cat. What is the procedure?"* | Friendly referral to Edison Municipal Animal Shelter, 125 Municipal Blvd, (732) 248-7258 | ✅ Passed |

---

## 🛠️ API Reference Table

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | System status, loaded departments, and active vector store |
| `/api/departments` | GET | List registered departments with MVP status badges |
| `/api/departments/{dept_id}` | GET | Department metadata, flows, forms, and knowledge links |
| `/api/document-inventory` | GET | Comprehensive Edison document inventory with OCR status |
| `/api/document-center` | GET | Full document catalog with keyword and category filtering |
| `/api/forms/{dept_id}/{file}` | GET | Streams static official PDF form (`application/pdf`) |
| `/api/chat` | POST | Conversational router: flow execution, form matching, and grounded RAG |
| `/api/flow/start` | POST | Explicitly starts a deterministic procedure flow |
| `/api/flow/step` | POST | Advances a flowchart step by selecting an option |
| `/api/flow/reset` | POST | Resets session procedure state |
| `/api/ingest` | POST | Protected admin re-ingestion endpoint (Requires `X-Admin-Key` header) |
| `/api/vector/stats` | GET | Vector store statistics and chunk breakdown |
