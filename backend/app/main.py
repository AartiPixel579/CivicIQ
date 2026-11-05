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
    GENERATED_DRAFTS_DIR, ENVIRONMENT, IS_PRODUCTION, ALLOWED_ORIGINS,
    UNCONFIGURED_SERVICE_MESSAGE
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

# Configure CORS origins based on environment
default_dev_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

cors_origins = default_dev_origins.copy()
if ALLOWED_ORIGINS:
    cors_origins.extend(ALLOWED_ORIGINS)

# Deduplicate origins preserving order
cors_origins = list(dict.fromkeys(cors_origins))

if "*" in cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=r"https://.*\.vercel\.app" if IS_PRODUCTION else None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

@app.on_event("startup")
def on_startup():
    """
    On startup, verify vector store chunks. If empty (such as on a fresh Render deployment),
    automatically trigger ingestion of official Edison Township municipal documents.
    """
    try:
        stats = vector_store.get_stats()
        if stats.get("total_chunks", 0) == 0:
            logger.info("Vector store is empty on startup. Triggering automatic initial ingestion...")
            from backend.scripts.ingest import run_ingestion_and_inventory
            run_ingestion_and_inventory()
            registry.reload()
            logger.info(
                "Initial ingestion completed successfully. Total indexed chunks: %d",
                vector_store.get_stats().get("total_chunks", 0)
            )
    except Exception as e:
        logger.warning(f"Automatic startup ingestion notice: {e}")

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

@app.get("/api/forms/{dept_id}/{filename:path}")
def serve_official_form(dept_id: str, filename: str):
    """
    Streams official static PDF document from /departments/<dept_id>/forms/<filename>.
    Does not allow path traversal.
    """
    import urllib.parse
    decoded_filename = urllib.parse.unquote(filename)
    safe_filename = Path(decoded_filename).name
    pdf_path = registry.get_form_path(dept_id, safe_filename)
    if not pdf_path or not pdf_path.exists():
        for alt_dept in ["engineering", "public_works", "zoning"]:
            candidate = registry.get_form_path(alt_dept, safe_filename)
            if candidate and candidate.exists():
                pdf_path = candidate
                break
    if not pdf_path or not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"Official form '{safe_filename}' not found for department '{dept_id}'.")

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
    user_accepted_offer = offered_form_fill and any(w in msg_clean for w in [
        "yes", "sure", "ok", "okay", "yep", "please", "go ahead", "let's do it"
    ]) and not any(phrase in msg_clean for phrase in [
        "tree", "soil", "road", "sewer", "site", "zoning", "procedure", "how to", "what about", "help me with"
    ])
    if (user_accepted_offer or explicit_fill_intent) and (not session or session.completed):
        # Find which form was offered or matches context
        target_form_id = None
        if "tree" in msg_clean or "tree" in last_bot_msg:
            target_form_id = "tree_removal"
        elif "soil import" in msg_clean or "soil import" in last_bot_msg:
            target_form_id = "soil_import"
        elif "soil export" in msg_clean or "soil export" in last_bot_msg:
            target_form_id = "soil_export"
        elif "road opening" in last_bot_msg or "road" in msg_clean or "excavation" in msg_clean:
            target_form_id = "road_opening"
        elif "sewer" in last_bot_msg or "sewer" in msg_clean:
            target_form_id = "sewer_connection"
        elif "zoning permit" in last_bot_msg or "zoning" in msg_clean:
            target_form_id = "zoning_permit"
        else:
            rec = form_matcher.match_form(req.message, history=history)
            if rec and rec.is_application_form:
                target_form_id = rec.form.form_id

        if target_form_id:
            if target_form_id == "tree_removal":
                tree_notice = (
                    "Interactive form filling for Tree Removal is currently unavailable in the assistant. "
                    "You can download and complete the official blank [Township of Edison Tree Removal Permit Application](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf) "
                    "directly and submit it to the Division of Engineering."
                )
                history.append({"role": "user", "content": req.message})
                history.append({"role": "assistant", "content": tree_notice})
                CHAT_HISTORIES[req.session_id] = history[-10:]
                return ChatResponse(
                    session_id=req.session_id,
                    message=tree_notice,
                    mode="rag",
                    completed=False
                )

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

    # Resolve empty message from selected_option_id if needed
    OPTION_LABEL_MAP = {
        "opt_remove_tree": "Tree",
        "opt_remove_soil": "Soil",
        "opt_remove_other": "Something else",
        "opt_soil_import": "Bring soil onto property (Soil Import)",
        "opt_soil_export": "Remove soil from property (Soil Export)",
        "opt_soil_10_plus": "10 cubic yards or more",
        "opt_soil_under_10": "Less than 10 cubic yards",
        "opt_tree_has_permit": "Yes, I have an approved permit",
        "opt_tree_no_permit": "No, I do not have a permit",
        "opt_tree_urgent": "It is an emergency",
        "opt_tree_is_emergency": "Yes, it is an emergency",
        "opt_tree_planned": "Planned, non-emergency removal",
        "opt_excavate_soil": "Remove soil from property (Soil Export)",
        "opt_excavate_street": "Street / pavement excavation",
        "opt_street_opening": "Street Opening / Excavation",
        "opt_street_apron": "Driveway Apron / Curb",
        "opt_street_other": "Something else",
        "opt_tree_remove": "Remove a tree",
        "opt_tree_fee": "Tree permit fees",
        "opt_tree_docs": "Required documents",
        "opt_permit_tree": "Tree Removal Permit",
        "opt_permit_soil": "Soil Import / Export Permit",
        "opt_permit_other": "Other municipal service",
        "opt_app_tree": "Tree Removal Application",
        "opt_app_soil_imp": "Soil Import Application",
        "opt_app_soil_exp": "Soil Export Application",
        "opt_apply_yes": "Yes, help me apply",
        "opt_apply_no": "No, thanks"
    }
    if not req.message and req.selected_option_id and req.selected_option_id in OPTION_LABEL_MAP:
        req.message = OPTION_LABEL_MAP[req.selected_option_id]

    # Case 0.5: Form Filling Requests or Assistance Actions (Disabled in Deployment)
    is_fill_request = (
        req.selected_option_id == "opt_apply_yes" or
        any(phrase in req.message.lower() for phrase in [
            "can you fill", "could you fill", "will you fill", "fill out the form for me",
            "fill the form for me", "fill out this form for me", "fill this form for me",
            "fill the permit for me", "fill out the permit for me", "fill for me",
            "fill it for me", "fill out for me", "complete the form for me",
            "complete the application for me", "help me fill out", "help me apply",
            "fill out application", "fill application for me", "fill permit for me",
            "fill this application for me", "fill out the tree removal", "fill the tree removal",
            "fill tree removal", "yes, help me apply", "help me with the application"
        ])
    )
    is_apply_no = (
        req.selected_option_id == "opt_apply_no" or
        any(p in req.message.lower() for p in ["no, thanks", "no thanks", "no thank you", "no, thank you", "not now"])
    )

    if is_fill_request:
        m_lower = req.message.lower()
        packet = None
        if any(w in m_lower for w in ["tree", "arborist"]):
            packet = rag_engine.match_official_form_packet("tree removal", force=True)
            notice = (
                "CivicIQ currently provides official blank municipal applications and procedural guidance, not interactive form completion. "
                "You can download the official blank [Township of Edison Tree Removal Permit Application (PDF)](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf) "
                "to complete and submit directly to the Division of Engineering."
            )
        elif any(w in m_lower for w in ["soil import", "import soil"]):
            packet = rag_engine.match_official_form_packet("soil import", force=True)
            notice = (
                "CivicIQ currently provides official blank municipal applications and procedural guidance, not interactive form completion. "
                "You can download the official blank [Township of Edison Soil Importation Permit Application (PDF)](/api/forms/engineering/Forms_Soil_Importation_Appl.pdf) "
                "to complete and submit directly to the Division of Engineering."
            )
        elif any(w in m_lower for w in ["soil export", "export soil"]):
            packet = rag_engine.match_official_form_packet("soil export", force=True)
            notice = (
                "CivicIQ currently provides official blank municipal applications and procedural guidance, not interactive form completion. "
                "You can download the official blank [Township of Edison Soil Exportation Permit Application (PDF)](/api/forms/engineering/Forms_Soil_Exportation_App.pdf) "
                "to complete and submit directly to the Division of Engineering."
            )
        elif any(w in m_lower for w in ["road", "street"]):
            packet = rag_engine.match_official_form_packet("road opening", force=True)
            notice = (
                "CivicIQ currently provides official blank municipal applications and procedural guidance, not interactive form completion. "
                "You can download the official blank [Township of Edison Street Opening Application (PDF)](/api/forms/engineering/RoadOpenApp.pdf) "
                "to complete and submit directly to the Department of Public Works."
            )
        else:
            for msg in reversed(history):
                c = msg.get("content", "").lower()
                if "soil import" in c:
                    packet = rag_engine.match_official_form_packet("soil import", force=True)
                    notice = (
                        "CivicIQ currently provides official blank municipal applications and procedural guidance, not interactive form completion. "
                        "You can download the official blank [Township of Edison Soil Importation Permit Application (PDF)](/api/forms/engineering/Forms_Soil_Importation_Appl.pdf) "
                        "to complete and submit directly to the Division of Engineering."
                    )
                    break
                elif "soil export" in c:
                    packet = rag_engine.match_official_form_packet("soil export", force=True)
                    notice = (
                        "CivicIQ currently provides official blank municipal applications and procedural guidance, not interactive form completion. "
                        "You can download the official blank [Township of Edison Soil Exportation Permit Application (PDF)](/api/forms/engineering/Forms_Soil_Exportation_App.pdf) "
                        "to complete and submit directly to the Division of Engineering."
                    )
                    break
                elif "tree" in c:
                    packet = rag_engine.match_official_form_packet("tree removal", force=True)
                    notice = (
                        "CivicIQ currently provides official blank municipal applications and procedural guidance, not interactive form completion. "
                        "You can download the official blank [Township of Edison Tree Removal Permit Application (PDF)](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf) "
                        "to complete and submit directly to the Division of Engineering."
                    )
                    break
            else:
                notice = (
                    "CivicIQ currently provides official blank municipal applications and procedural guidance, not interactive form completion. "
                    "You can download the official blank application to complete and submit directly to the Division of Engineering."
                )

        citations = []
        if packet:
            citations.append(
                RagCitation(
                    url=packet.pdf_download_url,
                    title=packet.form_title,
                    category="Application Form",
                    department_id="engineering",
                    relevance_score=1.0,
                    excerpt=f"Official Township Application Form: {packet.form_title}. Download: {packet.pdf_download_url}",
                    visibility="public",
                    document_type="application_form",
                    service=packet.form_code,
                    verification_status="verified"
                )
            )

        user_text = req.message if req.message else "Can you fill this form for me?"
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": notice})
        CHAT_HISTORIES[req.session_id] = history[-10:]
        return ChatResponse(
            session_id=req.session_id,
            message=notice,
            mode="rag",
            form_packet=packet,
            citations=citations,
            completed=False
        )

    if is_apply_no:
        closure_msg = "No problem! Let me know if you need any other assistance with Edison Township Engineering services."
        user_text = req.message if req.message else "No, thanks"
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": closure_msg})
        CHAT_HISTORIES[req.session_id] = history[-10:]
        return ChatResponse(
            session_id=req.session_id,
            message=closure_msg,
            mode="rag",
            completed=False
        )

    # Check for volume or procedural corrections to a completed flow
    if session and session.completed:
        is_correction = any(phrase in req.message.lower() for phrase in [
            "actually", "wait", "change", "correct", "correction", "more than", "less than",
            "10 cubic", "under 10", "over 10", "5 cubic", "15 cubic", "20 cubic"
        ])
        if is_correction and session.flow_id in ["soil_import_export_flow", "tree_removal_flow"]:
            flow_engine.reset_session(req.session_id)
            session = None

    # Case 1: Active procedural flow (advanced by button option selection OR typed natural language!)
    if session and not session.completed:
        # Check if the user is asking an informational side question (e.g. "How much?", "Is there any fee?", "What about documents?", "Where do I submit it?")
        from .services.service_intent_service import service_intent_service
        intent_res = service_intent_service.detect_intent(req.message, history=history)
        if intent_res.detail_type in ["fee", "documents", "submission", "turnaround", "complete_process", "permit_required"] and not req.selected_option_id:
            svc_id = intent_res.service_id
            if svc_id == "other_engineering" and session.flow_id:
                if "tree" in session.flow_id:
                    svc_id = "tree_removal"
                elif "soil" in session.flow_id:
                    svc_id = "soil_import"
                elif "street" in session.flow_id or "road" in session.flow_id:
                    svc_id = "road_opening"
                elif "site" in session.flow_id:
                    svc_id = "site_improvement"

            detail_msg = service_intent_service.get_detail_response(svc_id, intent_res.detail_type)
            if detail_msg:
                history.append({"role": "user", "content": req.message})
                history.append({"role": "assistant", "content": detail_msg})
                CHAT_HISTORIES[req.session_id] = history[-10:]
                return ChatResponse(
                    session_id=req.session_id,
                    message=detail_msg,
                    mode="flow",
                    options=session.current_step.options if session and session.current_step else [],
                    current_step=session.current_step if session else None,
                    active_flow_id=session.flow_id if session else None,
                    department_id=session.department_id if session else "engineering",
                    completed=False
                )

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
                if form_packet:
                    citations.append(
                        RagCitation(
                            url=form_packet.pdf_download_url,
                            title=form_packet.form_title,
                            category="Application Form",
                            department_id="engineering",
                            relevance_score=1.0,
                            excerpt=f"Official Township Application Form: {form_packet.form_title}. Form Code: {form_packet.form_code}. Download: {form_packet.pdf_download_url}",
                            visibility="public",
                            document_type="application_form",
                            service=form_packet.form_code,
                            verification_status="verified"
                        )
                    )
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
    flow_match = rag_engine.detect_flow_intent(req.message, req.department_id, history=history)
    if flow_match and not form_packet and (not session or session.completed):
        dept_id, flow_id = flow_match
        success, msg, step, started_packet = flow_engine.start_flow(
            session_id=req.session_id,
            department_id=dept_id,
            flow_id=flow_id,
            initial_user_text=req.message
        )
        if success and step:
            active_sess = flow_engine.get_session(req.session_id)
            is_completed = active_sess.completed if active_sess else False
            effective_packet = started_packet
            if not effective_packet and active_sess and active_sess.current_step_id:
                flow_def = registry.get_flow(dept_id, flow_id)
                if flow_def and active_sess.current_step_id in flow_def.steps:
                    step_obj = flow_def.steps[active_sess.current_step_id]
                    if step_obj and step_obj.form_file:
                        effective_packet = flow_engine._build_form_packet(dept_id, step_obj)

            citations = []
            if effective_packet:
                citations.append(
                    RagCitation(
                        url=effective_packet.pdf_download_url,
                        title=effective_packet.form_title,
                        category="Application Form",
                        department_id="engineering",
                        relevance_score=1.0,
                        excerpt=f"Official Township Application Form: {effective_packet.form_title}. Form Code: {effective_packet.form_code}. Download: {effective_packet.pdf_download_url}",
                        visibility="public",
                        document_type="application_form",
                        service=effective_packet.form_code,
                        verification_status="verified"
                    )
                )
            history.append({"role": "user", "content": req.message})
            history.append({"role": "assistant", "content": step.message})
            return ChatResponse(
                session_id=req.session_id,
                message=step.message,
                mode="flow",
                options=step.options,
                form_packet=effective_packet,
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
    
    # Do not present application forms prematurely while clarifying procedural questions
    is_clarifying_question = "?" in final_message and any(phrase in final_message.lower() for phrase in [
        "10 cubic yards", "import or export", "impervious coverage", "ground disturbance",
        "approved permit", "urgent situation", "emergency condition", "what specific type of work"
    ])
    has_apply_or_form_intent = any(w in msg_clean for w in [
        "apply", "download", "application form", "fill out", "how do i get the form",
        "where is the application", "give me the form", "send me the form", "form packet"
    ])

    is_unconfigured_or_out_of_context = (
        "out of our context" in final_message.lower() or
        final_message.strip() == UNCONFIGURED_SERVICE_MESSAGE.strip() or
        "this service hasn't been configured yet in civiciq" in final_message.lower()
    )

    # In deployment, interactive conversational form filling is disabled.
    # Blank official applications are delivered via form_packet and citations.
    form_rec_dict = None

    # Filter citations to ensure internal documents are never exposed in ChatResponse, and deduplicate by URL
    seen_urls = set()
    safe_citations = []
    for c in (rag_res.citations or []):
        if getattr(c, "visibility", "public") == "internal":
            continue
        if "permit flow chart" in c.title.lower() or "flowchart" in getattr(c, "category", "").lower() or "permit_flow_charts" in c.url.lower():
            continue
        base_url = c.url.split("#")[0].split("?")[0]
        if base_url in seen_urls:
            continue
        seen_urls.add(base_url)
        safe_citations.append(c)

    # Record history
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": final_message})
    CHAT_HISTORIES[req.session_id] = history[-10:]

    effective_form_packet = None if is_unconfigured_or_out_of_context else (rag_res.form_packet or form_packet)

    return ChatResponse(
        session_id=req.session_id,
        message=final_message,
        mode="rag",
        citations=safe_citations,
        form_packet=effective_form_packet,
        form_recommendation=form_rec_dict,
        options=rag_res.options,
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
    if not ADMIN_API_KEY or not x_admin_key or x_admin_key != ADMIN_API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Admin access forbidden: invalid or missing X-Admin-Key header, or admin access is unconfigured."
        )

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
    raise HTTPException(
        status_code=400,
        detail="Interactive form filling is currently unavailable in this deployment. Please download and complete the official blank municipal application PDF directly."
    )

@app.post("/api/form-session/answer", response_model=FormQuestionResponse)
def answer_form_session(req: FormAnswerRequest):
    """Submits answer for the current question in an active form session."""
    raise HTTPException(
        status_code=400,
        detail="Interactive form filling is currently unavailable in this deployment."
    )

@app.post("/api/form-session/edit", response_model=FormQuestionResponse)
def edit_form_session(req: FormEditRequest):
    """Edits a previously submitted answer in an active form session."""
    raise HTTPException(
        status_code=400,
        detail="Interactive form filling is currently unavailable in this deployment."
    )

@app.get("/api/form-session/review")
def review_form_session(session_id: str = Query(...)):
    """Returns review summary of all collected information."""
    raise HTTPException(
        status_code=400,
        detail="Interactive form filling is currently unavailable in this deployment."
    )

@app.post("/api/form-session/generate-pdf")
def generate_form_pdf(session_id: str = Query(...)):
    """Generates a completed municipal draft PDF populated with resident answers."""
    raise HTTPException(
        status_code=400,
        detail="Interactive PDF draft generation is currently unavailable in this deployment. Please download and complete the official blank municipal application PDF directly."
    )

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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, reload=False)

