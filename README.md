# CivicIQ — Your Edison Township Buddy

**CivicIQ** is an AI-powered municipal application assistant for residents of the **Township of Edison, New Jersey** (Department of Engineering).

It helps residents navigate municipal procedures, permits, and engineering regulations using official data from the **Edison Township Document Center** ([edisonnj.org/document_center/index.php](https://www.edisonnj.org/document_center/index.php)).

---

## 🏛️ Official Identity & Branding

- **Application Name**: `CivicIQ`
- **Official Tagline**: `Your Edison Township Buddy`
- **Welcome Prompt**: `How can **"CivicIQ"** help you today?` (visually bolded)
- **Official Portal**: [https://www.edisonnj.org/document_center/index.php](https://www.edisonnj.org/document_center/index.php)

---

## 🚀 Key Features

### 1. Free-First LLM Architecture (Zero Paid API Lock-In)
- **Primary Provider**: **Google Gemini** (`gemini-1.5-flash` via official SDK + REST fallback).
- **First Backup**: **Groq API** (`llama-3.3-70b-versatile` with low-latency inference).
- **Second Backup**: **OpenRouter** with strict free-model enforcement (`:free` suffix guard). Blocks paid models to prevent surprise billing.
- **Offline / Local Fallback**: **Deterministic Grounded Retrieval Synthesis** produces verified responses from municipal excerpts even when all external LLM APIs are unreachable.

### 2. Grounded Question Answering (RAG)
- Answers queries using official Edison Township Engineering documentation.
- Rigorous anti-hallucination guardrail: inquiries outside Engineering return the official municipal redirection:
  > *"Sorry, this information is out of our context. Please visit https://www.edisonnj.org/document_center/index.php for more information."*
- Strict privacy: No physical street addresses, phone numbers, or staff contact details are exposed.

### 3. Intelligent Form Identification
- Distinguishes **Application Forms** (interactive permit applications) from **Reference Documents** (Schedule A yard requirements, pool setbacks, deck coverage), **Fee Schedules**, and **Decision Flowcharts**.
- Recommends the verified form and offers: *"Would you like me to help you fill out this application?"*

### 4. Conversational Form-Filling State Machine
- Interactive step-by-step guidance asking one question at a time.
- Validates inputs (emails, 10-digit phone numbers, positive numbers, choice options).
- In-flight correction support: residents can type `edit [field_name]` or click edit to update previous answers.
- Review summary presented before draft generation.

### 5. Official PDF Form Draft Generation
- Automatically generates standardized municipal draft PDFs.
- **Unsubmitted Draft Watermark Banner**: Every page is branded with:
  `*** OFFICIAL REVIEW COPY — UNSUBMITTED MUNICIPAL DRAFT — PHYSICAL SIGNATURE REQUIRED ***`
- **Blank Physical Ink Signature**: In accordance with municipal guidelines, signature lines are never AI-simulated and are explicitly stamped:
  `[SIGNATURE REQUIRED - SIGN MANUALLY IN INK AFTER PRINTING]`
- **Session Isolation**: Each resident's draft is created in a secure, isolated directory (`backend/data/generated_drafts/{session_id}/`) and served through session-authenticated download endpoints.

### 6. Submission Guidance & Checklist
- Provides required attachment checklists (e.g., sealed property surveys, plot plans, NJ 811 Call Before You Dig tickets, surety bonds, liability insurance certificates).
- Directs residents to the official municipal portal for final submission.

---

## 🐘 Vector Storage & pgvector Integration

CivicIQ natively supports **pgvector (PostgreSQL 16)** with automatic fallback to a local SQLite vector store when Docker/PostgreSQL is offline.

### Quick Start with Docker:
```bash
docker compose up -d
```
This initializes PostgreSQL with the `pgvector` extension and creates HNSW cosine index tables via `init_pgvector.sql`.

---

## 🛠️ Configuration (`.env`)

Copy `.env.example` to `.env`:

```env
# Official Identity
MUNICIPALITY_NAME=Township of Edison, New Jersey

# Vector Store
DATABASE_URL=postgresql://postgres:postgrespassword@localhost:5432/civiciq
VECTOR_STORE_PROVIDER=pgvector
SIMILARITY_THRESHOLD=0.075
EMBEDDING_DIM=128

# Free-First LLM Architecture
LLM_PRIMARY_PROVIDER=gemini
LLM_FALLBACK_PROVIDERS=groq,openrouter
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES=2

# 1. Primary: Google Gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash

# 2. First Backup: Groq
GROQ_API_KEY=your_groq_api_key_here
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=llama-3.3-70b-versatile

# 3. Second Backup: OpenRouter (Free Tier Only)
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=meta-llama/llama-3.2-3b-instruct:free
OPENROUTER_ALLOW_FREE_MODELS_ONLY=true

# Admin Ingestion Key
ADMIN_API_KEY=edison_admin_secret_key_2026
```

---

## 🚀 Running the Application

### 1. Backend (FastAPI)
```bash
# From workspace root
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
Swagger API documentation: [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Frontend (Next.js)
```bash
cd frontend
npm install
npm run dev
```
CivicIQ web portal: [http://localhost:3000](http://localhost:3000)

---

## 🧪 Comprehensive Automated Test Suite

CivicIQ includes an automated test suite covering all 20 required system specifications without requiring paid API keys:

```bash
# Run the 20-point comprehensive system test suite
python -m unittest backend.tests.test_civiciq_full_suite

# Run all 45 automated unit and scenario tests
python -m unittest discover -s backend/tests -p "test_*.py"
```

### Verified Test Matrix (20 Specifications):
| # | Test Requirement | Implementation | Status |
|---|---|---|---|
| 1 | Gemini Primary Provider | Configured & selected by default in `LLMProviderManager` | ✅ PASS |
| 2 | Groq Fallback | Automatically invoked when Gemini encounters quota/errors | ✅ PASS |
| 3 | OpenRouter Fallback | Seamlessly invoked when Gemini and Groq fail | ✅ PASS |
| 4 | Deterministic Grounded Synthesis | Fallback answer generated locally when all free LLMs fail | ✅ PASS |
| 5 | OpenRouter Free Guard | Paid models without `:free` suffix rejected with `ValueError` | ✅ PASS |
| 6 | Form Identification: Application | Road opening identified as application with conversational fill | ✅ PASS |
| 7 | Form Identification: Reference Doc | Schedule A yard requirements marked as reference document | ✅ PASS |
| 8 | Form Identification: Fee Schedule | Zoning fee schedule marked as informational reference | ✅ PASS |
| 9 | Form Identification: Flowchart | Permit Flow Charts marked as reference document | ✅ PASS |
| 10 | Conversational Form: Start | Session initialized at Step 1 with first question prompt | ✅ PASS |
| 11 | Conversational Form: Sequence | Sequential progression: name $\to$ phone $\to$ email $\to$ address | ✅ PASS |
| 12 | Input Validation: Email | Rejects invalid email (`not-an-email`) with validation notice | ✅ PASS |
| 13 | Input Validation: Phone | Rejects malformed phone (`123-abc`) with 10-digit telephone notice | ✅ PASS |
| 14 | Edit Previous Answer | `edit [field]` updates answer and allows resuming | ✅ PASS |
| 15 | Review Summary | Comprehensive summary presented before draft generation | ✅ PASS |
| 16 | PDF Generation: Answers | Generates valid PDF populated with citizen answers | ✅ PASS |
| 17 | Blank Ink Signature | Signature line explicitly blank with manual ink signing notice | ✅ PASS |
| 18 | Watermark Banner | Unsubmitted municipal draft red watermark banner applied | ✅ PASS |
| 19 | Secure PDF Serving | Session-authenticated download URL (`/api/form-session/download/...`) | ✅ PASS |
| 20 | Session Isolation | Answers from Resident A never leak into Resident B's session | ✅ PASS |

---

## 📂 Department Assets & Document Registry

All documents are officially retrieved from **Edison Township Document Center**:
- `RoadOpenApp.pdf`: Street Opening & Pavement Excavation Application
- `Zoning_Permit_Application_Edison.pdf`: Residential Construction & Zoning Permit Application
- `Sewer_Connection_Charge_Applications.pdf`: Sewer Utility Connection & Tap Application
- `Permit_Flow_Charts.pdf`: Official Permit Flow Charts & Tree Removal Guidance
- `Schedule_A_Yard_Requirements.pdf`: Bulk Yard Dimensions & Setback Table
- `Zoning_Permit_Fees_2022.pdf`: Official Fee Schedule (Ordinance O.2158-2022)
- `Pool_Setbacks.pdf` & `Deck_Coverage.pdf`: Residential Construction Reference Sheets
- `Minor_Subdivision_Packet_2024.pdf`: Minor Subdivision Checklist & Application

---

## 🔒 Security & Compliance

- **No AI Signatures**: Municipal regulations strictly prohibit synthetic signatures. CivicIQ drafts must be printed and signed by hand in ink.
- **Privacy First**: Physical addresses and staff phone numbers are omitted from chat responses; citizens are directed to the official website [edisonnj.org/document_center/index.php](https://www.edisonnj.org/document_center/index.php).
- **Session-Restricted Storage**: Generated drafts are isolated per session to prevent unauthorized access.
