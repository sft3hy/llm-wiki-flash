from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm_provider import call_with_fallback
from .utils import normalize_whitespace, sentence_split


TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")
SYSTEM_WIKI_DOCUMENTS = {"SCHEMA.md", "index.md", "log.md"}


@dataclass(slots=True)
class TopicDocument:
    name: str
    kind: str
    title: str
    content: str


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def _document_title(content: str, fallback: str) -> str:
    first_heading = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
    if first_heading:
        return normalize_whitespace(first_heading.group(1))
    return fallback


def _load_markdown_documents(directory: Path, kind: str) -> list[TopicDocument]:
    documents: list[TopicDocument] = []
    if not directory.exists():
        return documents
    for path in sorted(directory.glob("*.md")):
        if kind == "wiki" and path.name in SYSTEM_WIKI_DOCUMENTS:
            continue
        content = path.read_text(encoding="utf-8")
        documents.append(
            TopicDocument(
                name=path.name,
                kind=kind,
                title=_document_title(content, path.stem.replace("-", " ").title()),
                content=content,
            )
        )
    return documents


def load_topic_documents(vault_path: Path, wiki_id: str) -> list[TopicDocument]:
    topic_root = vault_path / wiki_id
    wiki_documents = _load_markdown_documents(topic_root / "wiki", "wiki")
    source_documents = _load_markdown_documents(topic_root / "sources", "source")
    return wiki_documents + source_documents


def _score_document(query: str, document: TopicDocument) -> int:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0
    lowered = document.content.lower()
    score = 0
    for token in query_tokens:
        score += lowered.count(token) * 3
    for phrase in sentence_split(query):
        if phrase and phrase.lower() in lowered:
            score += 5
    if document.kind == "wiki":
        score += 2
    return score


def retrieve_topic_context(
    vault_path: Path,
    wiki_id: str,
    query: str,
    document_name: str | None = None,
    document_kind: str | None = None,
    limit: int = 5,
) -> tuple[str, list[str]]:
    documents = load_topic_documents(vault_path, wiki_id)
    available_pages = [document.name.replace(".md", "") for document in documents if document.kind == "wiki"]
    if document_name:
        filtered = []
        for document in documents:
            if document.name == document_name and (document_kind is None or document.kind == document_kind):
                filtered.append(document)
        documents = filtered
    ranked = sorted(documents, key=lambda document: _score_document(query, document), reverse=True)
    selected = [document for document in ranked if _score_document(query, document) > 0][:limit]
    if not selected:
        selected = ranked[:limit]
    parts: list[str] = []
    for document in selected:
        parts.append(f"--- {document.kind.upper()}: {document.name} ({document.title}) ---\n{document.content}")
    return "\n\n".join(parts), available_pages


def _replace_internal_links(response: str, available_pages: list[str]) -> str:
    available_lookup = {page.lower(): page for page in available_pages}

    def replace_link(match: re.Match[str]) -> str:
        page_name = match.group(1).strip()
        label = match.group(2).strip() if match.group(2) else page_name
        normalized = page_name.lower()
        if normalized in available_lookup:
            resolved = available_lookup[normalized]
            return f"[{label}](wiki://{resolved})"
        if normalized.startswith("sources/"):
            source_name = page_name.split("/", 1)[1]
            return f"[{label}](source://{source_name})"
        return label

    return re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", replace_link, response)


async def chat_with_topic(
    vault_path: Path,
    topic: str,
    wiki_id: str,
    message: str,
    history: list[dict] | None = None,
    model_id: str | None = None,
    document_name: str | None = None,
    document_kind: str | None = None,
) -> dict:
    context, available_pages = retrieve_topic_context(
        vault_path=vault_path,
        wiki_id=wiki_id,
        query=message,
        document_name=document_name,
        document_kind=document_kind,
    )
    page_list = ", ".join(available_pages) if available_pages else "none"
    system_prompt = f"""IMPORTANT: PROVIDE DIRECT RESPONSES ONLY. DO NOT INCLUDE ANY INTERNAL MONOLOGUES, THINKING, OR <thought> TAGS.

You are the wiki-builder assistant for a locally generated research vault.
Answer only from the provided context. If the context is insufficient, say so clearly.

AVAILABLE WIKI PAGES:
{page_list}

LINKING RULES:
1. You may use [[page-name]] only for pages in the available list.
2. Do not invent page links that do not exist.
3. When citing a source note, prefer natural language and mention the note title.

TOPIC:
{topic}

CONTEXT:
{context or 'No topic context was available.'}
"""
    messages = [SystemMessage(content=system_prompt)]
    for item in history or []:
        role = item.get("role", "user")
        content = item.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(SystemMessage(content=content))
    messages.append(HumanMessage(content=message))
    response = await call_with_fallback(messages, "wiki-builder-chat", model_id=model_id)
    return {
        "response": _replace_internal_links(response or "", available_pages),
        "context": context,
        "available_pages": available_pages,
    }
