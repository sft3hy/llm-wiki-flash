import os
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

from core.ingest import IngestEngine
from core.benchmarker import Benchmarker
from core.lint import LintEngine
from core.llm_provider import get_llm, call_with_fallback
from config import settings, AVAILABLE_MODELS
from utils.progress import progress_manager
from sse_starlette.sse import EventSourceResponse
import logging
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger("llm-wiki")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="LLM Wiki API")

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage paths
RAW_DIR = settings.RAW_DIR
WIKI_DIR = settings.WIKI_DIR


# ─── Request/Response Models ──────────────────────────────────────────

class WikiPage(BaseModel):
    title: str
    content: str
    metadata: Optional[dict] = None

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []
    model: Optional[str] = None

class WikiEditRequest(BaseModel):
    content: str


# ─── Health ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "LLM Wiki API is running"}


# ─── Models ────────────────────────────────────────────────────────────

@app.get("/models")
async def list_models():
    """Return all available models with provider metadata."""
    return {
        "models": [m.to_dict() for m in AVAILABLE_MODELS],
        "default": settings.DEFAULT_MODEL,
        "groq_configured": bool(settings.GROQ_API_KEY),
    }


# ─── Progress SSE ─────────────────────────────────────────────────────

@app.get("/progress")
async def progress():
    return EventSourceResponse(progress_manager.subscribe())


# ─── Chat ──────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        from core.query import QueryEngine
        engine = QueryEngine(WIKI_DIR)
        
        # We no longer need to manually construct the static wiki_context
        # The qa_query method handles retrieving documents and sending them to the LLM
        result = await engine.qa_query(
            query=request.message,
            history=request.history,
            model_id=request.model
        )
        
        return {"response": result["response"], "context": result["context"]}
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Ingest ────────────────────────────────────────────────────────────

@app.post("/ingest")
async def ingest_source(
    file: UploadFile = File(...),
    model: Optional[str] = Query(None, description="Model ID to use for ingestion"),
):
    # Save file to RAW_DIR
    file_path = os.path.join(RAW_DIR, file.filename)
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    # Trigger Ingest Engine with selected model
    engine = IngestEngine(RAW_DIR, WIKI_DIR, model_id=model)
    result = await engine.process_file(file.filename)

    return {
        "status": result.get("status", "success"),
        "filename": file.filename,
        "model": engine.model_id,
        "pages_created": result.get("pages_created", []),
        "pages_updated": result.get("pages_updated", []),
        "total_pages_touched": result.get("total_pages_touched", 0),
        "message": "Ingestion completed",
    }


# ─── Raw Management ───────────────────────────────────────────────────

@app.get("/raw", response_model=List[str])
async def list_raw_sources():
    """List all raw source documents."""
    if not os.path.exists(RAW_DIR):
        return []
    return [f for f in os.listdir(RAW_DIR) if not f.startswith(".")]


@app.delete("/raw/{filename}")
async def delete_raw_source(filename: str):
    """Delete a raw source document."""
    file_path = os.path.join(RAW_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Source not found")
    
    os.remove(file_path)
    return {"status": "success", "filename": filename, "message": "Raw source deleted"}


# ─── Compare ──────────────────────────────────────────────────────────

@app.post("/compare")
async def compare_models(file: UploadFile = File(...)):
    # Save file to RAW_DIR
    file_path = os.path.join(RAW_DIR, file.filename)
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    benchmarker = Benchmarker(RAW_DIR, WIKI_DIR)
    results = await benchmarker.compare_models(file.filename)

    return {"status": "success", "results": results}


# ─── Lint ──────────────────────────────────────────────────────────────

@app.post("/lint")
async def run_lint(model: Optional[str] = Query(None)):
    """Run the wiki health check / librarian lint."""
    lint_engine = LintEngine(WIKI_DIR, model_id=model)
    results = await lint_engine.run_full_lint()
    return results


@app.post("/meditate")
async def meditate(model: Optional[str] = Query(None)):
    """
    Trigger global agentic maintenance (Karpathy-style meditation).
    Scans RAW_DIR for unprocessed files and synchronizes them.
    """
    if not os.path.exists(RAW_DIR):
        return {"status": "success", "message": "No raw files to process.", "processed": 0}

    # 1. Get list of all raw files
    raw_files = [f for f in os.listdir(RAW_DIR) if not f.startswith(".")]
    
    # 2. Get list of already processed files from log.md
    log_path = os.path.join(WIKI_DIR, "log.md")
    processed_files = set()
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            log_content = f.read()
            for raw_file in raw_files:
                if raw_file in log_content:
                    processed_files.add(raw_file)
                    
    pending_files = [f for f in raw_files if f not in processed_files]
    
    if not pending_files:
        return {"status": "success", "message": "Wiki is already up to date.", "processed": 0}
        
    # 3. Process each pending file
    engine = IngestEngine(RAW_DIR, WIKI_DIR, model_id=model)
    results = []
    for filename in pending_files:
        res = await engine.process_file(filename)
        results.append(res)
        
    return {
        "status": "success", 
        "message": f"Agentic maintenance complete. Synced {len(pending_files)} documents.",
        "processed": len(pending_files),
        "details": results
    }


@app.get("/log")
async def get_wiki_log():
    """Return the recent compilation/maintenance log."""
    log_path = os.path.join(WIKI_DIR, "log.md")
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            # Read first 1000 lines or so
            return {"content": f.read()}
    return {"content": "No log.md found. Ingest your first document to start the log."}


# ─── Wiki CRUD ─────────────────────────────────────────────────────────

@app.get("/wiki", response_model=List[str])
async def list_wiki_pages():
    if not os.path.exists(WIKI_DIR):
        return []
    return [f for f in os.listdir(WIKI_DIR) if f.endswith(".md")]


@app.get("/wiki/{filename}", response_model=WikiPage)
async def get_wiki_page(filename: str):
    file_path = os.path.join(WIKI_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Page not found")

    with open(file_path, "r") as f:
        content = f.read()

    return WikiPage(title=filename, content=content)


@app.put("/wiki/{filename}")
async def update_wiki_page(filename: str, request: WikiEditRequest):
    """Manual edit of a wiki page (human-in-the-loop)."""
    file_path = os.path.join(WIKI_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Page not found")

    with open(file_path, "w") as f:
        f.write(request.content)

    return {"status": "success", "filename": filename}


@app.delete("/wiki/{filename}")
async def delete_wiki_page(filename: str):
    """Delete a wiki page (used during merge operations)."""
    engine = IngestEngine(RAW_DIR, WIKI_DIR)
    success = engine.remove_wiki_page(filename)
    
    if not success:
        raise HTTPException(status_code=404, detail="Page not found")
        
    return {"status": "success", "filename": filename, "message": "Page deleted"}


# ─── Schema ────────────────────────────────────────────────────────────

@app.get("/schema")
async def get_schema():
    """Return the SCHEMA.md governance document."""
    schema_path = os.path.join(WIKI_DIR, "SCHEMA.md")
    if os.path.exists(schema_path):
        with open(schema_path, "r") as f:
            return {"content": f.read()}
    return {"content": "No SCHEMA.md found. One will be created on first ingestion."}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
