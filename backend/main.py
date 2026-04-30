import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

from core.ingest import IngestEngine
from core.benchmarker import Benchmarker
from config import settings
from utils.progress import progress_manager
from sse_starlette.sse import EventSourceResponse
from langchain_ollama import ChatOllama
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

# Mock data/storage paths
RAW_DIR = settings.RAW_DIR
WIKI_DIR = settings.WIKI_DIR

ingest_engine = IngestEngine(RAW_DIR, WIKI_DIR)
benchmarker = Benchmarker(RAW_DIR, WIKI_DIR)

# Initialize Ollama for chat
chat_model = ChatOllama(
    model=settings.DEFAULT_MODEL,
    base_url=settings.OLLAMA_BASE_URL
)

class WikiPage(BaseModel):
    title: str
    content: str
    metadata: Optional[dict] = None

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []

@app.get("/")
async def root():
    return {"message": "LLM Wiki API is running"}

@app.get("/progress")
async def progress():
    return EventSourceResponse(progress_manager.subscribe())

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        messages = [
            SystemMessage(content="You are a helpful assistant for the LLM Wiki. You have access to user's knowledge base. Answer concisely and accurately.")
        ]
        
        for msg in request.history:
            if msg['role'] == 'user':
                messages.append(HumanMessage(content=msg['content']))
            else:
                messages.append(SystemMessage(content=msg['content'])) # Using System for Bot for simplicity in this context
        
        messages.append(HumanMessage(content=request.message))
        
        response = await chat_model.ainvoke(messages)
        return {"response": response.content}
    except Exception as e:
        print(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/compare")
async def compare_models(file: UploadFile = File(...)):
    # Save file to RAW_DIR
    file_path = os.path.join(RAW_DIR, file.filename)
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    # Run comparison
    results = await benchmarker.compare_models(file.filename)
    
    return {"status": "success", "results": results}

@app.post("/ingest")
async def ingest_source(file: UploadFile = File(...)):
    # Save file to RAW_DIR
    file_path = os.path.join(RAW_DIR, file.filename)
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    # Trigger Ingest Engine
    wiki_file = await ingest_engine.process_file(file.filename)
    
    return {"status": "success", "filename": file.filename, "wiki_page": wiki_file, "message": "Ingestion completed"}

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

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

