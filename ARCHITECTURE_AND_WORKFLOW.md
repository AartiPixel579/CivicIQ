# CivicIQ - Edison Township Resident Services Assistant
## Comprehensive Architecture, Workflows & Data Flow Diagrams (DFD)

This document provides complete technical architectural specifications, end-to-end workflows, and Level 0 & Level 1 Data Flow Diagrams (DFD) for the **CivicIQ Resident Services Assistant** for the **Township of Edison, New Jersey**.

Official municipal source: `https://www.edisonnj.org/document_center/index.php`

---

## 1. High-Level System Architecture

The system operates across four distinct operational layers:
1. **Presentation Layer (Frontend)**: Next.js (App Router), React, Tailwind CSS, Lucide icons. Features dual interaction modes: conversational procedural chat with official PDF cards and a dynamic Document Center tab powered by the live inventory.
2. **API & Service Layer (Backend)**: FastAPI (Python), housing the Intent Disambiguation Router, Deterministic Flowchart State Machine, Grounded Link RAG Engine, LLM Client (OpenAI / Gemini / Retrieval-Only Fallback), and Department Registry Loader.
3. **Official Document Ingestion & Inventory Pipeline**: Ingests official documents from Edison Township Document Center (`edisonnj.org`), extracts text using `pypdf`, classifies scanned image PDFs (`scanned_pdf_needs_ocr`), and generates `document_inventory.json`.
4. **Vector & Relational Storage Layer**: PostgreSQL with `pgvector` extension storing 128-dimensional dense vector embeddings with HNSW cosine distance indexing (`<=>`), alongside local resilient fallback caching (`vector_store.db`).
5. **File & Asset Layer**: Modular departmental file organization (`/departments/<dept>/`) holding metadata (`config.json`), verified decision trees (`flows.json`), knowledge links (`knowledge_links.json`), inventory (`document_inventory.json`), and official downloaded PDF documents (`forms/`).

```mermaid
flowchart TB
    subgraph Client["Presentation Layer (Next.js 14 / React / Tailwind)"]
        UI["Citizen Web Portal UI"]
        ChatUI["Chat Interface & Assistant"]
        DocCenterUI["Document Center (edisonnj.org Hub)"]
        PdfModal["In-App PDF Viewer Modal"]
        PdfCard["Official PDF Document Card Component"]
    end

    subgraph Gateway["API Gateway & Router (FastAPI)"]
        Router["Intent Router (/api/chat)"]
        DocAPI["Document Center API (/api/document-center)"]
        InvAPI["Document Inventory API (/api/document-inventory)"]
        FlowAPI["Flow State Machine API (/api/flow/*)"]
        FormAPI["PDF Static Streaming (/api/forms/*)"]
        IngestAPI["Admin Re-index API (/api/ingest)"]
    end

    subgraph Engines["Procedural & Retrieval Engines"]
        FlowEngine["Deterministic Flow Engine\n(Edison Workflows: Zoning, Road, Tree, Sewer)"]
        RagEngine["Grounded RAG Engine\n(Strict Anti-Hallucination Guardrails)"]
        LLM["LLM Client\n(OpenAI / Gemini / Retrieval Fallback)"]
        IngestEngine["Official Document Ingestion Pipeline\n(pypdf & OCR Classification)"]
        DeptLoader["Department Loader\n(Modular /departments/ discovery)"]
    end

    subgraph DataLayer["Data & Document Storage Layer"]
        PG["PostgreSQL 16 + pgvector\n(Table: municipal_knowledge_chunks)\nHNSW Cosine Index (<=>)"]
        SQLiteCache["Local SQLite Vector Fallback\n(vector_store.db)"]
        FileStore["Static Official PDF Repository\n(departments/engineering/forms/*.pdf)"]
        JSONStore["Official Department Assets\n(config.json, flows.json, document_inventory.json)"]
    end

    UI --> ChatUI & DocCenterUI
    ChatUI --> Router
    DocCenterUI --> DocAPI & InvAPI
    ChatUI --> FlowAPI
    PdfCard --> FormAPI
    Router --> FlowEngine & RagEngine
    RagEngine --> LLM
    RagEngine --> PG & SQLiteCache
    FlowEngine --> JSONStore & FileStore
    IngestEngine --> FileStore & JSONStore & PG & SQLiteCache
    IngestAPI --> IngestEngine
```

---

## 2. End-to-End Procedural Sequence Flow

The following sequence diagram details the full lifecycle of a resident inquiry—from procedural intent detection through mandatory prerequisite validation and authentic Edison PDF form issuance:

```mermaid
sequenceDiagram
    autonumber
    actor Resident as Edison Resident
    participant UI as Next.js Chat Portal
    participant API as FastAPI Router
    participant Flow as Deterministic Flow Engine
    participant RAG as Grounded RAG Engine
    participant LLM as LLM Client
    participant Store as Vector Store (pgvector / SQLite)
    participant Disk as Static PDF Storage (departments/engineering/forms)

    Resident->>UI: "I want to construct a new house on my property. Which permit do I need?"
    UI->>API: POST /api/chat {message, session_id, dept: "engineering"}
    
    API->>RAG: detect_flow_intent(message)
    Note over RAG: Identifies construction intent -> Matches residential_zoning_permit_flow
    RAG-->>API: ("engineering", "residential_zoning_permit_flow")

    API->>Flow: start_flow(session_id, "engineering", "residential_zoning_permit_flow")
    Flow-->>API: Step 1 (Scope Selection: New Single-Family Dwelling, Addition, Pool, Shed)
    API-->>UI: ChatResponse {mode: "flow", step: "step_scope_selection", options: [...]}
    UI-->>Resident: Renders Step 1 Decision Options

    Resident->>UI: Selects: "New Single-Family Dwelling Construction ($200.00 review fee)"
    UI->>API: POST /api/chat {session_id, selected_option_id: "scope_new_home"}
    API->>Flow: advance_step(session_id, "scope_new_home")
    Flow-->>API: Step 2 Prerequisite Check: Property Survey Verification
    API-->>UI: ChatResponse {mode: "flow", step: "step_survey_verification", is_mandatory: true}
    UI-->>Resident: Renders Mandatory Prerequisite: Signed & Sealed Survey Required

    Resident->>UI: Confirms: "Yes, I have an active certified property survey"
    UI->>API: POST /api/chat {session_id, selected_option_id: "survey_ready"}
    API->>Flow: advance_step(session_id, "survey_ready")
    Flow-->>API: Step 3 Prerequisite Check: Schedule A Setback Compliance
    API-->>UI: ChatResponse {mode: "flow", step: "step_setback_compliance"}

    Resident->>UI: Confirms: "Yes, proposed dwelling conforms to Schedule A setbacks"
    UI->>API: POST /api/chat {session_id, selected_option_id: "setbacks_conform"}
    API->>Flow: advance_step(session_id, "setbacks_conform")
    
    Note over Flow,Disk: Flow reaches Step: issue_edison_zoning_packet
    Flow->>Disk: Resolves static form: Zoning_Permit_Application_Edison.pdf
    Flow-->>API: FormIssuanceDetails {form_code, form_title, pdf_download_url, submission_routing, attachments}
    API-->>UI: ChatResponse {mode: "flow", form_packet: FormIssuanceDetails, completed: true}
    
    UI-->>Resident: Renders Rich Official PDF Download Card with Preview & Desk Routing
    Resident->>UI: Clicks "Preview Document" or "Download Official PDF"
    UI->>API: GET /api/forms/engineering/Zoning_Permit_Application_Edison.pdf
    API->>Disk: Stream binary PDF bytes
    Disk-->>API: PDF Stream
    API-->>UI: HTTP 200 FileResponse (application/pdf)
    UI-->>Resident: Displays PDF in full-screen authentic viewer modal
```

---

## 3. Data Flow Diagram: Level 0 (Context Diagram)

The Level 0 Context Diagram establishes the system boundary of the **CivicIQ Resident Services Assistant** and details all inbound and outbound data flows with external entities:

```mermaid
graph TD
    Citizen["Citizen / Municipal Resident"]
    Admin["Municipal Department Administrator"]
    EdisonWeb["Official Edison Portal (edisonnj.org)"]

    System[["0.0\nCivicIQ Resident Services Assistant\n(Township of Edison, NJ)"]]

    Citizen -->|"1. Procedural Inquiries & Questions"| System
    Citizen -->|"2. Workflow Step Selections"| System
    System -->|"3. Grounded Municipal Excerpts & Citations"| Citizen
    System -->|"4. Interactive Flowchart Options"| Citizen
    System -->|"5. Official Static PDF Forms & Desk Routing"| Citizen
    System -->|"6. Unsupported Department Referrals (e.g. Animal Shelter)"| Citizen

    Admin -->|"7. Admin Trigger Re-index (X-Admin-Key)"| System
    System -->|"8. Ingestion & Vector Indexing Diagnostics"| Admin

    EdisonWeb -->|"9. Official PDFs, Guidelines & Fee Schedules"| System
    System -->|"10. Document Inventory & Text Embeddings"| System
```

---

## 4. Data Flow Diagram: Level 1 (Subsystem Decomposition)

The Level 1 DFD decomposes the system into its core functional processes, data stores, and interactions:

```mermaid
graph TD
    Citizen["Citizen / Resident"]
    Admin["Department Administrator"]
    EdisonWeb["Edison Document Center (edisonnj.org)"]

    P1["1.0\nConversational Intake & Intent Disambiguation"]
    P2["2.0\nDeterministic Flowchart State Machine"]
    P3["3.0\nGrounded Link RAG & LLM Synthesis"]
    P4["4.0\nOfficial Document Ingestion & OCR Classifier"]
    P5["5.0\nOfficial PDF & Document Delivery Engine"]
    P6["6.0\nDepartment Referral & Routing Handler"]

    D1[("D1: Department Config & Workflows\n(flows.json, config.json)")]
    D2[("D2: Vector Knowledge Store\n(PostgreSQL pgvector / SQLite)")]
    D3[("D3: Official PDF Storage\n(/departments/engineering/forms/)")]
    D4[("D4: Session State Store\n(FlowSession memory cache)")]
    D5[("D5: Document Center Inventory\n(document_inventory.json)")]

    Citizen -->|"User Message / Inquiries"| P1
    P1 -->|"Check Unsupported Dept (Cat adoption, etc.)"| P6
    P6 -->|"Department Referral + Official Contacts"| Citizen

    P1 -->|"Procedural Permit Intent"| P2
    P1 -->|"Informational Knowledge Query"| P3
    P1 -->|"Step Option Selection"| P2

    P2 <-->|"Read Step Logic & Prerequisites"| D1
    P2 <-->|"Read / Write Step State"| D4
    P2 -->|"Form Issuance Request"| P5
    P2 -->|"Interactive Step Prompt"| Citizen

    P3 -->|"Query Vector Search (<=>)"| D2
    D2 -->|"Matching Chunks & Relevance Score"| P3
    P3 -->|"Grounded Answer with Link Citations"| Citizen

    EdisonWeb -->|"Scrape / Download Official Documents"| P4
    P4 -->|"Store Official PDFs"| D3
    P4 -->|"Extract Text & Chunk Chunks"| D2
    P4 -->|"Write Metadata Inventory"| D5

    Admin -->|"Trigger Ingestion (X-Admin-Key)"| P4
    P4 -->|"Ingestion Summary & OCR Status"| Admin

    P5 <-->|"Read Authentic Static PDF"| D3
    P5 -->|"Stream Official PDF & Download Link"| Citizen
    D5 -->|"Serve Document Center Catalog"| Citizen
```

---

## 5. Scope: Edison Township Department of Engineering

| Department | Status | Municipal Office | Contacts | Key Forms / Services |
|---|---|---|---|---|
| **Department of Engineering** | **Active Focus** | Municipal Complex, 100 Municipal Blvd | (732) 248-7288 / `engineering@edisonnj.gov` | Road Openings, Street Excavations, Utility Trenching, Tree Clearances, Sewer Connections, Municipal Site Plans |
