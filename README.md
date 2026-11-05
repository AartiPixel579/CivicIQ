# CivicIQ — Municipal Application Assistant (Edison Township)

**CivicIQ** is an AI-powered municipal application assistant developed for residents of the **Township of Edison, New Jersey**. It assists residents with municipal Engineering regulations, procedural questions, and official permit applications using verified data sourced from the [Edison Township Document Center](https://www.edisonnj.org/document_center/index.php).

---

## 🏛️ Project Overview

Navigating municipal permits and township codes can be complicated for residents. CivicIQ provides a conversational interface that:
- Answers resident inquiries about municipal Engineering services and requirements.
- Distinguishes between procedural guidance, fee inquiries, document checklists, and application requests.
- Guides residents through verified workflows (such as Tree Removal and Soil Movement).
- Provides direct access to official municipal forms and reference documents without exposing internal municipal flowcharts.
- Politely redirects out-of-context requests (e.g., animal control, taxes, vital statistics) to the official township portal.

---

## ⚡ Currently Implemented Features

1. **Grounded Question Answering (RAG)**
   - Answers questions using text extracted from official Edison Township Engineering documents.
   - Provides direct clickable links and citations to official application forms.
   - Includes an offline grounded fallback mode that produces verified answers from excerpts even when external LLM APIs are unavailable.

2. **Service Intent Detection & Context-Aware Conversations**
   - Differentiates between procedural workflows, fee inquiries, document checklists, and submission questions.
   - Inquiries such as *"Tree removal cost"* or *"Where do I apply?"* answer the specific question directly rather than forcing the user into a multi-step workflow.
   - Maintains conversation history across multi-turn exchanges (e.g., answering *"What documents do I need?"* in the context of a previous tree removal question).

3. **Ambiguity Resolution**
   - Automatically detects short or ambiguous messages (e.g., *"removal"*) and asks a single clarifying question with interactive options (*"What would you like to remove — a tree or soil?"*).

4. **Multi-Provider LLM Resiliency**
   - Configured with a multi-tier fallback architecture: **Google Gemini** (Primary Provider) $\to$ **Groq** (Fallback Provider) $\to$ **Local Grounded Retrieval Synthesis** (Offline Fallback).
   - If external APIs are unavailable or unconfigured, the system automatically synthesizes verified responses locally from indexed municipal excerpts without crashing.

5. **Document Center & Form Inventory**
   - Catalogs official Township of Edison Engineering documents.
   - Supports search and in-app viewing of official municipal PDF files.
   - Distinguishes interactive application forms from informational reference sheets (e.g., setback requirements).

6. **Out-of-Scope & Unconfigured Service Safeguards**
   - Non-engineering inquiries receive a standard municipal redirection to the Edison Document Center portal.
   - Engineering topics without active workflows are explicitly flagged as unconfigured rather than generating inaccurate guidance.

---

## 📋 Supported Services

CivicIQ strictly identifies what is currently active versus what is unconfigured:

### 1. Fully Supported & Verified Services

- **Tree Removal & Preservation**:
  - **Decision Evaluation**: Evaluates whether a removal is an emergency (dead, dying, or imminent hazard) or standard residential removal.
  - **Emergency Guidance**: Informs residents that emergency removals may proceed immediately concurrent with submitting an application, provided photographic evidence or arborist certification is obtained.
  - **Fee Schedule Accuracy**: Advises on the standard \$25 residential filing fee, the senior citizen fee waiver for residents aged 62 or older (with valid proof of age), and the \$200 fee for removals tied to Planning or Zoning Board approval.
  - **Document Requirements**: Explains requirements including property surveys/tax maps, written statements, and tree marking.
  - **Form Access**: Delivers the official Township of Edison Tree Permit Application (`3.23.21 tree permit application.pdf`).

- **Soil Movement, Importation & Exportation**:
  - **Volume Thresholds**: Evaluates projects under Township Chapter 31 based on the 10 cubic yard threshold.
  - **Importation Guidance**: Directs projects of 10 cubic yards or more to the Soil Importation Permit Application (`Forms_Soil_Importation_Appl.pdf`).
  - **Exportation Guidance**: Directs projects of 10 cubic yards or more to the Soil Exportation Permit Application (`Forms_Soil_Exportation_App.pdf`).
  - **Minor Volumes**: Explains that quantities under 10 cubic yards do not require a soil permit, and details standard plot plan review standards for small yard fill.

### 2. Unconfigured Services (Document Catalog Only)

The following services exist in the municipal document catalog, but their interactive workflows are **not yet active**. Queries for these services return an explicit notice that the service is unconfigured:
- **Street Opening & Road Excavation**: Returns notice; does not solicit utility tickets or bonds.
- **Residential Zoning & Construction**: Returns notice; informational reference sheets (deck coverage, pool setbacks) remain viewable via the Document Center.
- **Site Improvement & Grading**: Returns notice.
- **Sanitary Sewer Connections**: Returns notice.

---

## 🛠️ Technology Stack

- **Backend**: Python 3.11, FastAPI, Uvicorn, Pydantic v2
- **Frontend**: Next.js 14 (App Router), React 18, Tailwind CSS, Lucide Icons
- **Vector Storage**: SQLite Vector Store (built-in zero-setup fallback) and PostgreSQL with `pgvector`
- **PDF & Document Processing**: `pypdf`, ReportLab, BeautifulSoup4
- **LLM Integrations**: Google Gemini API (Primary Provider), Groq API (Fallback Provider)

---

## 📁 Project Folder Structure

```
CivicIQ/
├── backend/
│   ├── app/
│   │   ├── config.py                 # Application configuration & environment settings
│   │   ├── main.py                   # FastAPI REST API endpoints & CORS setup
│   │   ├── models/                   # Pydantic data schemas & request/response models
│   │   ├── rag_engine.py             # Grounded retrieval-augmented generation engine
│   │   ├── flow_engine.py            # Conversational state machine & decision flows
│   │   ├── vector_store.py           # Unified vector store (pgvector + SQLite fallback)
│   │   ├── pgvector_store.py         # PostgreSQL pgvector database adapter
│   │   ├── edison_document_center.py # Catalog & metadata for official documents
│   │   ├── llm_client.py             # LLM orchestration and fallback synthesis
│   │   ├── llm_provider/             # Providers for Gemini and Groq
│   │   └── services/                 # Intent detection, form matching, and PDF utilities
│   ├── data/                         # Local SQLite vector database & runtime drafts
│   ├── scripts/                      # Document discovery and ingestion pipeline
│   ├── tests/                        # 98 automated unit, scenario, and routing tests
│   └── requirements.txt              # Python backend dependencies
├── departments/
│   └── engineering/
│       ├── document_inventory.json   # Verified catalog of municipal documents
│       ├── flows.json                # Procedural decision trees
│       ├── knowledge_links.json      # Official portal links and contacts
│       └── forms/                    # 14 official municipal PDFs
├── frontend/
│   ├── public/                       # Static public assets (official Edison logo)
│   ├── src/
│   │   ├── app/                      # Next.js 14 App Router pages & layout
│   │   └── components/               # Chat, Document Center, and UI components
│   ├── next.config.js                # API proxy rewrites & build configuration
│   └── package.json                  # Frontend dependencies & scripts
├── .env.example                      # Environment variables template with safe placeholders
├── DEPLOYMENT_GUIDE.md               # Step-by-step production deployment guide (Vercel + Render)
├── render.yaml                       # Render Web Service blueprint definition
└── README.md                         # Project documentation
```

---

## 📋 Prerequisites

- **Python**: 3.10 or 3.11
- **Node.js**: 18.x or 20.x, with `npm`
- **Optional API Keys**: A free API key from [Google AI Studio](https://aistudio.google.com/) (recommended primary) and/or [Groq Console](https://console.groq.com/) (fast fallback). *(The app operates using local grounded retrieval synthesis if no external API keys are configured).*
- **Optional Database**: A PostgreSQL database with the `pgvector` extension. If omitted, CivicIQ runs out-of-the-box using local SQLite.

---

## 🚀 Local Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/AartiPixel579/CivicIQ.git
cd CivicIQ
```

### 2. Environment Configuration
Copy `.env.example` to create your local `.env` file:
```bash
# On Linux / macOS
cp .env.example .env

# On Windows (PowerShell)
Copy-Item .env.example .env
```

Open `.env` in your local text editor and fill in your private API keys:
```env
# Municipality Metadata
MUNICIPALITY_NAME=Township of Edison, New Jersey

# Database & Vector Store
# Leave empty to use the built-in SQLite vector store automatically:
DATABASE_URL=
VECTOR_STORE_PROVIDER=pgvector

# Primary AI Provider: Google Gemini (Get free key at https://aistudio.google.com/)
LLM_PRIMARY_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-1.5-flash

# Fallback AI Provider: Groq (Get free key at https://console.groq.com/)
LLM_FALLBACK_PROVIDERS=groq
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile

# Security & CORS
ADMIN_API_KEY=replace_with_a_strong_random_secret
ENVIRONMENT=development
ALLOWED_ORIGINS=http://localhost:3000
```

> [!IMPORTANT]
> **API Key Privacy & Security**:
> - Real API keys, database passwords, and secrets belong **strictly in your private local `.env` file**.
> - The `.env` file is excluded from git tracking by `.gitignore` so your private credentials are never pushed to GitHub.
> - Never commit or expose actual secrets, tokens, or passwords to version control.

---

## 🖥️ Starting the Application

### 1. Start the Backend (FastAPI)
```bash
# Create and activate a Python virtual environment (recommended)
python -m venv venv

# On Linux / macOS:
source venv/bin/activate
# On Windows:
.\venv\Scripts\activate

# Install backend dependencies
pip install -r backend/requirements.txt

# Start the FastAPI server
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
- API Base: `http://localhost:8000`
- Interactive API Documentation: `http://localhost:8000/docs`
- Health Endpoint: `http://localhost:8000/api/health`

### 2. Start the Frontend (Next.js)
In a separate terminal:
```bash
cd frontend
npm install
npm run dev
```
- CivicIQ Web Application: `http://localhost:3000`

---

## 🧪 Automated Tests

CivicIQ includes an automated test suite verifying routing, service isolation, tree removal rules, multi-provider LLM fallback, and out-of-context protections.

Run all tests from the repository root:
```bash
python -m unittest discover -s backend/tests -p "test_*.py"
```

### Test Coverage Summary:
- **Test Count**: 98 tests
- **Result**: `OK (100% passing)`
- **Key Verified Scenarios**:
  - Tree Removal conversational emergency flow and form packet delivery.
  - Senior fee waiver qualification at age 62 or older (per official form).
  - Ambiguity resolution for short queries (e.g., *"removal"* clarifying tree vs. soil).
  - Context retention across multi-turn exchanges.
  - Unconfigured service isolation for Street Opening, Zoning, Site Improvement, and Sewer.
  - Out-of-context guardrails returning official municipal redirection.
  - Multi-LLM provider failover (Gemini $\to$ Groq $\to$ Grounded Retrieval Synthesis).
  - Vector store indexing and query operations across pgvector and SQLite.

---

## ⚠️ Current Limitations

- **Engineering Department Scope**: The assistant is currently focused strictly on Edison Township Department of Engineering services.
- **Active Workflow Scope**: Multi-turn procedural decision workflows are currently implemented for Tree Removal and Soil Movement. Other engineering services provide document access and catalog summaries, but interactive decision flows remain unconfigured.
- **In-Memory Session Storage**: Multi-turn chat history and interactive form session states are held in server process memory and do not persist across container restarts or cold-boots. Residents who disconnect or experience a service restart start a fresh session.
- **Scanned Document OCR**: Scanned historical PDFs in the Document Center are cataloged, but full text search for image-only scans requires manual transcription or future OCR integration.
- **Advisory Guidance**: CivicIQ provides procedural guidance and form preparation assistance. It does not replace formal regulatory reviews, official permits, or inspections by the Township of Edison.

---

## 🔮 Future Improvements (Planned)

The following features are planned for future versions of CivicIQ:
- **Interactive Street Opening Workflow**: Complete procedural flow for road opening permits, right-of-way excavations, and utility coordination.
- **Residential Zoning Decision Trees**: Step-by-step guidance for residential accessory structures (sheds, decks, fences, swimming pools) and building additions.
- **Automated OCR Ingestion Pipeline**: Ingestion pipeline for scanned municipal documents and fee tables using OCR.
- **Multi-Department Expansion**: Expanding the platform architecture to cover additional municipal departments (Zoning, Department of Public Works, Health, and Municipal Clerk).
- **Resident Application Dashboard**: Optional authenticated portal for saving draft progress and tracking permit application statuses.
