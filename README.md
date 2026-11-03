# Pixelvyne Smart Assistant (CivicIQ)

A citizen-facing procedural web assistant and grounded knowledge portal engineered for municipal and enterprise service portals.

Built with **Next.js (App Router)**, **React**, **Tailwind CSS**, **FastAPI**, and **pgvector (PostgreSQL)**, operating under strict municipal administrative standards:
1. **Link/URL Knowledge Base (Grounded RAG with pgvector)**: Answers general inquiries strictly by retrieving context from verified municipal documentation links indexed as vector embeddings in PostgreSQL using native cosine distance (`<=>`) with HNSW indexing. Zero hallucinations.
2. **Deterministic Flowcharts**: Interactive step-by-step decision trees with non-bypassable statutory prerequisite checks.
3. **Official PDF Form Delivery**: No AI-generated or fabricated form fields. Serves standardized, authentic government PDF documents with download links, in-app preview, fill-in instructions, and attachment checklists.
4. **Acknowledgment & Departmental Routing**: Routes citizens to exact counter desks, hours, fee cashier protocols, and submission channels (Engineering, Healthcare, and easily extensible to others).

---

## 🐘 pgvector Setup & Architecture

CivicIQ natively uses **pgvector** for local link RAG retrieval.

### 1. Launch pgvector via Docker Compose (1 Command)
```bash
docker compose up -d
```
This spins up PostgreSQL 16 with the `pgvector` extension pre-configured, mapping port `5432`, and runs [init_pgvector.sql](file:///d:/CivicIQ/init_pgvector.sql).

### 2. Configure Environment (`.env`)
```env
DATABASE_URL=postgresql://postgres:postgrespassword@localhost:5432/civiciq
VECTOR_STORE_PROVIDER=pgvector
EMBEDDING_DIM=128
```

### 3. Native pgvector Schema & Operations
- **Vector Column**: `embedding vector(128)`
- **HNSW Cosine Index**:
  ```sql
  CREATE INDEX idx_chunks_hnsw ON municipal_knowledge_chunks USING hnsw (embedding vector_cosine_ops);
  ```
- **Cosine Distance Search**:
  ```sql
  SELECT id, department_id, url, title, category, content,
         (1.0 - (embedding <=> %s::vector)) AS similarity
  FROM municipal_knowledge_chunks
  WHERE (%s IS NULL OR department_id = %s)
    AND (1.0 - (embedding <=> %s::vector)) >= %s
  ORDER BY (embedding <=> %s::vector) ASC
  LIMIT %s;
  ```
- **Local Fallback**: If PostgreSQL has not yet been started, CivicIQ seamlessly falls back to local SQLite vector caching so offline development and testing never crash. Once PostgreSQL is launched, it automatically routes all queries through pgvector.

---

## 🏛️ Modular Department File Architecture

New municipal departments can be added by non-technical staff simply by dropping a new folder into `/departments`:

```plaintext
/departments
  ├── engineering/
  │     ├── config.json          # Department metadata (name, counter location, hours, contact)
  │     ├── knowledge_links.json # URLs/documentation links to scrape and index
  │     ├── flows.json           # Decision trees / step-by-step logic
  │     └── forms/               # Official static PDF files (e.g., ENG-204, ENG-102)
  │           ├── ENG-204_Residential_Permit_Application.pdf
  │           └── ENG-102_Excavation_Right_of_Way_Permit.pdf
  └── healthcare/
        ├── config.json
        ├── knowledge_links.json
        ├── flows.json
        └── forms/
              ├── HLT-101_Food_Establishment_License.pdf
              └── HLT-202_Mobile_Food_Sanitation_Clearance.pdf
```

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
# 1. Install Python backend dependencies
pip install fastapi uvicorn pydantic requests beautifulsoup4 scikit-learn numpy reportlab

# 2. (Optional) Generate authentic standardized municipal PDF forms
python backend/scripts/generate_official_forms.py

# 3. Run the Link Scraper & Vector Indexer
python backend/scripts/ingest.py --clear

# 4. Launch the FastAPI backend server (Runs on port 8000)
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

### 3. Frontend Setup & Launch

Open a second terminal:

```bash
cd frontend

# 1. Install frontend dependencies (if not already installed)
npm install

# 2. Run the Next.js development server (Runs on port 3000)
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

### 4. Running Automated Tests

Run the complete test suite (Core Engine, End-to-End API, pgvector):
```bash
python -m unittest discover -s backend/tests -p "test_*.py"
```

---

## 🔍 Core Features & Verification

### 1. Grounded Link RAG & Citations
- **Strict Anti-Hallucination**: Queries without verified municipal citations (e.g. non-governmental topics) are refused with an official municipal referral.
- **Verbatim Link Citations**: Responses quote exact excerpts with clickable source links (e.g., `https://pixelvyne.gov/departments/engineering/setbacks-and-zoning`), match relevance percentage, and topic category chips.
- Try asking:
  - *"What are the setback distances for an R-1 residential zone?"*
  - *"What is the permit fee schedule for 2026?"*
  - *"What are the food holding temperatures and CFPM requirements?"*

### 2. Deterministic Flowcharts
- Executes decision tree logic defined in `flows.json` (Eligibility -> Required Permits -> Mandatory Prerequisites -> Form Delivery).
- Non-bypassable checkpoints: Citizens cannot proceed without verifying statutory prerequisites (e.g., property ownership, zoning classification, 811 Call-Before-You-Dig tickets).
- If disqualified (e.g., commercial property in residential flow), routes the citizen to the proper municipal board (e.g. Zoning Board of Adjustment) with alternative instructions.

### 3. In-Chat Official PDF Delivery Component
- Upon prerequisite validation, renders a rich municipal document card:
  - **Official Document Code & Title**: (e.g., `Form ENG-204: Municipal Residential Building & Excavation Permit Application`).
  - **Direct Download Button**: Directly serves the static official PDF file from `/departments/<dept>/forms/`.
  - **In-App PDF Preview**: Accessible full modal previewing the authentic PDF document with zoom and download.
  - **Interactive Checklist**: Citizen-interactive checklist of mandatory attachments (e.g., dimensioned site plans, recorded deed proof, contractor license & liability insurance).
  - **Target Submission Desk Routing**: Explicit counter location, physical address, intake hours, cutoff times, and direct email/phone dispatch.

---

## 🛠️ API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | System status, loaded departments, and vector count |
| `/api/departments` | GET | List all registered municipal departments |
| `/api/departments/{dept_id}` | GET | Department metadata, flows, forms, and knowledge links |
| `/api/flows/{dept_id}` | GET | Available deterministic procedures for a department |
| `/api/chat` | POST | Conversational router (Flow step execution & Grounded RAG) |
| `/api/flow/start` | POST | Explicitly starts a deterministic procedure flow |
| `/api/flow/step` | POST | Advances a flowchart step by selecting an option |
| `/api/flow/reset` | POST | Resets procedure session state |
| `/api/forms/{dept_id}/{file}` | GET | Streams static official PDF form (`application/pdf`) |
| `/api/ingest` | POST | Re-indexes links from `knowledge_links.json` |
| `/api/vector/stats` | GET | Vector store statistics and chunk breakdown |
