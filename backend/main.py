import os
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

from core.ingest import IngestEngine
from core.benchmarker import Benchmarker
from core.lint import LintEngine
from core.llm_provider import get_llm
from config import settings, AVAILABLE_MODELS
from utils.progress import progress_manager
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage, SystemMessage

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
        llm = get_llm(request.model)

        # Build wiki context: read index.md so the LLM knows what's available
        wiki_context = ""
        index_path = os.path.join(WIKI_DIR, "index.md")
        if os.path.exists(index_path):
            with open(index_path, "r") as f:
                wiki_context = f.read()

        messages = [
            SystemMessage(content=f"""You are a helpful assistant for the LLM Wiki knowledge base. 
You have access to the user's compiled wiki. Answer concisely and accurately.
Use [[wikilinks]] when referencing wiki pages.

Current Wiki Index:
{wiki_context}""")
        ]

        for msg in request.history:
            if msg['role'] == 'user':
                messages.append(HumanMessage(content=msg['content']))
            else:
                messages.append(SystemMessage(content=msg['content']))

        messages.append(HumanMessage(content=request.message))

        response = await llm.ainvoke(messages)
        return {"response": response.content}
    except Exception as e:
        print(f"Chat error: {e}")
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
    file_path = os.path.join(WIKI_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Page not found")

    os.remove(file_path)
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
