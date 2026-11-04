import os
import re
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .config import (
    APP_NAME, APP_VERSION, MUNICIPALITY_NAME, ADMIN_API_KEY, APP_TAGLINE,
    GENERATED_DRAFTS_DIR
)
from .models import (
    ChatRequest, ChatResponse, FlowStartRequest, FlowStepRequest,
    DepartmentConfig, FlowDefinition, RagResult, RagCitation,
    FormStartSessionRequest, FormAnswerRequest, FormEditRequest,
    FormQuestionResponse, FormRecommendation
)
from .department_loader import registry
from .flow_engine import flow_engine
from .rag_engine import rag_engine
from .vector_store import vector_store
from .edison_document_center import EDISON_DOCUMENT_CATALOG, get_document_inventory
from .services import (
    form_schema_service,
    form_matcher,
    form_session_service,
    pdf_filler,
    submission_guidance_service,
    rag_service
)
from .llm_provider import llm_manager

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
    form_session_service.cancel_session(session_id)
    CHAT_HISTORIES.pop(session_id, None)
    return {"status": "success", "message": f"Procedure and conversation history reset for session {session_id}."}

@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    """
    Main conversational router for CivicIQ:
    - Maintains multi-turn conversation memory for context across prompts.
    - Cites verified Edison Engineering documentation.
    - Guides conversational form filling one question at a time.
    - Generates downloadable completed PDF drafts with signature guidance.
    - Delivers official PDF cards when explicitly requested in context.
    - Strictly returns out-of-context response for non-engineering queries.
    """
    session = flow_engine.get_session(req.session_id)
    history = CHAT_HISTORIES.setdefault(req.session_id, [])
    msg_clean = req.message.strip().lower()

    # Reset intent
    if msg_clean in ["/reset", "reset", "start over", "cancel", "restart"]:
        flow_engine.reset_session(req.session_id)
        form_session_service.cancel_session(req.session_id)
        CHAT_HISTORIES.pop(req.session_id, None)
        return ChatResponse(
            session_id=req.session_id,
            message="Your session has been reset. How may I assist you with Edison Township Engineering services today?",
            mode="general",
            department_id="engineering",
            completed=False
        )

    # Case 0: Active Form Filling Session in progress
    active_form_sess = form_session_service.get_session(req.session_id)
    if active_form_sess and active_form_sess.status in ["in_progress", "review"]:
        ok, status_msg, q_resp = form_session_service.answer_question(req.session_id, req.message)
        if q_resp:
            if q_resp.is_complete:
                ok_pdf, pdf_msg, pdf_path, pdf_url = pdf_filler.generate_draft_pdf(
                    session_id=req.session_id,
                    form_id=q_resp.form_id,
                    answers=q_resp.collected_answers
                )
                guidance = submission_guidance_service.get_guidance(q_resp.form_id, q_resp.collected_answers)
                final_msg = f"{q_resp.message}\n\n{guidance['markdown_guidance']}"
                history.append({"role": "user", "content": req.message})
                history.append({"role": "assistant", "content": final_msg})
                CHAT_HISTORIES[req.session_id] = history[-10:]
                return ChatResponse(
                    session_id=req.session_id,
                    message=final_msg,
                    mode="form_fill",
                    completed=True,
                    pdf_download_url=pdf_url,
                    submission_guidance=guidance,
                    form_session_info=q_resp.model_dump()
                )
            else:
                history.append({"role": "user", "content": req.message})
                history.append({"role": "assistant", "content": q_resp.message})
                CHAT_HISTORIES[req.session_id] = history[-10:]
                return ChatResponse(
                    session_id=req.session_id,
                    message=q_resp.message,
                    mode="form_fill",
                    completed=False,
                    form_session_info=q_resp.model_dump()
                )

    # Case 0.5: Citizen accepts offer to fill out an application form
    last_bot_msg = history[-1].get("content", "").lower() if history else ""
    offered_form_fill = any(phrase in last_bot_msg for phrase in [
        "help you fill out this application",
        "help you fill out the application",
        "prepare this application"
    ])
    explicit_fill_intent = any(phrase in msg_clean for phrase in [
        "fill it out", "help me fill", "start application", "prepare application", "fill out the application"
    ])
    if (offered_form_fill or explicit_fill_intent) and (not session or session.completed):
        # Find which form was offered or matches context
        target_form_id = None
        if "road opening" in last_bot_msg or "road" in msg_clean or "excavation" in msg_clean:
            target_form_id = "road_opening"
        elif "sewer" in last_bot_msg or "sewer" in msg_clean:
            target_form_id = "sewer_connection"
        elif "zoning" in last_bot_msg:
            target_form_id = "zoning_permit"
        else:
            rec = form_matcher.match_form(req.message, history=history)
            if rec and rec.is_application_form:
                target_form_id = rec.form.form_id

        if target_form_id:
            ok, start_msg, q_resp = form_session_service.start_session(req.session_id, target_form_id)
            if ok and q_resp:
                history.append({"role": "user", "content": req.message})
                history.append({"role": "assistant", "content": q_resp.message})
                CHAT_HISTORIES[req.session_id] = history[-10:]
                return ChatResponse(
                    session_id=req.session_id,
                    message=q_resp.message,
                    mode="form_fill",
                    completed=False,
                    form_session_info=q_resp.model_dump()
                )

    # Case 1: Active procedural flow (advanced by button option selection OR typed natural language!)
    if session and not session.completed:
        # Check if the user is attempting to completely change topics (e.g. asking about road opening while in tree flow)
        different_flow = rag_engine.detect_flow_intent(req.message, req.department_id)
        if different_flow and different_flow[1] != session.flow_id:
            flow_engine.reset_session(req.session_id)
            session = None
        else:
            success, msg, step, form_packet = flow_engine.advance_step(
                session_id=req.session_id,
                option_id=req.selected_option_id,
                user_text=req.message
            )
            if success and step:
                citations = []
                if session.flow_id == "tree_removal_flow":
                    citations = [
                        RagCitation(
                            url="https://cms2.revize.com/revize/edisonnj/document_center/Permit%20Flow%20Charts.pdf",
                            title="Township of Edison Official Permit Flow Charts - Tree Removal Permit",
                            category="Procedure/guideline",
                            department_id="engineering",
                            relevance_score=1.0,
                            excerpt="Decision tree flowchart determining when a Tree Removal Permit is required, emergency removal protocols, and subdivision/demolition requirements (Page 3)."
                        )
                    ]
                user_content = req.message if not req.selected_option_id else f"Selected option: {req.selected_option_id}"
                history.append({"role": "user", "content": user_content})
                history.append({"role": "assistant", "content": step.message})
                return ChatResponse(
                    session_id=req.session_id,
                    message=step.message,
                    mode="flow",
                    options=step.options,
                    form_packet=form_packet,
                    citations=citations,
                    current_step=step,
                    active_flow_id=session.flow_id,
                    department_id=session.department_id,
                    completed=session.completed
                )

    # Check if user explicitly asked to download or access an official form (with context awareness!)
    form_packet = rag_engine.match_official_form_packet(req.message, "engineering", history=history)

    # Case 2: Intent detection for starting a flow
    flow_match = rag_engine.detect_flow_intent(req.message, req.department_id)
    if flow_match and not form_packet and (not session or session.completed):
        dept_id, flow_id = flow_match
        success, msg, step, _ = flow_engine.start_flow(
            session_id=req.session_id,
            department_id=dept_id,
            flow_id=flow_id,
            initial_user_text=req.message
        )
        if success and step:
            active_sess = flow_engine.get_session(req.session_id)
            is_completed = active_sess.completed if active_sess else False
            citations = []
            if flow_id == "tree_removal_flow":
                citations = [
                    RagCitation(
                        url="https://cms2.revize.com/revize/edisonnj/document_center/Permit%20Flow%20Charts.pdf",
                        title="Township of Edison Official Permit Flow Charts - Tree Removal Permit",
                        category="Procedure/guideline",
                        department_id="engineering",
                        relevance_score=1.0,
                        excerpt="Decision tree flowchart determining when a Tree Removal Permit is required, emergency removal protocols, and subdivision/demolition requirements (Page 3)."
                    )
                ]
            history.append({"role": "user", "content": req.message})
            history.append({"role": "assistant", "content": step.message})
            return ChatResponse(
                session_id=req.session_id,
                message=step.message,
                mode="flow",
                options=step.options,
                citations=citations,
                current_step=step,
                active_flow_id=flow_id,
                department_id=dept_id,
                completed=is_completed
            )

    # Case 3: Grounded Conversational RAG with Multi-turn History Context
    rag_res: RagResult = rag_engine.answer_query(
        query=req.message,
        department_id="engineering",
        history=history
    )

    final_message = rag_res.answer

    # Check for Form Recommendation and Offer Conversational Fill
    rec = form_matcher.match_form(req.message, history=history)
    form_rec_dict = None
    if rec and rec.is_application_form and rag_res.grounded:
        form_rec_dict = rec.model_dump()
        # If user expresses intent to apply or request permit, append the conversational filling offer
        if any(w in msg_clean for w in ["apply", "permit", "need a form", "fill out", "want to", "how do i get"]):
            final_message += f"\n\nWould you like me to help you fill out this application?"

    # Record history
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": final_message})
    CHAT_HISTORIES[req.session_id] = history[-10:]

    return ChatResponse(
        session_id=req.session_id,
        message=final_message,
        mode="rag",
        citations=rag_res.citations,
        form_packet=form_packet or rag_res.form_packet,
        form_recommendation=form_rec_dict,
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

# --- Conversational Form Identification & Filling Endpoints ---

@app.get("/api/forms/recommend")
def recommend_form(query: str = Query(...)):
    """Identifies and recommends official forms matching resident query."""
    rec = form_matcher.match_form(query)
    if not rec:
        return {"matched": False, "message": "No verified application form matched your query."}
    return {"matched": True, "recommendation": rec.model_dump()}

@app.post("/api/form-session/start", response_model=FormQuestionResponse)
def start_form_session(req: FormStartSessionRequest):
    """Starts a step-by-step conversational form filling session."""
    ok, msg, resp = form_session_service.start_session(req.session_id, req.form_id)
    if not ok or not resp:
        raise HTTPException(status_code=400, detail=msg)
    return resp

@app.post("/api/form-session/answer", response_model=FormQuestionResponse)
def answer_form_session(req: FormAnswerRequest):
    """Submits answer for the current question in an active form session."""
    ok, msg, resp = form_session_service.answer_question(req.session_id, req.answer)
    if not ok or not resp:
        raise HTTPException(status_code=400, detail=msg)
    return resp

@app.post("/api/form-session/edit", response_model=FormQuestionResponse)
def edit_form_session(req: FormEditRequest):
    """Edits a previously submitted answer in an active form session."""
    ok, msg, resp = form_session_service.edit_answer(req.session_id, req.field_name, req.new_answer)
    if not ok or not resp:
        raise HTTPException(status_code=400, detail=msg)
    return resp

@app.get("/api/form-session/review")
def review_form_session(session_id: str = Query(...)):
    """Returns review summary of all collected information."""
    state = form_session_service.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="No active application session found.")
    form = form_schema_service.get_form_by_id(state.form_id)
    if not form:
        raise HTTPException(status_code=404, detail="Form definition not found.")
    return form_session_service._build_review_response(state, form)

@app.post("/api/form-session/generate-pdf")
def generate_form_pdf(session_id: str = Query(...)):
    """Generates a completed municipal draft PDF populated with resident answers."""
    state = form_session_service.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="No active application session found.")
    ok, msg, path, url = pdf_filler.generate_draft_pdf(session_id, state.form_id, state.answers)
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    guidance = submission_guidance_service.get_guidance(state.form_id, state.answers)
    return {
        "status": "success",
        "pdf_download_url": url,
        "filename": Path(path).name,
        "submission_guidance": guidance
    }

@app.get("/api/form-session/download/{session_id}/{filename}")
def download_draft_pdf(session_id: str, filename: str):
    """
    Securely streams the generated draft PDF.
    Prevents path traversal and validates file existence.
    """
    safe_filename = Path(filename).name
    file_path = GENERATED_DRAFTS_DIR / session_id / safe_filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Requested draft PDF document not found.")

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=safe_filename,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "Cache-Control": "private, max-age=600"
        }
    )

@app.get("/api/llm/status")
def get_llm_status():
    """Returns non-sensitive status and availability for all configured free-first LLM providers."""
    return llm_manager.get_status()

