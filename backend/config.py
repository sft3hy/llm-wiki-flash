import os
from pydantic_settings import BaseSettings
from typing import List, Dict


class ModelConfig:
    """Metadata for a supported LLM model."""
    def __init__(self, model_id: str, display_name: str, provider: str, description: str = ""):
        self.model_id = model_id
        self.display_name = display_name
        self.provider = provider  # "ollama" or "groq"
        self.description = description

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "display_name": self.display_name,
            "provider": self.provider,
            "description": self.description,
        }


# All supported models
AVAILABLE_MODELS: List[ModelConfig] = [
    ModelConfig(
        model_id="auto-smart",
        display_name="Smart (Auto Tiering)",
        provider="system",
        description="Automatically selects the best model for each task (Gemma for small, Groq for hard)"
    ),
    ModelConfig(
        model_id="llama3.2:1b",
        display_name="Llama 3.2 1B (Fast)",
        provider="ollama",
        description="Meta's Llama 3.2 — ultra-fast for local filtering and extraction"
    ),
    ModelConfig(
        model_id="gemma4:e4b",
        display_name="Gemma 4 Medium",
        provider="ollama",
        description="Google's Gemma 4 — balanced quality and speed"
    ),
    ModelConfig(
        model_id="llama-3.3-70b-versatile",
        display_name="Llama 3.3 70B",
        provider="groq",
        description="Meta's Llama 3.3 70B — versatile cloud model via Groq"
    ),
    ModelConfig(
        model_id="openai/gpt-oss-120b",
        display_name="GPT-OSS 120B",
        provider="groq",
        description="OpenAI GPT-OSS 120B — large-scale cloud model via Groq"
    ),
    ModelConfig(
        model_id="meta-llama/llama-4-scout-17b-16e-instruct",
        display_name="Llama 4 Scout 17B",
        provider="groq",
        description="Meta's Llama 4 Scout — efficient cloud model via Groq"
    ),
]

MODEL_LOOKUP: Dict[str, ModelConfig] = {m.model_id: m for m in AVAILABLE_MODELS}


class Settings(BaseSettings):
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    RAW_DIR: str = os.getenv("RAW_DIR", "data/raw")
    WIKI_DIR: str = os.getenv("WIKI_DIR", "data/wiki")

    DEFAULT_MODEL: str = "llama3.2:1b"

    class Config:
        env_file = ".env"


settings = Settings()
