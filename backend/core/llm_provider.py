"""
LLM Provider Factory
Routes model requests to the correct backend (Ollama for local, Groq for cloud).
"""

from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from config import settings, MODEL_LOOKUP


def get_llm(model_id: str = None):
    """
    Returns a LangChain chat model for the given model_id.
    Falls back to DEFAULT_MODEL if not specified.
    """
    model_id = model_id or settings.DEFAULT_MODEL
    model_config = MODEL_LOOKUP.get(model_id)

    if not model_config:
        raise ValueError(
            f"Unknown model '{model_id}'. "
            f"Available: {list(MODEL_LOOKUP.keys())}"
        )

    if model_config.provider == "ollama":
        return ChatOllama(
            model=model_id,
            base_url=settings.OLLAMA_BASE_URL,
        )
    elif model_config.provider == "groq":
        if not settings.GROQ_API_KEY:
            raise ValueError(
                f"GROQ_API_KEY is required for cloud model '{model_id}'. "
                "Set it in your .env file or environment variables."
            )
        return ChatGroq(
            model=model_id,
            api_key=settings.GROQ_API_KEY,
        )
    else:
        raise ValueError(f"Unknown provider '{model_config.provider}' for model '{model_id}'")
