import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")

    RAW_DIR: str = os.getenv("RAW_DIR", "data/raw")
    WIKI_DIR: str = os.getenv("WIKI_DIR", "data/wiki")

    DEFAULT_MODEL: str = "gemma4:e4b"

    class Config:
        env_file = ".env"

settings = Settings()
