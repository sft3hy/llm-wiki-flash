from enum import Enum
from typing import List, Optional
import time
import logging
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.language_models.chat_models import BaseChatModel
from config import settings, MODEL_LOOKUP

logger = logging.getLogger("llm-wiki")

class TaskComplexity(Enum):
    SMALL = "llama3.2:1b"   # Fast filtering
    MEDIUM = "llama3.2:1b"  # Fast extraction
    HARD = "llama3.2:1b"    # Synthesis — local by default for reliability

def get_llm(model_id: str = None, complexity: Optional[TaskComplexity] = None) -> BaseChatModel:
    """
    Returns a LangChain chat model.
    If complexity is provided, it uses the tiered logic.
    If a Groq model is requested but fails/not available, falls back to Ollama.
    """
    # 1. Determine target model_id
    if model_id == "auto-smart":
        model_id = None

    if complexity:
        model_id = complexity.value
    else:
        model_id = model_id or settings.DEFAULT_MODEL

    model_config = MODEL_LOOKUP.get(model_id)
    if not model_config:
        # Fallback to default if unknown
        model_id = settings.DEFAULT_MODEL
        model_config = MODEL_LOOKUP.get(model_id)

    # 2. Check Groq availability/Rate limit state
    if model_config.provider == "groq" and not settings.GROQ_API_KEY:
        logger.warning(f"Groq API key missing, falling back from {model_id} to gemma4:e4b")
        return get_llm("gemma4:e4b")

    # 3. Initialize the model
    if model_config.provider == "ollama":
        # Disable Thinking and manage memory
        return ChatOllama(
            model=model_id,
            base_url=settings.OLLAMA_BASE_URL,
            stop=["</thought>", "</thinking>"],
            num_ctx=4096,
            num_predict=1024,
            temperature=0.1,
            repeat_penalty=1.15,
            timeout=60,
        )
    elif model_config.provider == "groq":
        return ChatGroq(
            model=model_id,
            api_key=settings.GROQ_API_KEY,
            max_retries=1, # Low retries to trigger fallback faster
        )
    
    return ChatOllama(model=settings.DEFAULT_MODEL, base_url=settings.OLLAMA_BASE_URL)

async def call_with_fallback(messages, task_type: str, model_id: Optional[str] = None):
    """
    Execute an LLM call with intelligent tiering and 429 fallback.
    """
    # Use task_type to get the initial model
    if model_id:
        llm = get_llm(model_id=model_id)
    else:
        llm = get_model_for_task(task_type)

    try:
        response = await llm.ainvoke(messages)
        return response.content
    except Exception as e:
        error_msg = str(e)
        # Check for Groq Rate Limit (429)
        if ("429" in error_msg or "rate_limit" in error_msg.lower()) and "groq" in error_msg.lower():
            logger.warning(f"⚠️ Groq Rate Limit hit for {task_type}. Falling back to local model.")
            # Fallback to medium local model
            fallback_llm = get_llm(complexity=TaskComplexity.MEDIUM)
            response = await fallback_llm.ainvoke(messages)
            return response.content
        
        logger.error(f"❌ LLM call failed for {task_type}: {e}")
        raise e

def get_model_for_task(task_type: str) -> BaseChatModel:
    """
    Map common tasks to model tiers.
    """
    if task_type == "filtering":
        return get_llm(complexity=TaskComplexity.SMALL)
    elif task_type in ["extraction", "relevance"]:
        return get_llm(complexity=TaskComplexity.MEDIUM)
    elif task_type == "synthesis":
        # Synthesis is hard, try Groq
        return get_llm(complexity=TaskComplexity.HARD)
    else:
        return get_llm()
