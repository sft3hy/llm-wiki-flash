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
from config import settings
import urllib.request
import json
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
    document: Optional[str] = None

class WikiEditRequest(BaseModel):
    content: str

class VaultIngestRequest(BaseModel):
    path: str
    topic: str
    model: Optional[str] = None


# ─── Health ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "LLM Wiki API is running"}


# ─── Models ────────────────────────────────────────────────────────────

@app.get("/models")
async def list_models():
    """Return all available models from Ollama."""
    try:
        req = urllib.request.Request(f"{settings.OLLAMA_BASE_URL}/api/tags")
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())
            models = []
            for m in data.get("models", []):
                if "nomic-embed" in m["name"].lower():
                    continue
                models.append({
                    "model_id": m["name"],
                    "display_name": m["name"],
                    "provider": "ollama",
                    "description": f"Local Ollama model: {m['name']}"
                })
    except Exception as e:
        logger.warning(f"Could not fetch models from Ollama: {e}")
        # Fallback to defaults if Ollama is unreachable
        models = [
            {"model_id": "gemma4:e4b", "display_name": "Gemma 4 Medium", "provider": "ollama", "description": "Google's Gemma 4"},
            {"model_id": "llama3.2:1b", "display_name": "Llama 3.2 1B (Fast)", "provider": "ollama", "description": "Meta's Llama 3.2"},
        ]
        
    return {
        "models": models,
        "default": settings.DEFAULT_MODEL,
        "groq_configured": False,
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
            model_id=request.model,
            document=request.document
        )
        
        return {"response": result["response"], "context": result["context"]}
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Ingest ────────────────────────────────────────────────────────────

@app.post("/ingest")
async def ingest_source(
    files: List[UploadFile] = File(...),
    topic: str = Query(..., description="Topic of the corpus"),
    model: Optional[str] = Query(None, description="Model ID to use for ingestion"),
):
    documents = []
    os.makedirs(RAW_DIR, exist_ok=True)
    
    for file in files:
        # Save file to RAW_DIR temporarily (optional, but good for raw backup)
        file_path = os.path.join(RAW_DIR, file.filename)
        content_bytes = await file.read()
        
        try:
            content_str = content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            # Skip binary files if any slipped through
            continue

        with open(file_path, "wb") as f:
            f.write(content_bytes)

        documents.append({
            "filename": file.filename,
            "content": content_str,
            "source_type": "upload"
        })

    if not documents:
        raise HTTPException(status_code=400, detail="No readable text files uploaded.")

    # Trigger Ingest Engine with selected model
    engine = IngestEngine(RAW_DIR, WIKI_DIR, model_id=model)
    result = await engine.process_corpus(topic, documents)

    return result

@app.post("/ingest/vault")
async def ingest_vault(request: VaultIngestRequest):
    # Strip quotes if they were pasted in
    clean_path = request.path.strip().strip("'").strip('"')
    vault_path = os.path.abspath(clean_path)
    
    if not os.path.exists(vault_path) or not os.path.isdir(vault_path):
        logger.error(f"Vault path does not exist or is not a directory: {vault_path}")
        raise HTTPException(status_code=400, detail=f"Invalid vault path: {vault_path}. Ensure it is an absolute path and accessible by the backend.")

    documents = []
    # Recursively scan for markdown files
    for root_dir, _, files in os.walk(vault_path):
        for file in files:
            if file.endswith(('.md', '.txt')):
                full_path = os.path.join(root_dir, file)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content_str = f.read()
                    
                    documents.append({
                        "filename": os.path.relpath(full_path, vault_path).replace('/', '-'),
                        "content": content_str,
                        "source_type": "vault"
                    })
                except Exception as e:
                    logger.warning(f"Failed to read vault file {full_path}: {e}")

    if not documents:
        logger.error(f"No readable markdown/text files found in vault path: {vault_path}")
        raise HTTPException(status_code=400, detail=f"No readable markdown/text files found in vault: {vault_path}")

    engine = IngestEngine(RAW_DIR, WIKI_DIR, model_id=request.model)
    result = await engine.process_corpus(request.topic, documents)

    return result


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
        
    # 3. Read pending files and process as a corpus
    engine = IngestEngine(RAW_DIR, WIKI_DIR, model_id=model)
    documents = []
    for filename in pending_files:
        file_path = os.path.join(RAW_DIR, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content_str = f.read()
            documents.append({
                "filename": filename,
                "content": content_str,
                "source_type": "maintenance"
            })
        except Exception as e:
            logger.warning(f"Could not read pending file {filename}: {e}")

    if not documents:
        return {"status": "success", "message": "No readable pending files found.", "processed": 0}

    result = await engine.process_corpus("Maintenance Update", documents)
        
    return {
        "status": "success", 
        "message": f"Agentic maintenance complete. Synced {len(pending_files)} documents.",
        "processed": len(pending_files),
        "details": result
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
