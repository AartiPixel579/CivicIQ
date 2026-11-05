# CivicIQ — Production Deployment Guide (Vercel & Render)

This step-by-step guide walks you through deploying **CivicIQ** into production using **Vercel** for the Next.js frontend and **Render** for the FastAPI backend, with persistent or zero-config vector storage.

---

## 🏛️ Architecture Overview

CivicIQ is split into two cleanly separated layers:

```
                  ┌─────────────────────────────────────────┐
                  │           Citizen / Browser             │
                  └──────────────────┬──────────────────────┘
                                     │
                     HTTPS Requests  │
                                     ▼
        ┌────────────────────────────────────────────────────────┐
        │              Frontend (Hosted on Vercel)               │
        │  • Next.js 14 App Router + Tailwind CSS               │
        │  • Official Township of Edison Branding & Logo        │
        │  • Interactive Chat & Form Session Flow               │
        │  • Next.js Rewrites Proxy (`/api/*` -> Render Backend) │
        └────────────────────────────┬───────────────────────────┘
                                     │
                        Secure API   │ Reverse Proxy / CORS
                                     ▼
        ┌────────────────────────────────────────────────────────┐
        │               Backend (Hosted on Render)               │
        │  • FastAPI Python 3.11 Web Service                     │
        │  • RAG Engine & LLM Provider Chain (Gemini/Groq/OpenR) │
        │  • Deterministic Decision Flows (Tree, Soil, Zoning)   │
        │  • ReportLab Automated PDF Form Filler                 │
        │  • Auto-indexing of 14 Official Municipal Forms        │
        └────────────────────────────┬───────────────────────────┘
                                     │
                        Dual-Backend │ Vector Storage
                                     ▼
        ┌────────────────────────────────────────────────────────┐
        │              Database / Vector Knowledge               │
        │  • Primary: PostgreSQL + pgvector (Supabase/Neon/Render)│
        │  • Resilient Fallback: SQLite Vector Store (Zero-setup)│
        └────────────────────────────────────────────────────────┘
```

---

## 📋 Prerequisites & Accounts

Before starting, make sure you have:
1. **GitHub Account**: Access to your repository (`https://github.com/AartiPixel579/CivicIQ`).
2. **Render Account**: Free account at [render.com](https://render.com).
3. **Vercel Account**: Free account at [vercel.com](https://vercel.com).
4. **LLM API Key** (at least one free tier key):
   - **Google Gemini API Key** (Recommended): Get free key at [aistudio.google.com](https://aistudio.google.com).
   - **Groq API Key** (Fast backup): Get free key at [console.groq.com](https://console.groq.com).
   - **OpenRouter API Key** (Optional free backup): Get free key at [openrouter.ai](https://openrouter.ai).

---

## 🚀 Step 1: Deploy the Backend on Render

### Option A: Using the `render.yaml` Blueprint (Easiest)
1. Log in to [dashboard.render.com](https://dashboard.render.com).
2. Click **New +** in the top right and select **Blueprint**.
3. Connect your GitHub repository: `AartiPixel579/CivicIQ`.
4. Select the branch: `deployment/vercel-render`.
5. Render will automatically parse `render.yaml` and configure the Web Service with Python 3.11, build commands, and start commands.
6. Fill in your environment variables when prompted (see table below).
7. Click **Apply**.

---

### Option B: Manual Web Service Setup
If you prefer configuring manually through the Render dashboard:
1. Go to [dashboard.render.com](https://dashboard.render.com) and click **New +** -> **Web Service**.
2. Select **Build and deploy from a Git repository**.
3. Choose `AartiPixel579/CivicIQ`.
4. Configure the settings:
   - **Name**: `civiciq-backend`
   - **Region**: Choose the region closest to you (e.g., *Oregon (US West)* or *Ohio (US East)*).
   - **Branch**: `deployment/vercel-render`
   - **Root Directory**: Leave blank (repository root).
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: `Free`
5. Expand **Advanced** -> **Health Check Path**: `/api/health`.
6. Under **Environment Variables**, add the required backend variables (see [Environment Variables Reference](#-environment-variables-reference)).
7. Click **Create Web Service**.

> [!NOTE]
> **Render Free Tier Cold Starts**: On Render's free tier, inactive services sleep after 15 minutes of inactivity. When a new request arrives, it may take 30–50 seconds for the service to spin up. Subsequent requests respond instantly.

---

## 🗄️ Step 2: Database & Vector Storage Setup

CivicIQ includes a dual-mode vector storage architecture. Choose the option that fits your needs:

### Option 1: Automatic SQLite Vector Storage (Zero Configuration)
- **Setup required**: None! Leave `DATABASE_URL` empty in your Render environment variables.
- **How it works**: CivicIQ detects that PostgreSQL is not configured and automatically activates its built-in SQLite vector database (`backend/data/vector_store.db`).
- **Cold Boot Auto-Indexing**: Whenever the backend starts up, if the vector store has 0 chunks, it automatically reads, extracts, and indexes all 14 official Edison Township forms located in `departments/engineering/forms/` within ~2 seconds.

---

### Option 2: Hosted PostgreSQL with pgvector (Persistent Production)
If you want persistent relational database storage with native PostgreSQL vector similarity:

1. **Create a Free pgvector Database**:
   - **Supabase (Recommended - Free Tier)**: Create a project at [supabase.com](https://supabase.com). In the SQL Editor, run:
     ```sql
     CREATE EXTENSION IF NOT EXISTS vector;
     ```
     Copy the connection string (URI mode) from **Project Settings** -> **Database**.
   - **Neon (Free Tier)**: Create a Postgres database at [neon.tech](https://neon.tech) and copy the connection string.
   - **Render PostgreSQL**: You can also add a PostgreSQL instance directly inside Render.
2. **Add `DATABASE_URL` to Render**:
   - In your Render Web Service dashboard, go to **Environment**.
   - Set `DATABASE_URL` to your full connection string:
     ```
     postgresql://postgres:[YOUR-PASSWORD]@[YOUR-HOST]:5432/postgres?sslmode=require
     ```
   - CivicIQ will automatically connect, initialize the `municipal_knowledge_chunks` table, and store vector embeddings. If the database is ever temporarily unreachable, CivicIQ seamlessly falls back to local SQLite without crashing.

---

## 🌐 Step 3: Deploy the Frontend on Vercel

1. Log in to [vercel.com](https://vercel.com) and click **Add New...** -> **Project**.
2. Connect your GitHub account and import `AartiPixel579/CivicIQ`.
3. In the project configuration screen:
   - **Project Name**: `civiciq` (or your preferred name).
   - **Framework Preset**: `Next.js` (automatically detected).
   - **Root Directory**: Click **Edit** and select `frontend` (⚠️ **Crucial Step**).
4. Expand **Environment Variables** and add:
   - `NEXT_PUBLIC_API_URL`: Your Render backend URL, e.g.:
     ```
     https://civiciq-backend.onrender.com
     ```
   - `BACKEND_INTERNAL_URL`: Same value as above:
     ```
     https://civiciq-backend.onrender.com
     ```
5. Click **Deploy**.
6. Vercel will build the frontend and assign a live URL (e.g., `https://civiciq.vercel.app`).

### Update Render CORS with your Vercel URL
After Vercel assigns your live domain (e.g., `https://civiciq.vercel.app`):
1. Go back to Render -> `civiciq-backend` -> **Environment**.
2. Update `ALLOWED_ORIGINS` to include your Vercel production URL:
   ```
   ALLOWED_ORIGINS=https://civiciq.vercel.app
   ```
   *(CivicIQ automatically supports localhost and all `https://*.vercel.app` preview deployments out-of-the-box).*

---

## 🔑 Environment Variables Reference

### Backend Variables (Render)

| Variable | Required | Default Value | Description |
| :--- | :---: | :--- | :--- |
| `ENVIRONMENT` | Yes | `production` | Deployment mode (`production` enables strict CORS and admin protection). |
| `DATABASE_URL` | Optional | *(empty)* | Connection URI for PostgreSQL + pgvector. If empty, SQLite is used automatically. |
| `VECTOR_STORE_PROVIDER` | No | `pgvector` | Vector provider engine (`pgvector` with automatic SQLite fallback). |
| `ALLOWED_ORIGINS` | Yes | *(empty)* | Comma-separated list of allowed frontend domains (e.g. `https://civiciq.vercel.app`). |
| `ADMIN_API_KEY` | Yes | *(auto-generated)* | 32+ character secret for protecting `/api/ingest`. Auto-generated by `render.yaml`. |
| `LLM_PRIMARY_PROVIDER` | No | `gemini` | Primary AI provider (`gemini` or `groq`). |
| `GEMINI_API_KEY` | Recommended | *(empty)* | Google Gemini API Key from Google AI Studio. |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Free tier supported Google Gemini model. |
| `GROQ_API_KEY` | Recommended | *(empty)* | Groq API Key from Groq Console. |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Ultra-fast Llama 3 model on Groq. |

---

### Frontend Variables (Vercel)

| Variable | Required | Example Value | Description |
| :--- | :---: | :--- | :--- |
| `NEXT_PUBLIC_API_URL` | Yes | `https://civiciq-backend.onrender.com` | Base URL used by client-side browser requests to reach the API. |
| `BACKEND_INTERNAL_URL` | Yes | `https://civiciq-backend.onrender.com` | Backend URL used by Next.js rewrites to securely proxy API & form requests. |

---

## ✅ Step 4: Post-Deployment Verification Checklist

Once both services are deployed, perform these checks:

- [ ] **1. Backend Health Check**:
  Visit `https://<your-render-url>/api/health` in your browser.
  Expected output:
  ```json
  {
    "status": "healthy",
    "app": "CivicIQ",
    "version": "2.2.0",
    "municipality": "Township of Edison, New Jersey",
    "vector_backend": "SQLite Vector Store (Local fallback)" or "pgvector (PostgreSQL)",
    "departments_loaded": 1,
    "vector_store_chunks": 70
  }
  ```

- [ ] **2. LLM Provider Status**:
  Visit `https://<your-render-url>/api/llm/status`.
  Verify that your configured provider (`gemini` or `groq`) shows `"configured": true`.

- [ ] **3. Document Inventory & Forms**:
  Visit `https://<your-render-url>/api/document-inventory`.
  Verify that the 14 official Edison Township Engineering documents are listed.

- [ ] **4. Frontend Branding & Logo**:
  Open your Vercel URL `https://<your-vercel-domain>.vercel.app`.
  Confirm that the official Township of Edison seal/logo displays in the top header.

- [ ] **5. Conversational Test (Tree Removal)**:
  Type: `"How much does a tree removal permit cost?"`
  Verify the answer indicates: **\$25 filing fee (waived for senior citizens aged 62 or older)**.

- [ ] **6. Ambiguity Test**:
  Type: `"removal"`
  Verify CivicIQ asks for clarification: *"What would you like to remove — a tree or soil?"*

- [ ] **7. Soil Import Flow**:
  Type: `"I want to import 20 cubic yards of soil"`
  Verify CivicIQ explains that importing under 25 cubic yards does not require a soil permit (only an Engineering plot plan review).

- [ ] **8. Guided PDF Application Generator**:
  Type: `"I want to remove a tree"`, follow the quick answers, and click **Download Completed Application**.
  Verify the generated official municipal PDF downloads to your device.

---

## 🔒 Security & Maintenance Best Practices

1. **Never Commit Secrets**:
   - The repository `.gitignore` ignores all `.env` and `.env.*` files.
   - Use `.env.example` as a template for local variables.
2. **Rotating API Keys**:
   - If an API key is ever compromised, generate a new key at the provider's console (e.g. AI Studio, Groq) and update the variable directly in the Render dashboard. Render will automatically redeploy with the updated secret without modifying any Git history.
3. **Draft PDF Storage Note**:
   - Draft PDFs are generated into `backend/data/generated_drafts/` and streamed directly to the citizen. Since Render's free tier filesystem is ephemeral, files are retained during active sessions and cleared upon container restarts. For high-volume municipal archiving, integrate AWS S3 or Supabase Storage.
