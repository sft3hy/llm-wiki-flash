import os
import errno
import subprocess
from pathlib import Path
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
from wiki_builder.chat import chat_with_topic
from wiki_builder.config import GenericJSONSearchConfig, PipelineConfig, SearxngConfig
from wiki_builder.pipeline import PipelineRunner
import chat_db
import uuid
import datetime
from wiki_registry import WikiRegistry

chat_db.init_db()

logger = logging.getLogger("llm-wiki")
logging.basicConfig(level=logging.INFO)

OLLAMA_UTILITY_PATTERNS = (
    "embed",
    "embedding",
    "rerank",
    "bge-",
    "e5-",
    "gte-",
    "jina-embeddings",
    "all-minilm",
)

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
WIKIS_DIR = settings.WIKIS_DIR
CANONICAL_SCHEMA_PATH = Path(WIKI_DIR) / "SCHEMA.md"
wiki_registry = WikiRegistry(
    Path(WIKIS_DIR),
    Path(RAW_DIR),
    Path(WIKI_DIR),
    canonical_schema_path=CANONICAL_SCHEMA_PATH,
    legacy_index_template_path=Path(WIKI_DIR) / "index.md",
    legacy_log_template_path=Path("data/wiki-OLD") / "log.md",
)


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
    wiki_id: Optional[str] = None

class WikiEditRequest(BaseModel):
    content: str

class VaultIngestRequest(BaseModel):
    path: str
    topic: str
    model: Optional[str] = None
    wiki_id: Optional[str] = None

class WikiCreateRequest(BaseModel):
    name: str

class WikiUpdateRequest(BaseModel):
    name: str

class BuilderRunRequest(BaseModel):
    topic: str
    wiki_id: Optional[str] = None
    wiki_name: Optional[str] = None
    vault_path: Optional[str] = None
    model: Optional[str] = None
    searxng_url: Optional[str] = None
    search_api_url: Optional[str] = None
    results_per_query: int = 5
    source_limit: int = 15

class BuilderChatRequest(BaseModel):
    topic: str
    wiki_id: str
    message: str
    history: Optional[List[dict]] = []
    model: Optional[str] = None
    document: Optional[str] = None
    document_kind: Optional[str] = None


def _clean_user_path(path: str) -> Path:
    clean_path = path.strip().strip("'").strip('"')
    return Path(clean_path).expanduser().resolve()


def _resolve_builder_paths(wiki_id: str) -> dict:
    paths = wiki_registry.get_paths(wiki_id)
    return {
        "topic_slug": wiki_id,
        "topic_root": paths.root_dir,
        "sources_dir": paths.sources_dir,
        "wiki_dir": paths.wiki_dir,
        "raw_dir": paths.sources_dir,
        "embeddings_dir": paths.embeddings_dir,
        "log_path": paths.log_file,
    }


def _extract_markdown_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _resolve_searxng_url(candidate_url: str | None) -> str | None:
    if not candidate_url:
        return settings.SEARXNG_URL
    normalized = candidate_url.rstrip("/")
    if normalized in ("http://localhost:8080", "http://127.0.0.1:8080"):
        return settings.SEARXNG_URL
    return candidate_url


def _get_wiki_paths(wiki_id: str | None):
    resolved = wiki_registry.resolve_wiki_id(wiki_id)
    return resolved, wiki_registry.get_paths(resolved)


def _is_chat_model(model_name: str) -> bool:
    lowered = model_name.lower()
    return not any(pattern in lowered for pattern in OLLAMA_UTILITY_PATTERNS)


def _sort_models(models: list[dict]) -> list[dict]:
    return sorted(
        models,
        key=lambda model: (
            0 if model["model_id"] == settings.DEFAULT_MODEL else 1,
            model["display_name"].lower(),
        ),
    )


def _discover_models_from_ollama_list() -> list[dict]:
    result = subprocess.run(
        ["ollama", "list"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    models: list[dict] = []
    for raw_line in result.stdout.splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        name = line.split()[0]
        if not _is_chat_model(name):
            continue
        models.append(
            {
                "model_id": name,
                "display_name": name,
                "provider": "ollama",
                "description": f"Local Ollama chat model: {name}",
            }
        )
    return _sort_models(models)


def _discover_models_from_ollama_api() -> list[dict]:
    req = urllib.request.Request(f"{settings.OLLAMA_BASE_URL}/api/tags")
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read())
    models = []
    for model in data.get("models", []):
        name = model.get("name", "")
        if not name or not _is_chat_model(name):
            continue
        models.append(
            {
                "model_id": name,
                "display_name": name,
                "provider": "ollama",
                "description": f"Local Ollama chat model: {name}",
            }
        )
    return _sort_models(models)


# ─── Health ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "LLM Wiki API is running"}


# ─── Models ────────────────────────────────────────────────────────────

@app.get("/models")
async def list_models():
    """Return currently installed Ollama chat models."""
    try:
        models = _discover_models_from_ollama_list()
    except Exception as e:
        logger.warning(f"Could not read models from `ollama list`: {e}")
        try:
            models = _discover_models_from_ollama_api()
        except Exception as api_error:
            logger.warning(f"Could not fetch models from Ollama API: {api_error}")
            models = []
        
    return {
        "models": models,
        "default": settings.DEFAULT_MODEL,
        "groq_configured": False,
    }


# ─── Progress SSE ─────────────────────────────────────────────────────

@app.get("/progress")
async def progress():
    return EventSourceResponse(progress_manager.subscribe())


# ─── Wiki Registry ────────────────────────────────────────────────────

@app.get("/wikis")
async def list_wikis():
    return {
        "wikis": wiki_registry.list_wikis(),
        "default_wiki_id": wiki_registry.default_wiki_id(),
    }


@app.post("/wikis")
async def create_wiki(request: WikiCreateRequest):
    try:
        return wiki_registry.create_wiki(request.name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.get("/wikis/{wiki_id}")
async def get_wiki(wiki_id: str):
    try:
        return wiki_registry.load_wiki(wiki_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Wiki not found")


@app.put("/wikis/{wiki_id}")
async def rename_wiki(wiki_id: str, request: WikiUpdateRequest):
    try:
        return wiki_registry.rename_wiki(wiki_id, request.name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Wiki not found")


@app.delete("/wikis/{wiki_id}")
async def delete_wiki(wiki_id: str):
    try:
        wiki_registry.delete_wiki(wiki_id)
        return {"status": "success", "wiki_id": wiki_id}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Wiki not found")


@app.post("/wikis/{wiki_id}/rebuild-embeddings")
async def rebuild_wiki_embeddings(wiki_id: str):
    try:
        return wiki_registry.rebuild_embeddings(wiki_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Wiki not found")


@app.post("/wikis/{wiki_id}/reindex")
async def reindex_wiki(wiki_id: str, model: Optional[str] = Query(None)):
    try:
        resolved_wiki_id, paths = _get_wiki_paths(wiki_id)
        if not paths.sources_dir.exists():
            return {
                "status": "success",
                "wiki_id": resolved_wiki_id,
                "processed": 0,
                "message": "No source documents found to re-index.",
            }

        documents = []
        for file_path in sorted(paths.sources_dir.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.suffix not in {".md", ".txt", ".html"}:
                continue
            if "__metadata" in file_path.name or "__raw" in file_path.name:
                continue
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                continue
            documents.append(
                {
                    "filename": file_path.name,
                    "content": content,
                    "source_type": "reindex",
                }
            )

        if not documents:
            return {
                "status": "success",
                "wiki_id": resolved_wiki_id,
                "processed": 0,
                "message": "No readable source documents found to re-index.",
            }

        wiki_info = wiki_registry.load_wiki(resolved_wiki_id)
        engine = IngestEngine(
            str(paths.sources_dir),
            str(paths.wiki_dir),
            model_id=model,
            embeddings_dir=str(paths.embeddings_dir),
        )
        result = await engine.process_corpus(f"Reindex {wiki_info['name']}", documents)
        wiki_registry.update_models(resolved_wiki_id, {"reindex": model or settings.DEFAULT_MODEL})
        wiki_registry.touch(resolved_wiki_id)
        return {
            "status": "success",
            "wiki_id": resolved_wiki_id,
            "processed": len(documents),
            "message": f"Re-indexed {len(documents)} source documents.",
            "details": result,
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Wiki not found")


@app.get("/wikis/{wiki_id}/validate")
async def validate_wiki(wiki_id: str):
    try:
        return wiki_registry.validate_wiki(wiki_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Wiki not found")


# ─── Wiki Builder ─────────────────────────────────────────────────────

@app.post("/builder/run")
async def run_wiki_builder(request: BuilderRunRequest):
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required.")
    if request.wiki_id:
        try:
            selected_wiki = wiki_registry.load_wiki(request.wiki_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Wiki not found.")
    else:
        selected_wiki = wiki_registry.create_wiki(request.wiki_name or topic)
    selected_wiki_id = selected_wiki["wiki_id"]

    resolved_searxng_url = _resolve_searxng_url(request.searxng_url)

    if not resolved_searxng_url and not request.search_api_url:
        raise HTTPException(status_code=400, detail="Provide either a SearXNG URL or a fallback search API URL.")

    searxng = SearxngConfig(base_url=resolved_searxng_url) if resolved_searxng_url else None
    fallback_search = GenericJSONSearchConfig(endpoint=request.search_api_url) if request.search_api_url else None

    progress_manager.broadcast(
        f"Preparing local research pipeline for {topic}",
        2,
        "processing",
        channel="wiki_builder",
        stage="search",
        topic=topic,
        wiki_id=selected_wiki_id,
    )

    def builder_progress(stage: str, message: str, progress: int, status: str = "processing", **context):
        payload = {"channel": "wiki_builder", "stage": stage, "topic": topic, "wiki_id": selected_wiki_id, **context}
        progress_manager.broadcast(
            message,
            progress,
            status,
            **payload,
        )

    try:
        config = PipelineConfig(
            vault_path=Path(WIKIS_DIR).resolve(),
            workspace_id=selected_wiki_id,
            model_id=request.model or settings.DEFAULT_MODEL,
            data_root=Path(WIKIS_DIR).resolve(),
            logs_dir=Path(WIKIS_DIR).resolve(),
            searxng=searxng,
            fallback_search=fallback_search,
            results_per_query=request.results_per_query,
            source_limit=request.source_limit,
        )
        result = PipelineRunner(config, progress_callback=builder_progress).run_pipeline(topic)
        wiki_registry.rebuild_embeddings(selected_wiki_id)
        wiki_registry.touch(selected_wiki_id)
        response = result.to_dict()
        response["wiki_id"] = selected_wiki_id
        response["wiki_name"] = selected_wiki["name"]
        return response
    except OSError as error:
        logger.error(f"Wiki builder filesystem error: {error}")
        if error.errno in (errno.EROFS, errno.EACCES, errno.EPERM):
            detail = (
                f"Wiki storage for '{selected_wiki_id}' is not writable from the backend container."
            )
            progress_manager.broadcast(
                detail,
                100,
                "error",
                channel="wiki_builder",
                stage="error",
                topic=topic,
                wiki_id=selected_wiki_id,
                error=detail,
            )
            raise HTTPException(status_code=400, detail=detail)
        raise HTTPException(status_code=500, detail=str(error))
    except Exception as error:
        logger.error(f"Wiki builder failed: {error}")
        progress_manager.broadcast(
            f"Wiki builder failed: {error}",
            100,
            "error",
            channel="wiki_builder",
            stage="error",
            topic=topic,
            wiki_id=selected_wiki_id,
            error=str(error),
        )
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/builder/topic")
async def get_builder_topic(wiki_id: str = Query(...)):
    try:
        wiki_info = wiki_registry.load_wiki(wiki_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Built topic not found.")
    paths = _resolve_builder_paths(wiki_id)

    sources_manifest_path = paths["raw_dir"] / "sources.json"
    source_manifest = []
    if sources_manifest_path.exists():
        with open(sources_manifest_path, "r", encoding="utf-8") as handle:
            source_manifest = json.load(handle)

    wiki_pages = []
    if paths["wiki_dir"].exists():
        for file_name in sorted(os.listdir(paths["wiki_dir"])):
            if not file_name.endswith(".md"):
                continue
            file_path = paths["wiki_dir"] / file_name
            with open(file_path, "r", encoding="utf-8") as handle:
                content = handle.read()
            wiki_pages.append(
                {
                    "name": file_name,
                    "title": _extract_markdown_title(content, file_name.replace(".md", "").replace("-", " ").title()),
                }
            )

    source_notes = []
    for item in source_manifest:
        source_notes.append(
            {
                "name": f"{item['source_id']}.md",
                "title": item.get("title", item["source_id"]),
                "url": item.get("url"),
                "snippet": item.get("snippet", ""),
                "retrieved_at": item.get("retrieval_timestamp"),
                "last_updated": item.get("last_updated"),
            }
        )
    if not source_notes:
        source_notes = wiki_info.get("sources", [])

    return {
        "topic": wiki_info["name"],
        "wiki_id": wiki_id,
        "topic_slug": paths["topic_slug"],
        "raw_sources_dir": str(paths["raw_dir"]),
        "sources_dir": str(paths["sources_dir"]),
        "wiki_dir": str(paths["wiki_dir"]),
        "log_path": str(paths["log_path"]),
        "source_notes": source_notes,
        "wiki_pages": wiki_pages,
    }


@app.get("/builder/content")
async def get_builder_content(
    wiki_id: str = Query(...),
    kind: str = Query(..., pattern="^(wiki|source|log)$"),
    name: str = Query(...),
):
    paths = _resolve_builder_paths(wiki_id)

    safe_name = os.path.basename(name)
    if safe_name != name:
        raise HTTPException(status_code=400, detail="Invalid file name.")

    if kind == "wiki":
        file_path = paths["wiki_dir"] / safe_name
    elif kind == "source":
        file_path = paths["sources_dir"] / safe_name
    else:
        file_path = paths["log_path"]

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Requested content not found.")

    with open(file_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    return {
        "name": safe_name,
        "kind": kind,
        "content": content,
    }


@app.post("/builder/chat")
async def builder_chat(request: BuilderChatRequest):
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required.")
    paths = _resolve_builder_paths(request.wiki_id)
    if not paths["topic_root"].exists():
        raise HTTPException(status_code=404, detail="Built topic not found.")

    try:
        result = await chat_with_topic(
            vault_path=Path(WIKIS_DIR).resolve(),
            topic=topic,
            wiki_id=request.wiki_id,
            message=request.message,
            history=request.history,
            model_id=request.model,
            document_name=request.document,
            document_kind=request.document_kind,
        )
        return result
    except Exception as error:
        logger.error(f"Wiki builder chat failed: {error}")
        raise HTTPException(status_code=500, detail=str(error))


# ─── Chat ──────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        from core.query import QueryEngine
        resolved_wiki_id, paths = _get_wiki_paths(request.wiki_id)
        if not paths.embeddings_dir.exists() or not any(paths.embeddings_dir.iterdir()):
            wiki_registry.rebuild_embeddings(resolved_wiki_id)
        engine = QueryEngine(str(paths.wiki_dir), embeddings_dir=str(paths.embeddings_dir))
        
        # We no longer need to manually construct the static wiki_context
        # The qa_query method handles retrieving documents and sending them to the LLM
        result = await engine.qa_query(
            query=request.message,
            history=request.history,
            model_id=request.model,
            document=request.document
        )
        
        wiki_info = wiki_registry.load_wiki(resolved_wiki_id)
        
        # Save messages to database
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        user_msg_id = uuid.uuid4().hex
        bot_msg_id = uuid.uuid4().hex
        
        chat_db.save_message(user_msg_id, resolved_wiki_id, request.message, "user", timestamp)
        chat_db.save_message(bot_msg_id, resolved_wiki_id, result["response"], "bot", timestamp, request.model, result.get("context"))

        return {"response": result["response"], "context": result["context"], "wiki_id": resolved_wiki_id, "wiki_name": wiki_info["name"]}
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/{wiki_id}")
async def get_chat_history_endpoint(wiki_id: str):
    try:
        resolved_wiki_id, _ = _get_wiki_paths(wiki_id)
        history = chat_db.get_chat_history(resolved_wiki_id)
        return {"history": history}
    except Exception as e:
        logger.error(f"Failed to fetch chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Ingest ────────────────────────────────────────────────────────────

@app.post("/ingest")
async def ingest_source(
    files: List[UploadFile] = File(...),
    topic: str = Query(..., description="Topic of the corpus"),
    model: Optional[str] = Query(None, description="Model ID to use for ingestion"),
    wiki_id: Optional[str] = Query(None, description="Target wiki ID"),
):
    documents = []
    resolved_wiki_id, paths = _get_wiki_paths(wiki_id)
    os.makedirs(paths.sources_dir, exist_ok=True)
    
    for file in files:
        # Save file to RAW_DIR temporarily (optional, but good for raw backup)
        file_path = os.path.join(str(paths.sources_dir), file.filename)
        content_bytes = await file.read()
        
        try:
            content_str = content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            # Skip binary files if any slipped through
            continue

        os.makedirs(os.path.dirname(file_path), exist_ok=True)
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
    engine = IngestEngine(str(paths.sources_dir), str(paths.wiki_dir), model_id=model, embeddings_dir=str(paths.embeddings_dir))
    result = await engine.process_corpus(topic, documents)
    wiki_registry.update_models(resolved_wiki_id, {"ingest": model or settings.DEFAULT_MODEL})
    wiki_registry.touch(resolved_wiki_id)
    result["wiki_id"] = resolved_wiki_id

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

    resolved_wiki_id, paths = _get_wiki_paths(request.wiki_id)
    engine = IngestEngine(str(paths.sources_dir), str(paths.wiki_dir), model_id=request.model, embeddings_dir=str(paths.embeddings_dir))
    result = await engine.process_corpus(request.topic, documents)
    wiki_registry.update_models(resolved_wiki_id, {"ingest": request.model or settings.DEFAULT_MODEL})
    wiki_registry.touch(resolved_wiki_id)
    result["wiki_id"] = resolved_wiki_id

    return result


# ─── Raw Management ───────────────────────────────────────────────────

@app.get("/raw", response_model=List[str])
async def list_raw_sources(wiki_id: Optional[str] = Query(None)):
    """List all raw source documents."""
    _resolved_wiki_id, paths = _get_wiki_paths(wiki_id)
    if not os.path.exists(paths.sources_dir):
        return []
    return [f for f in os.listdir(paths.sources_dir) if not f.startswith(".")]


@app.delete("/raw/{filename}")
async def delete_raw_source(filename: str, wiki_id: Optional[str] = Query(None)):
    """Delete a raw source document."""
    resolved_wiki_id, paths = _get_wiki_paths(wiki_id)
    file_path = os.path.join(str(paths.sources_dir), filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Source not found")
    
    os.remove(file_path)
    wiki_registry.touch(resolved_wiki_id)
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
async def run_lint(model: Optional[str] = Query(None), wiki_id: Optional[str] = Query(None)):
    """Run the wiki health check / librarian lint."""
    _resolved_wiki_id, paths = _get_wiki_paths(wiki_id)
    lint_engine = LintEngine(str(paths.wiki_dir), model_id=model)
    results = await lint_engine.run_full_lint()
    return results


@app.post("/meditate")
async def meditate(model: Optional[str] = Query(None), wiki_id: Optional[str] = Query(None)):
    """
    Trigger global agentic maintenance (Karpathy-style meditation).
    Scans RAW_DIR for unprocessed files and synchronizes them.
    """
    resolved_wiki_id, paths = _get_wiki_paths(wiki_id)
    if not os.path.exists(paths.sources_dir):
        return {"status": "success", "message": "No raw files to process.", "processed": 0}

    # 1. Get list of all raw files
    raw_files = [
        f for f in os.listdir(paths.sources_dir)
        if not f.startswith(".") and f.endswith((".md", ".txt")) and "__metadata" not in f and "__raw" not in f
    ]
    
    # 2. Get list of already processed files from log.md
    log_path = os.path.join(str(paths.wiki_dir), "log.md")
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
    engine = IngestEngine(str(paths.sources_dir), str(paths.wiki_dir), model_id=model, embeddings_dir=str(paths.embeddings_dir))
    documents = []
    for filename in pending_files:
        file_path = os.path.join(str(paths.sources_dir), filename)
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
    wiki_registry.update_models(resolved_wiki_id, {"maintenance": model or settings.DEFAULT_MODEL})
    wiki_registry.touch(resolved_wiki_id)
        
    return {
        "status": "success", 
        "message": f"Agentic maintenance complete. Synced {len(pending_files)} documents.",
        "processed": len(pending_files),
        "details": result,
        "wiki_id": resolved_wiki_id,
    }


@app.get("/log")
async def get_wiki_log(wiki_id: Optional[str] = Query(None)):
    """Return the recent compilation/maintenance log."""
    _resolved_wiki_id, paths = _get_wiki_paths(wiki_id)
    log_path = os.path.join(str(paths.wiki_dir), "log.md")
    pipeline_log = str(paths.log_file)
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            # Read first 1000 lines or so
            return {"content": f.read()}
    if os.path.exists(pipeline_log):
        with open(pipeline_log, "r") as f:
            return {"content": f.read()}
    return {"content": "No log.md found. Ingest your first document to start the log."}


# ─── Wiki CRUD ─────────────────────────────────────────────────────────

@app.get("/wiki", response_model=List[str])
async def list_wiki_pages(wiki_id: Optional[str] = Query(None)):
    _resolved_wiki_id, paths = _get_wiki_paths(wiki_id)
    if not os.path.exists(paths.wiki_dir):
        return []
    return [f for f in os.listdir(paths.wiki_dir) if f.endswith(".md")]


@app.get("/wiki/{filename}", response_model=WikiPage)
async def get_wiki_page(filename: str, wiki_id: Optional[str] = Query(None)):
    _resolved_wiki_id, paths = _get_wiki_paths(wiki_id)
    file_path = os.path.join(str(paths.wiki_dir), filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Page not found")

    with open(file_path, "r") as f:
        content = f.read()

    return WikiPage(title=filename, content=content)


@app.put("/wiki/{filename}")
async def update_wiki_page(filename: str, request: WikiEditRequest, wiki_id: Optional[str] = Query(None)):
    """Manual edit of a wiki page (human-in-the-loop)."""
    resolved_wiki_id, paths = _get_wiki_paths(wiki_id)
    file_path = os.path.join(str(paths.wiki_dir), filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Page not found")

    with open(file_path, "w") as f:
        f.write(request.content)
    wiki_registry.rebuild_embeddings(resolved_wiki_id)
    wiki_registry.touch(resolved_wiki_id)

    return {"status": "success", "filename": filename}


@app.delete("/wiki/{filename}")
async def delete_wiki_page(filename: str, wiki_id: Optional[str] = Query(None)):
    """Delete a wiki page (used during merge operations)."""
    resolved_wiki_id, paths = _get_wiki_paths(wiki_id)
    engine = IngestEngine(str(paths.sources_dir), str(paths.wiki_dir), embeddings_dir=str(paths.embeddings_dir))
    success = engine.remove_wiki_page(filename)
    
    if not success:
        raise HTTPException(status_code=404, detail="Page not found")
    wiki_registry.touch(resolved_wiki_id)
        
    return {"status": "success", "filename": filename, "message": "Page deleted"}


# ─── Schema ────────────────────────────────────────────────────────────

@app.get("/schema")
async def get_schema(wiki_id: Optional[str] = Query(None)):
    """Return the SCHEMA.md governance document."""
    _resolved_wiki_id, paths = _get_wiki_paths(wiki_id)
    schema_path = os.path.join(str(paths.wiki_dir), "SCHEMA.md")
    if os.path.exists(schema_path):
        with open(schema_path, "r") as f:
            return {"content": f.read()}
    if CANONICAL_SCHEMA_PATH.exists():
        with CANONICAL_SCHEMA_PATH.open("r", encoding="utf-8") as f:
            return {"content": f.read()}
    return {"content": "No SCHEMA.md found. Please restore the canonical schema at data/wiki/SCHEMA.md."}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
