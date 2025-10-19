from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uvicorn
import logging

# Import your orchestrator invoke function
from orchestrator import invoke

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Multi-Agent Research Orchestrator API",
    description="API for orchestrating multi-agent research workflow",
    version="1.0.0",
)

# Enable CORS for Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your Streamlit URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    """Request model for research queries"""

    user_query: str
    session_id: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "user_query": "What are the latest advancements in quantum computing?",
                "session_id": "session-123",
            }
        }


class QueryResponse(BaseModel):
    """Response model for research results"""

    response: str
    status: str
    session_id: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    phase: Optional[str] = None


@app.get("/")
def read_root():
    """Root endpoint"""
    return {
        "message": "Multi-Agent Research Orchestrator API",
        "status": "running",
        "endpoints": {"health": "/health", "query": "/query (POST)"},
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "research-orchestrator"}


@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Process a research query through the multi-agent orchestrator

    This endpoint:
    1. Receives a research query
    2. Passes it through the orchestrator (Planner → Searcher → Analyzer → Critique → Reporter)
    3. Returns the final research report
    """
    try:
        logger.info(f"Received query: {request.user_query[:100]}...")

        # Prepare payload for orchestrator
        payload = {"user_query": request.user_query}

        # Call the orchestrator's invoke function
        result = invoke(payload)

        # Extract response text from AgentResult
        # The result.message is a Message object with content blocks
        response_text = ""
        if hasattr(result, "message") and result.message:
            # Extract text from message content
            if isinstance(result.message, dict):
                content = result.message.get("content", [])
                if isinstance(content, list):
                    # Concatenate all text blocks
                    response_text = "\n".join(
                        block.get("text", "")
                        for block in content
                        if isinstance(block, dict) and "text" in block
                    )
                else:
                    response_text = str(content)
            else:
                # Use the __str__ method if available
                response_text = str(result)

        if not response_text:
            response_text = "No response generated from orchestrator"

        # Extract metrics if available
        metrics = None
        if hasattr(result, "metrics"):
            try:
                metrics = result.metrics.get_summary()
                # Convert to dict if it's a string
                if isinstance(metrics, str):
                    metrics = {"summary": metrics}
            except Exception as e:
                logger.warning(f"Could not extract metrics: {e}")
                metrics = None

        # Extract phase from state if available
        phase = None
        if hasattr(result, "state"):
            phase = result.state.get("phase", "COMPLETE")

        logger.info("Query processed successfully")

        return QueryResponse(
            response=response_text,
            status="success",
            session_id=request.session_id,
            metrics=metrics,
            phase=phase,
        )

    except Exception as e:
        logger.error(f"Error processing query: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail={"error": str(e), "type": type(e).__name__}
        )


@app.get("/status")
def get_status():
    """Get orchestrator status information"""
    return {
        "orchestrator": "operational",
        "agents": ["Planner", "Searcher", "Analyzer", "Critique", "Reporter"],
        "workflow": "Planning → Search → Analysis → Critique → Reporting",
    }


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Starting Multi-Agent Research Orchestrator API")
    print("=" * 60)
    print("\nAPI will be available at:")
    print("  - http://localhost:8000")
    print("  - API docs: http://localhost:8000/docs")
    print("  - Health check: http://localhost:8000/health")
    print("\n" + "=" * 60 + "\n")

    uvicorn.run(
        "middleware:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Auto-reload on code changes
        log_level="info",
    )
