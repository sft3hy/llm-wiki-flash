"""
QueryEngine — 4-phase hybrid retrieval pipeline.

Phase 1:   TokenSearchService    — fast lexical keyword search
Phase 1.5: Chroma vector search  — semantic boost via OllamaEmbedder
Phase 2:   GraphExpansionService — wiki-link graph expansion (2-hop)
Phase 3:   BudgetAllocator       — token-budget-controlled page selection
Phase 4:   ContextAssemblyService — citation-numbered context block
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from langchain_chroma import Chroma
import ollama
from langchain_core.messages import SystemMessage, HumanMessage

from core.llm_provider import call_with_fallback
from config import settings
from .retrieval.token_search import TokenSearchService, SearchHit
from .retrieval.graph_expansion import GraphExpansionService, build_graph, GraphHit
from .retrieval.budget import BudgetAllocator, RetrievedPage, approx_tokens
from .retrieval.context_assembly import ContextAssemblyService


# ─── Embedder ──────────────────────────────────────────────────────────

class OllamaEmbedder:
    def __init__(self, model: str, base_url: str):
        self.model = model
        self.client = ollama.Client(host=base_url)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.client.embeddings(model=self.model, prompt=t)["embedding"] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.client.embeddings(model=self.model, prompt=text)["embedding"]


# ─── Retrieval Settings ────────────────────────────────────────────────

@dataclass
class RetrievalSettings:
    budget_tokens: int = 8192
    max_keyword_hits: int = 12
    max_graph_pages: int = 8
    graph_max_hops: int = 2
    graph_decay: float = 0.5
    vector_weight: float = 0.4   # How much to boost vector-matched pages
    max_pages_in_context: int = 12


DEFAULT_SETTINGS = RetrievalSettings()


# ─── Merge Helpers ─────────────────────────────────────────────────────

def _merge_results(
    keyword_hits: list[SearchHit],
    vector_docs: list,           # Chroma Document objects
    graph_hits: list[GraphHit],
    vector_weight: float = 0.4,
) -> list:
    """
    Merge keyword, vector, and graph results into a unified ranked list.
    Returns objects with .path, .title, .content, .score, .page_type.
    """
    # Build combined score map: path → SearchHit-like object
    scores: dict[str, dict] = {}

    for h in keyword_hits:
        scores[h.path] = {
            "path": h.path,
            "title": h.title,
            "content": h.content,
            "score": h.score,
            "page_type": h.page_type,
        }

    # Vector results boost existing or add new
    for doc in vector_docs:
        source = doc.metadata.get("source", "")
        # Try to resolve to a full path
        fpath = source if os.path.isfile(source) else source
        if fpath in scores:
            scores[fpath]["score"] += vector_weight * 10  # flat boost
        else:
            scores[fpath] = {
                "path": fpath,
                "title": Path(fpath).stem.replace("-", " ").title() if fpath else source,
                "content": doc.page_content,
                "score": vector_weight * 10,
                "page_type": doc.metadata.get("type", "wiki"),
            }

    # Graph hits add at their decayed score
    for g in graph_hits:
        if g.path in scores:
            scores[g.path]["score"] = max(scores[g.path]["score"], g.score)
        else:
            scores[g.path] = {
                "path": g.path,
                "title": g.title,
                "content": g.content,
                "score": g.score,
                "page_type": g.page_type,
            }

    # Convert to simple namespace-like objects
    class _Hit:
        def __init__(self, d):
            self.__dict__.update(d)

    merged = [_Hit(v) for v in scores.values() if v.get("content", "").strip()]
    merged.sort(key=lambda x: x.score, reverse=True)
    return merged


# ─── Query Engine ──────────────────────────────────────────────────────

class QueryEngine:
    def __init__(
        self,
        wiki_dir: str,
        embeddings_dir: str = None,
        sources_dir: str = None,
        collection_name: str = "wiki_pages",
        retrieval_settings: RetrievalSettings = None,
    ):
        self.wiki_dir = wiki_dir
        self.sources_dir = sources_dir
        self.embeddings_dir = embeddings_dir or os.path.join(wiki_dir, ".chroma")
        self.settings = retrieval_settings or DEFAULT_SETTINGS

        self.embeddings = OllamaEmbedder(
            model="nomic-embed-text",
            base_url=settings.OLLAMA_BASE_URL
        )
        self.vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.embeddings_dir
        )

        self._token_search = TokenSearchService()
        self._graph_expansion = GraphExpansionService()
        self._budget = BudgetAllocator(budget_tokens=self.settings.budget_tokens)
        self._context_assembly = ContextAssemblyService()

    # ─── Document Management ───────────────────────────────────────────

    def add_documents(self, chunks: list[str], metadatas: list[dict]):
        """Add document chunks to the vectorstore."""
        if not chunks:
            return
        self.vectorstore.add_texts(texts=chunks, metadatas=metadatas)

    def clear(self):
        try:
            self.vectorstore.delete_collection()
        except Exception:
            pass
        self.vectorstore = Chroma(
            collection_name="wiki_pages",
            embedding_function=self.embeddings,
            persist_directory=self.embeddings_dir
        )

    # ─── Phase 1: Keyword Search ───────────────────────────────────────

    def _keyword_search(self, query: str) -> list[SearchHit]:
        return self._token_search.search(
            query=query,
            wiki_dir=self.wiki_dir,
            sources_dir=self.sources_dir,
            top_k=self.settings.max_keyword_hits,
        )

    # ─── Phase 1.5: Vector Search ─────────────────────────────────────

    def _vector_search(self, query: str, k: int = 6) -> list:
        """Return Chroma documents via MMR. Falls back to empty list on error."""
        try:
            return self.vectorstore.max_marginal_relevance_search(
                query, k=k, fetch_k=min(k * 3, 30)
            )
        except Exception:
            return []

    # ─── Phase 2: Graph Expansion ─────────────────────────────────────

    def _graph_expand(self, keyword_hits: list[SearchHit], graph=None) -> list[GraphHit]:
        if graph is None:
            graph = build_graph(self.wiki_dir)
        return self._graph_expansion.expand(
            seed_hits=keyword_hits,
            wiki_dir=self.wiki_dir,
            graph=graph,
            max_hops=self.settings.graph_max_hops,
            max_pages=self.settings.max_graph_pages,
            decay=self.settings.graph_decay,
        )

    # ─── Full Retrieval Pipeline ───────────────────────────────────────

    async def retrieve(self, query: str, document: str = None) -> tuple[list[RetrievedPage], dict]:
        """
        Run the full 4-phase retrieval pipeline.
        Returns (allocated_pages, retrieval_stats).
        """
        # Phase 1 — keyword
        if document:
            # Targeted mode: only search within a specific document
            keyword_hits = self._token_search.search(
                query=query, wiki_dir=self.wiki_dir,
                sources_dir=self.sources_dir, top_k=6,
            )
            keyword_hits = [h for h in keyword_hits if document in h.path or h.path.endswith(document)]
        else:
            keyword_hits = self._keyword_search(query)

        # Phase 1.5 — vector boost
        vector_docs = self._vector_search(query, k=6)

        # Phase 2 — graph expansion from top keyword hits
        top_seeds = keyword_hits[:5]
        graph = build_graph(self.wiki_dir)
        graph_hits = self._graph_expand(top_seeds, graph) if top_seeds else []

        # Merge all signals
        merged = _merge_results(keyword_hits, vector_docs, graph_hits, self.settings.vector_weight)

        # Phase 3 — budget allocation
        allocated = self._budget.allocate(merged, max_pages=self.settings.max_pages_in_context)

        stats = {
            "keyword_hits": len(keyword_hits),
            "vector_hits": len(vector_docs),
            "graph_expanded": len(graph_hits),
            "pages_in_context": len(allocated),
            "tokens_used": sum(p.token_count for p in allocated),
        }

        return allocated, stats

    # ─── Legacy search() shim (used by ingest.py article synthesis) ───

    async def search(self, query: str, k: int = 6, document: str = None) -> str:
        """
        Backward-compatible search returning a flat context string.
        Used internally by IngestEngine during article synthesis.
        """
        pages, _ = await self.retrieve(query, document=document)
        if not pages:
            return ""
        parts = []
        for i, page in enumerate(pages[:k]):
            source = Path(page.path).name
            parts.append(f"--- Document {i+1} (Source: {source}, Type: {page.page_type}) ---\n{page.content}")
        return "\n\n".join(parts)

    # ─── Available Pages Helper ────────────────────────────────────────

    def _get_available_pages(self) -> list[str]:
        if not os.path.exists(self.wiki_dir):
            return []
        system = {"SCHEMA.md", "index.md", "log.md", "purpose.md"}
        return [
            f.replace(".md", "")
            for f in os.listdir(self.wiki_dir)
            if f.endswith(".md") and f not in system
        ]

    def _read_system_page(self, filename: str) -> str:
        path = os.path.join(self.wiki_dir, filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError:
                pass
        return ""

    # ─── QA Query ─────────────────────────────────────────────────────

    async def qa_query(
        self,
        query: str,
        history: list[dict] = None,
        model_id: str = None,
        document: str = None,
    ) -> dict:
        """
        Full retrieval-augmented generation with 4-phase pipeline.
        Returns response, context, citation_map, and retrieval_stats.
        """
        # 1. Retrieve
        allocated_pages, retrieval_stats = await self.retrieve(query, document=document)

        # 2. Load system pages
        purpose_content = self._read_system_page("purpose.md")
        index_content = self._read_system_page("index.md")
        available_pages = self._get_available_pages()

        # 3. Assemble context
        assembled = self._context_assembly.assemble(
            pages=allocated_pages,
            purpose_content=purpose_content,
            index_content=index_content,
        )
        context_str = assembled.context_str
        citation_map = assembled.citation_map
        citation_instructions = self._context_assembly.build_citation_instructions(citation_map)
        
        if not allocated_pages and not context_str.strip():
            context_str = "No relevant context found in wiki."

        # 4. Build system prompt
        pages_str = ", ".join(available_pages) if available_pages else "None"
        purpose_section = f"\n\nWIKI PURPOSE & DIRECTION:\n{purpose_content}" if purpose_content else ""

        system_instr = f"""IMPORTANT: PROVIDE DIRECT RESPONSES ONLY. DO NOT INCLUDE ANY INTERNAL MONOLOGUES, THINKING, OR <thought> TAGS.

You are a helpful assistant for the LLM Wiki knowledge base.
Answer concisely and accurately based ONLY on the provided WIKI CONTEXT.
If the context does not contain the answer, explicitly state that you cannot answer based on the context.{purpose_section}
If the user explicitly asks to update the wiki purpose/thesis, or if your conversation significantly evolves the thesis, output the complete new purpose wrapped exactly in <UPDATE_PURPOSE>...</UPDATE_PURPOSE> tags.

AVAILABLE WIKI PAGES:
{pages_str}

LINKING RULES:
1. You may link to existing concepts using [[Page Name]] syntax.
2. You MUST ONLY link to pages listed in the AVAILABLE WIKI PAGES.
3. NEVER hallucinate or invent new page links. If a concept is not in the list, DO NOT use brackets.

{citation_instructions}

WIKI CONTEXT:
{context_str}"""

        messages = [SystemMessage(content=system_instr)]

        if history:
            for msg in history:
                role = msg.get("role", "user")
                if role == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                else:
                    messages.append(SystemMessage(content=msg["content"]))

        messages.append(HumanMessage(content=query))

        # 5. LLM call
        response = await call_with_fallback(messages, "chat", model_id=model_id)

        # 6. Post-process wiki links
        def replace_link(match):
            page_name = match.group(1).strip()
            valid = next((p for p in available_pages if p.lower() == page_name.lower()), None)
            if valid:
                return f"[{page_name}](wiki://{valid})"
            return page_name

        if response:
            response = re.sub(r'\[\[(.*?)\]\]', replace_link, response)

        return {
            "response": response,
            "context": context_str,
            "citation_map": citation_map,
            "retrieval_stats": retrieval_stats,
        }
