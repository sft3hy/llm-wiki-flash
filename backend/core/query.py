import os
import re
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.messages import SystemMessage, HumanMessage
from core.llm_provider import get_llm, call_with_fallback
from config import settings

class QueryEngine:
    def __init__(self, wiki_dir: str, embeddings_dir: str = None, collection_name: str = "wiki_pages"):
        self.wiki_dir = wiki_dir
        self.embeddings_dir = embeddings_dir or os.path.join(wiki_dir, ".chroma")
        self.embeddings = OllamaEmbeddings(
            model="nomic-embed-text",
            base_url=settings.OLLAMA_BASE_URL
        )
        self.vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.embeddings_dir
        )

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

    async def search(self, query: str, k: int = 6, document: str = None):
        """Semantic search returning formatted string context with MMR for diversity."""
        search_kwargs = {"k": k, "fetch_k": 20}
        if document:
            search_kwargs["filter"] = {"source": document}
            
        results = self.vectorstore.max_marginal_relevance_search(query, **search_kwargs)
        if not results:
            return ""
        
        context_parts = []
        seen_content = set()
        
        for i, doc in enumerate(results):
            # Normalize content for simple deduplication
            content_norm = doc.page_content.strip()
            if content_norm in seen_content:
                continue
            seen_content.add(content_norm)
            
            source = doc.metadata.get("source", "Unknown")
            context_parts.append(f"--- Document {len(context_parts)+1} (Source: {source}) ---\n{doc.page_content}")
            
        return "\n\n".join(context_parts)

    def _get_available_pages(self) -> list[str]:
        if not os.path.exists(self.wiki_dir):
            return []
        pages = []
        for f in os.listdir(self.wiki_dir):
            if f.endswith(".md") and f not in ("SCHEMA.md", "index.md", "log.md"):
                pages.append(f.replace(".md", ""))
        return pages

    async def qa_query(self, query: str, history: list[dict] = None, model_id: str = None, document: str = None) -> dict:
        """Perform full retrieval-augmented generation."""
        # 1. Retrieve Context
        context = await self.search(query, k=6, document=document)
        if not context:
            context = "No relevant context found in wiki."
            
        # 2. Formulate QA Prompt
        available_pages = self._get_available_pages()
        pages_str = ", ".join(available_pages) if available_pages else "None"
        
        system_instr = f"""IMPORTANT: PROVIDE DIRECT RESPONSES ONLY. DO NOT INCLUDE ANY INTERNAL MONOLOGUES, THINKING, OR <thought> TAGS.

You are a helpful assistant for the LLM Wiki knowledge base. 
Answer concisely and accurately based ONLY on the provided WIKI CONTEXT. 
If the context does not contain the answer, explicitly state that you cannot answer based on the context.

AVAILABLE WIKI PAGES:
{pages_str}

LINKING RULES:
1. You may link to existing concepts using [[Page Name]] syntax.
2. You MUST ONLY link to pages listed in the AVAILABLE WIKI PAGES.
3. NEVER hallucinate or invent new page links. If a concept is not in the list, DO NOT use brackets.

WIKI CONTEXT:
{context}"""

        messages = [SystemMessage(content=system_instr)]
        
        if history:
            for msg in history:
                role = msg.get("role", "user")
                if role == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                else:
                    messages.append(SystemMessage(content=msg["content"]))
                    
        messages.append(HumanMessage(content=query))
        
        # 3. Call LLM
        response = await call_with_fallback(messages, "chat", model_id=model_id)
        
        # 4. Post-process response for links
        def replace_link(match):
            page_name = match.group(1).strip()
            # Find a case-insensitive match in available_pages
            valid_page = next((p for p in available_pages if p.lower() == page_name.lower()), None)
            if valid_page:
                return f"[{page_name}](wiki://{valid_page})"
            return page_name

        if response:
            response = re.sub(r'\[\[(.*?)\]\]', replace_link, response)
        
        return {
            "response": response,
            "context": context
        }
