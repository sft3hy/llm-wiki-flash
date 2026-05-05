from __future__ import annotations

import asyncio
import json
import logging
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from config import settings

logger = logging.getLogger("llm-wiki")

STOP_TOKENS = ["</thought>", "</thinking>"]
ASYNC_LLM_SEMAPHORE = asyncio.Semaphore(1)
SYNC_LLM_LOCK = threading.Lock()


@dataclass
class SimpleLLMResponse:
    content: str


def _resolve_model_id(model_id: Optional[str]) -> str:
    if model_id == "auto-smart" or not model_id:
        return settings.DEFAULT_MODEL
    return model_id


def _message_role(message: Any) -> str:
    role = getattr(message, "type", None) or getattr(message, "role", None) or "user"
    if role in {"system", "human", "ai", "assistant", "user"}:
        return "assistant" if role == "ai" else ("user" if role == "human" else role)
    return "user"


def _message_content(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, str):
                fragments.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    fragments.append(str(text))
        return "\n".join(fragment for fragment in fragments if fragment).strip()
    return str(content)


def _serialize_messages(messages: list[Any]) -> list[dict[str, str]]:
    serialized: list[dict[str, str]] = []
    for message in messages:
        serialized.append(
            {
                "role": _message_role(message),
                "content": _message_content(message),
            }
        )
    return serialized


def _build_payload(messages: list[Any], model_id: Optional[str] = None) -> dict[str, Any]:
    return {
        "model": _resolve_model_id(model_id),
        "messages": _serialize_messages(messages),
        "stream": False,
        "options": {
            "num_ctx": 4096,
            "num_predict": 1024,
            "temperature": 0.1,
            "repeat_penalty": 1.15,
            "stop": STOP_TOKENS,
        },
    }


def _post_chat(payload: dict[str, Any]) -> str:
    request = urllib.request.Request(
        f"{settings.OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        logger.error("❌ Ollama chat HTTP error: %s", details)
        raise RuntimeError(f"Ollama chat request failed ({exc.code}): {details}") from exc
    except urllib.error.URLError as exc:
        logger.error("❌ Ollama chat connection error: %s", exc)
        raise RuntimeError(f"Could not connect to Ollama at {settings.OLLAMA_BASE_URL}") from exc

    message = body.get("message", {}) if isinstance(body, dict) else {}
    content = message.get("content", "")
    return content.strip() if isinstance(content, str) else str(content)


class SimpleLLMClient:
    def __init__(self, model_id: Optional[str] = None):
        self.model_id = _resolve_model_id(model_id)

    async def ainvoke(self, messages: list[Any]) -> SimpleLLMResponse:
        async with ASYNC_LLM_SEMAPHORE:
            logger.info("🤖 queued local chat start model=%s messages=%s", self.model_id, len(messages))
            content = await asyncio.to_thread(_post_chat, _build_payload(messages, self.model_id))
            logger.info("🤖 queued local chat finish model=%s chars=%s", self.model_id, len(content))
        return SimpleLLMResponse(content=content)

    def invoke(self, messages: list[Any]) -> SimpleLLMResponse:
        with SYNC_LLM_LOCK:
            logger.info("🤖 sync local chat start model=%s messages=%s", self.model_id, len(messages))
            content = _post_chat(_build_payload(messages, self.model_id))
            logger.info("🤖 sync local chat finish model=%s chars=%s", self.model_id, len(content))
        return SimpleLLMResponse(content=content)


def get_llm(model_id: Optional[str] = None) -> SimpleLLMClient:
    """Return the local Ollama chat client."""
    return SimpleLLMClient(model_id=model_id)


async def call_with_fallback(messages, task_type: str, model_id: Optional[str] = None):
    """Execute an async local LLM call."""
    llm = get_llm(model_id=model_id)
    try:
        response = await llm.ainvoke(messages)
        return response.content
    except Exception as e:
        logger.error(f"❌ LLM call failed for {task_type}: {e}")
        raise e


def call_sync_with_fallback(messages, task_type: str, model_id: Optional[str] = None):
    """Execute a synchronous local LLM call."""
    llm = get_llm(model_id=model_id)
    try:
        response = llm.invoke(messages)
        return response.content
    except Exception as e:
        logger.error(f"❌ Sync LLM call failed for {task_type}: {e}")
        raise e
