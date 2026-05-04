from typing import Optional
import logging
from langchain_ollama import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from config import settings

logger = logging.getLogger("llm-wiki")

def get_llm(model_id: Optional[str] = None) -> BaseChatModel:
    """
    Returns a LangChain ChatOllama model.
    """
    if model_id == "auto-smart" or not model_id:
        model_id = settings.DEFAULT_MODEL

    return ChatOllama(
        model=model_id,
        base_url=settings.OLLAMA_BASE_URL,
        stop=["</thought>", "</thinking>"],
        num_ctx=4096,
        num_predict=1024,
        temperature=0.1,
        repeat_penalty=1.15,
        timeout=120,
    )

async def call_with_fallback(messages, task_type: str, model_id: Optional[str] = None):
    """
    Execute an LLM call. Fallback logic removed as everything is local.
    """
    llm = get_llm(model_id=model_id)

    try:
        response = await llm.ainvoke(messages)
        return response.content
    except Exception as e:
        logger.error(f"❌ LLM call failed for {task_type}: {e}")
        raise e

