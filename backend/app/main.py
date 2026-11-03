import os
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .config import APP_NAME, APP_VERSION, MUNICIPALITY_NAME, ADMIN_API_KEY, APP_TAGLINE
from .models import (
    ChatRequest, ChatResponse, FlowStartRequest, FlowStepRequest,
    DepartmentConfig, FlowDefinition, RagResult
)
from .department_loader import registry
from .flow_engine import flow_engine
from .rag_engine import rag_engine
from .vector_store import vector_store
from .edison_document_center import EDISON_DOCUMENT_CATALOG, get_document_inventory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("main")

# Multi-turn conversation histories by session_id
CHAT_HISTORIES = {}

app = FastAPI(
    title=f"{APP_NAME} - {APP_TAGLINE}",
    version=APP_VERSION,
    description=f"Citizen procedural assistant and grounded knowledge portal for {MUNICIPALITY_NAME}."
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    stats = vector_store.get_stats()
    return {
        "status": "healthy",
        "app": APP_NAME,
        "version": APP_VERSION,
        "municipality": MUNICIPALITY_NAME,
        "vector_backend": stats.get("backend", "pgvector"),
        "departments_loaded": len(registry.departments),
        "vector_store_chunks": stats["total_chunks"]
    }

@app.get("/api/departments")
def list_departments():
    """Returns list of registered municipal departments."""
    return [dept.model_dump() for dept in registry.get_departments()]

@app.get("/api/departments/{dept_id}")
def get_department(dept_id: str):
    """Returns department config, its available flows, and official forms."""
    dept = registry.get_department(dept_id)
    if not dept:
        raise HTTPException(status_code=404, detail=f"Department '{dept_id}' not found.")
    
    flows = [f.model_dump() for f in registry.get_flows_for_dept(dept_id)]
    forms = registry.list_forms_for_dept(dept_id)
    links = [l.model_dump() for l in registry.knowledge_links.get(dept_id, [])]

    return {
        "config": dept.model_dump(),
        "flows": flows,
        "forms": forms,
        "links": links
    }

@app.get("/api/flows/{dept_id}")
def get_department_flows(dept_id: str):
    """Returns all deterministic flows available in the given department."""
    flows = registry.get_flows_for_dept(dept_id)
    return [f.model_dump() for f in flows]

@app.get("/api/forms/{dept_id}/{filename}")
def serve_official_form(dept_id: str, filename: str):
    """
    Streams official static PDF document from /departments/<dept_id>/forms/<filename>.
    Does not allow path traversal.
    """
    safe_filename = Path(filename).name
    pdf_path = registry.get_form_path(dept_id, safe_filename)
    if not pdf_path or not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"Official form '{filename}' not found for department '{dept_id}'.")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=safe_filename,
        headers={
            "Content-Disposition": f'inline; filename="{safe_filename}"',
            "Cache-Control": "public, max-age=3600"
        }
    )

@app.post("/api/flow/start", response_model=ChatResponse)
def start_flow_endpoint(req: FlowStartRequest):
    """Explicitly launches a deterministic flow for a citizen session."""
    success, msg, step, form_packet = flow_engine.start_flow(
        session_id=req.session_id,
        department_id=req.department_id,
        flow_id=req.flow_id
    )
    if not success or not step:
        raise HTTPException(status_code=400, detail=msg)

    return ChatResponse(
        session_id=req.session_id,
        message=step.message,
        mode="flow",
        options=step.options,
        current_step=step,
        active_flow_id=req.flow_id,
        department_id=req.department_id,
        completed=False
    )

@app.post("/api/flow/step", response_model=ChatResponse)
def advance_flow_step(req: FlowStepRequest):
    """Advances the active procedure step by choosing an option."""
    session = flow_engine.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=400, detail="No active flow session. Start a procedure first.")

    success, msg, step, form_packet = flow_engine.advance_step(
        session_id=req.session_id,
        option_id=req.option_id
    )

    if not success or not step:
        raise HTTPException(status_code=400, detail=msg)

    return ChatResponse(
        session_id=req.session_id,
        message=step.message,
        mode="flow",
        options=step.options,
        form_packet=form_packet,
        current_step=step,
        active_flow_id=session.flow_id,
        department_id=session.department_id,
        completed=session.completed
    )

@app.post("/api/flow/reset")
def reset_flow(session_id: str = Query(...)):
    """Resets procedure and chat history state for session."""
    flow_engine.reset_session(session_id)
    CHAT_HISTORIES.pop(session_id, None)
    return {"status": "success", "message": f"Procedure and conversation history reset for session {session_id}."}

@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    """
    Main conversational router for CivicIQ:
    - Maintains multi-turn conversation memory for context across prompts.
    - Cites verified Edison Engineering documentation.
    - Delivers official PDF cards when explicitly requested in context.
    - Strictly returns out-of-context response for non-engineering queries.
    """
    session = flow_engine.get_session(req.session_id)
    history = CHAT_HISTORIES.setdefault(req.session_id, [])

    # Reset intent
    if req.message.strip().lower() in ["/reset", "reset", "start over", "cancel", "restart"]:
        flow_engine.reset_session(req.session_id)
        CHAT_HISTORIES.pop(req.session_id, None)
        return ChatResponse(
            session_id=req.session_id,
            message="Your session has been reset. How may I assist you with Edison Township Engineering services today?",
            mode="general",
            department_id="engineering",
            completed=False
        )

    # Case 1: Citizen clicked an option in an active flow
    if req.selected_option_id and session and not session.completed:
        success, msg, step, form_packet = flow_engine.advance_step(
            session_id=req.session_id,
            option_id=req.selected_option_id
        )
        if success and step:
            history.append({"role": "user", "content": f"Selected option: {req.selected_option_id}"})
            history.append({"role": "assistant", "content": step.message})
            return ChatResponse(
                session_id=req.session_id,
                message=step.message,
                mode="flow",
                options=step.options,
                form_packet=form_packet,
                current_step=step,
                active_flow_id=session.flow_id,
                department_id=session.department_id,
                completed=session.completed
            )

    # Check if user explicitly asked to download or access an official form (with context awareness!)
    form_packet = rag_engine.match_official_form_packet(req.message, "engineering", history=history)

    # Case 2: Intent detection for starting a flow (only if user explicitly says "start/apply flow")
    flow_match = rag_engine.detect_flow_intent(req.message, req.department_id)
    if flow_match and not form_packet and (not session or session.completed):
        dept_id, flow_id = flow_match
        success, msg, step, _ = flow_engine.start_flow(req.session_id, dept_id, flow_id)
        if success and step:
            history.append({"role": "user", "content": req.message})
            history.append({"role": "assistant", "content": step.message})
            return ChatResponse(
                session_id=req.session_id,
                message=step.message,
                mode="flow",
                options=step.options,
                current_step=step,
                active_flow_id=flow_id,
                department_id=dept_id,
                completed=False
            )

    # Case 3: Grounded Conversational RAG with Multi-turn History Context
    rag_res: RagResult = rag_engine.answer_query(
        query=req.message,
        department_id="engineering",
        history=history
    )

    final_message = rag_res.answer

    # Record history
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": final_message})
    CHAT_HISTORIES[req.session_id] = history[-10:]

    return ChatResponse(
        session_id=req.session_id,
        message=final_message,
        mode="rag",
        citations=rag_res.citations,
        form_packet=form_packet,
        department_id="engineering",
        completed=False
    )

@app.post("/api/ingest")
def trigger_ingestion(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    clear: bool = False
):
    """
    Protected Admin endpoint to trigger official document discovery, PDF extraction,
    and vector re-indexing for Edison Township.
    Requires header 'X-Admin-Key: <ADMIN_API_KEY>'.
    """
    if not x_admin_key or x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Admin-Key header.")

    from backend.scripts.ingest import run_ingestion_and_inventory
    result = run_ingestion_and_inventory()
    registry.reload()
    return {
        "status": "success",
        "message": "Official Edison Township document ingestion and indexing completed successfully.",
        "details": result
    }

@app.get("/api/vector/stats")
def get_vector_stats():
    """Returns vector store indexing statistics."""
    return vector_store.get_stats()

@app.get("/api/document-inventory")
def get_document_inventory_endpoint():
    """
    Returns the comprehensive Edison Township document inventory
    including title, department, document type, extraction status,
    needs_manual_verification, original URLs, and local paths.
    """
    inventory = get_document_inventory()
    return {
        "portal_name": "Township of Edison Official Document Center",
        "official_source": "https://www.edisonnj.org/document_center/index.php",
        "total_documents": len(inventory),
        "documents": inventory
    }

@app.get("/api/document-center")
def get_document_center(category: Optional[str] = None, search: Optional[str] = None):
    """
    Returns the Township of Edison Document Center catalog (edisonnj.org/document_center/index.php).
    Supports keyword filtering and departmental category filtering.
    """
    docs = get_document_inventory()
    if category and category.lower() != "all":
        docs = [d for d in docs if (d.get("category") or d.get("document_type", "")).lower() == category.lower()]
    if search and search.strip():
        q = search.lower().strip()
        docs = [d for d in docs if q in d.get("title", "").lower() or q in (d.get("description") or d.get("official_summary", "")).lower() or q in (d.get("category") or d.get("document_type", "")).lower()]

    categories = sorted(list(set(d.get("category") or d.get("document_type", "General") for d in get_document_inventory())))
    return {
        "portal_url": "https://www.edisonnj.org/document_center/index.php",
        "portal_name": "Township of Edison Document Center",
        "total_documents": len(docs),
        "categories": ["All"] + categories,
        "documents": docs
    }
