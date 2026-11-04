import logging
from typing import List, Dict, Optional, Any
from ..rag_engine import rag_engine, GroundedRagEngine
from ..models.core import RagResult, RagCitation

logger = logging.getLogger("services.rag_service")

class RagService:
    """Service wrapper for Grounded Municipal RAG and Document Retrieval."""

    def __init__(self, engine: GroundedRagEngine = rag_engine):
        self.engine = engine

    def answer_question(
        self,
        query: str,
        department_id: str = "engineering",
        history: Optional[List[Dict[str, str]]] = None
    ) -> RagResult:
        return self.engine.answer_query(
            query=query,
            department_id=department_id,
            history=history
        )

rag_service = RagService()
