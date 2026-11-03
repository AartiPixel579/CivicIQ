# CivicIQ - Pixelvyne Smart Assistant
## Comprehensive Architecture, Workflows & Data Flow Diagrams (DFD)

This document provides complete technical architectural specifications, end-to-end workflows, and Level 0 & Level 1 Data Flow Diagrams (DFD) for the **Pixelvyne Smart Assistant** (Citizen-Facing Procedural Web Portal).

---

## 1. High-Level System Architecture

The system operates across four distinct operational layers:
1. **Presentation Layer (Frontend)**: Next.js (App Router), React, Tailwind CSS, Lucide icons. Features dual interaction modes: conversational procedural chat and a full-text searchable Document Center tab.
2. **API & Engine Layer (Backend)**: FastAPI (Python), housing the Intent Disambiguation Router, Deterministic Flowchart State Machine, Grounded Link RAG Engine, and Department Registry Loader.
3. **Vector & Relational Storage Layer**: PostgreSQL with `pgvector` extension storing 128-dimensional dense vector embeddings with HNSW cosine distance indexing (`<=>`), alongside local fallback caching.
4. **File & Document Asset Layer**: Modular departmental file organization (`/departments/<dept>/`) holding metadata (`config.json`), decision trees (`flows.json`), knowledge links (`knowledge_links.json`), and official static PDF documents (`forms/`).

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
        FlowAPI["Flow State Machine API (/api/flow/*)"]
        FormAPI["PDF Static Streaming (/api/forms/*)"]
    end

    subgraph Engines["Procedural & Retrieval Engines"]
        FlowEngine["Deterministic Flow Engine\n(flows.json State Machine)"]
        RagEngine["Grounded RAG Engine\n(Strict Anti-Hallucination)"]
        Embedder["Dense Text Embedder\n(128-dim Normalized Vector)"]
        DeptLoader["Department Loader\n(Modular /departments/ discovery)"]
    end

    subgraph DataLayer["Data & Document Storage Layer"]
        PG["PostgreSQL 16 + pgvector\n(Table: municipal_knowledge_chunks)\nHNSW Cosine Index (<=>)"]
        SQLiteCache["Local SQLite Vector Fallback\n(vector_store.db)"]
        FileStore["Static PDF Repository\n(/departments/<dept>/forms/*.pdf)"]
        JSONStore["Department JSON Assets\n(config.json, flows.json, knowledge_links.json)"]
    end

    UI --> ChatUI & DocCenterUI
    ChatUI --> Router
    DocCenterUI --> DocAPI
    ChatUI --> FlowAPI
    PdfCard & DocCenterUI --> FormAPI
    FormAPI --> PdfModal

    Router --> FlowEngine
    Router --> RagEngine
    DocAPI --> JSONStore
    FlowAPI --> FlowEngine
    FormAPI --> FileStore

    FlowEngine --> JSONStore
    RagEngine --> Embedder
    Embedder --> PG
    PG -.->|Offline Fallback| SQLiteCache
    DeptLoader --> JSONStore & FileStore
```

---

## 2. End-to-End Workflow & Decision Logic

The conversational agent strictly enforces municipal rules:
- **Informational Queries**: Routed to the Grounded RAG Engine. If vector distance is within threshold, returns answer with exact source citations (e.g. `edisonnj.org`). If unverified, strictly refuses to prevent hallucinations.
- **Procedural Requests**: Initiates the deterministic step-by-step decision tree (`flows.json`). Mandatory prerequisites (e.g., zoning classification, deed ownership, 811 Call-Before-You-Dig locate ticket) cannot be skipped.
- **Form Stage**: Issues the official, pre-existing static government PDF (e.g. `ENG-204`, `RoadOpenApp.pdf`, `Zoning ApplicationNEW.pdf`) with in-chat interactive checklist and intake routing.

```mermaid
sequenceDiagram
    autonumber
    actor Citizen as Citizen / Business Applicant
    participant UI as Citizen Portal (Next.js)
    participant Router as Intent Router (FastAPI)
    participant Flow as Flow Engine (flows.json)
    participant RAG as Grounded RAG Engine
    participant PG as PostgreSQL (pgvector)
    participant Desk as Municipal Intake Desk

    Citizen->>UI: Submits inquiry or procedure request
    UI->>Router: POST /api/chat { message, session_id, option_id }

    alt Citizen selects Option in Active Flow
        Router->>Flow: advance_step(session_id, option_id)
        alt Next Step is Question / Prerequisite Check
            Flow-->>UI: Return next mandatory prerequisite question
            UI-->>Citizen: Render step options with requirement badge
        else Next Step is Form Issuance
            Flow-->>UI: Return FormIssuanceDetails packet
            UI-->>Citizen: Render Rich OfficialPdfCard (Code, Download, Checklist, Counter)
        else Disqualification
            Flow-->>UI: Return statutory disqualification & alternative board referral
            UI-->>Citizen: Display explanation and recovery steps
        end

    else New Procedural Intent Detected (e.g. "apply for building permit")
        Router->>Flow: start_flow(session_id, dept, flow_id)
        Flow-->>UI: Return Step 1 (Mandatory Prerequisite Check)
        UI-->>Citizen: Display initial options (Zoning verification)

    else Informational Inquiry (e.g. "What are pool setback distances?")
        Router->>RAG: answer_query(query, dept)
        RAG->>PG: Search <=> Cosine Distance (1 - distance >= 0.10)
        PG-->>RAG: Return top matching chunks & URLs
        alt Verified Citation Found
            RAG-->>UI: Return grounded answer with exact link citation & excerpt
            UI-->>Citizen: Display grounded response + clickable edisonnj.org citation card
        else No Verified Citation Found
            RAG-->>UI: Return municipal refusal + referral to physical counter/phone
            UI-->>Citizen: Display strict anti-hallucination notice
        end
    end

    opt Offline Form Submission
        Citizen->>Desk: Submits printed PDF + Checklist Attachments (Counter / Email)
        Desk-->>Citizen: Issues Municipal Intake Stamp & Tracking Receipt
    end
```

---

## 3. Data Flow Diagram (DFD) Level 0: Context Diagram

The Level 0 Context Diagram establishes the system boundary of the **Pixelvyne Smart Assistant (CivicIQ)** and details all inbound and outbound data flows with external entities:
- **Citizen / Applicant**: Submits inquiries, completes guided prerequisite steps, downloads official PDF forms, and checks attachment lists.
- **Department Intake Counter / Staff**: Receives assembled application packets, provides intake stamps, and updates office hours.
- **External Municipal Document Center (`edisonnj.org`)**: Live external documentation repository scraped and ingested into vector embeddings.
- **Municipal Administrator**: Updates department configurations (`config.json`), flowchart decision trees (`flows.json`), and static PDF files (`/forms/`).

```mermaid
flowchart LR
    Citizen(["Citizen / Business Applicant"])
    Admin(["Municipal Administrator"])
    EdisonWeb(["Township of Edison Document Center\n(edisonnj.org)"])
    IntakeDesk(["Department Intake Counter / Staff"])

    System[["0.0\nPixelvyne Smart Assistant\n(CivicIQ System Boundary)"]]

    Citizen -- "1. General Inquiries & Questions" --> System
    Citizen -- "2. Prerequisite Answers & Option Selections" --> System
    Citizen -- "3. Document Center Search Queries" --> System
    System -- "4. Grounded Answers with Official Citations" --> Citizen
    System -- "5. Guided Step-by-Step Questions" --> Citizen
    System -- "6. Official PDF Download & Preview" --> Citizen
    System -- "7. Mandatory Attachment Checklist" --> Citizen
    System -- "8. Submission Routing Instructions" --> Citizen

    Admin -- "9. Drop new /departments/ folders" --> System
    Admin -- "10. Update flows.json & config.json" --> System
    Admin -- "11. Upload official static PDFs" --> System

    EdisonWeb -- "12. Raw HTML, PDF Forms & Regulatory Text" --> System

    Citizen -. "13. Completed Application Packet + Attachments" .-> IntakeDesk
    IntakeDesk -. "14. Official Intake Stamp & Permit Number" .-> Citizen
```

---

## 4. Data Flow Diagram (DFD) Level 1: Subsystem Decomposition

The Level 1 DFD decomposes the system into six core operational processes, four primary data stores, and internal data flows.

### Processes:
- **1.0 Request Ingestion & Intent Disambiguation**: Receives citizen input, parses session state, and routes to Flow Engine, RAG Engine, or Document Center API.
- **2.0 Grounded RAG & Semantic Vector Search**: Embeds query, executes vector cosine search (`<=>`) in pgvector, validates relevance threshold, and formats citations.
- **3.0 Deterministic Flowchart State Machine**: Traverses decision trees from `flows.json`, enforces prerequisite validation, handles branching, and tracks step history.
- **4.0 Official Document Registry & PDF Delivery**: Retrieves static official PDF files from disk, generates download URLs, formats checklist, and supplies fill-in guidance.
- **5.0 Departmental Intake Routing Dispatch**: Attaches exact physical counter location, building address, hours, cutoff times, and direct email dispatch (e.g. `clerk@edisonnj.gov`).
- **6.0 Web Scraper & Vector Indexer**: Scrapes URLs from `knowledge_links.json`, chunks text into overlapping segments, computes embeddings, and stores in PostgreSQL `pgvector`.

### Data Stores:
- **D1: PostgreSQL `pgvector` Store**: Table `municipal_knowledge_chunks` holding 128-dim embeddings, text chunks, and URLs.
- **D2: Department Registry & Decision Trees**: Modular `/departments/<dept>/` holding `config.json` and `flows.json`.
- **D3: Static Official PDF Forms Store**: `/departments/<dept>/forms/*.pdf` containing authentic government forms.
- **D4: Citizen Session State Store**: In-memory and browser session tracking active flow ID, step progress, and history.
- **D5: Edison NJ Document Center Catalog**: Structured metadata for 80+ documents from `edisonnj.org/document_center/index.php`.

```mermaid
flowchart TD
    Citizen(["Citizen / Applicant"])
    Admin(["Municipal Administrator"])
    EdisonSite(["Edison Document Center (edisonnj.org)"])

    subgraph Processes["Pixelvyne Smart Assistant Core Subsystems"]
        P1["1.0\nRequest Ingestion &\nIntent Disambiguation"]
        P2["2.0\nGrounded RAG &\nVector Search (pgvector)"]
        P3["3.0\nDeterministic Flowchart\nState Machine"]
        P4["4.0\nOfficial Document Registry\n& PDF Issuance"]
        P5["5.0\nDepartmental Intake\nRouting Dispatch"]
        P6["6.0\nWeb Scraper &\nVector Indexer"]
    end

    subgraph DataStores["Data Stores"]
        D1[("D1: pgvector Database\n(municipal_knowledge_chunks)")]
        D2[("D2: Department Registry\n(flows.json & config.json)")]
        D3[("D3: Official PDF Forms\n(/departments/<dept>/forms/)")]
        D4[("D4: Session State Store\n(Active Flow & Step)")]
        D5[("D5: Document Center Catalog\n(edison_document_center.py)")]
    end

    %% Process 1 Inbound
    Citizen -->|"Input Message / Option ID"| P1
    P1 <-->|"Read/Write Session"| D4

    %% Routing logic
    P1 -->|"Informational Query"| P2
    P1 -->|"Procedure Request / Step Selection"| P3
    P1 -->|"Browse / Search Documents"| D5

    %% Process 2 (RAG)
    P2 <-->|"Cosine Query (<=>)"| D1
    P2 -->|"Grounded Response + Citations"| Citizen

    %% Process 3 (Flow Machine)
    P3 <-->|"Fetch Step & Prerequisite Logic"| D2
    P3 -->|"Prerequisite Questions"| Citizen
    P3 -->|"Prerequisites Satisfied"| P4

    %% Process 4 (PDF Registry)
    P4 <-->|"Stream Static PDF File"| D3
    P4 -->|"Fetch Submission Metadata"| P5
    P5 <-->|"Read Department Counters & Hours"| D2
    P4 -->|"Official PDF Card + Checklist + Routing"| Citizen

    %% Process 6 (Ingestion)
    Admin -->|"Trigger Ingestion Script"| P6
    EdisonSite -->|"HTML & Regulatory Content"| P6
    P6 -->|"Chunked Vectors & Embeddings"| D1

    %% Document Center Direct
    D5 -->|"Catalog Search Results"| Citizen
```

---

## 5. Security, Anti-Hallucination & Compliance Policies

1. **Zero AI Form Generation**: The system never uses an LLM to generate, synthesize, or alter municipal application forms. It serves the exact, static, authorized government PDF files directly from the departmental repository.
2. **Strict Grounded Inquiries**: The RAG engine compares cosine similarity against `pgvector` stored chunks. Any query falling below the strict threshold ($0.10$) triggers a graceful refusal and redirects the citizen to the physical counter desk or official telephone dispatch.
3. **Deterministic Prerequisite Gatekeeping**: Mandatory checks (e.g. single-family residential zoning, deed ownership standing, 811 utility locate ticket) are non-bypassable code paths. If a citizen cannot satisfy a prerequisite, the flow redirects them to the appropriate appeal board (e.g. Zoning Board of Adjustment for setback variances).
4. **Local Resilience**: In environments without a live PostgreSQL server, the unified vector store automatically transitions to local SQLite vector caching so testing and local development operate without disruption.
