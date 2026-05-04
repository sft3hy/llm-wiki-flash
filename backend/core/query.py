import os
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.messages import SystemMessage, HumanMessage
from core.llm_provider import get_llm, call_with_fallback
from config import settings

class QueryEngine:
    def __init__(self, wiki_dir: str):
        self.wiki_dir = wiki_dir
        self.embeddings = OllamaEmbeddings(
            model="nomic-embed-text",
            base_url=settings.OLLAMA_BASE_URL
        )
        self.vectorstore = Chroma(
            collection_name="wiki_pages",
            embedding_function=self.embeddings,
            persist_directory=os.path.join(wiki_dir, ".chroma")
        )

    def add_documents(self, chunks: list[str], metadatas: list[dict]):
        """Add document chunks to the vectorstore."""
        if not chunks:
            return
        self.vectorstore.add_texts(texts=chunks, metadatas=metadatas)

    async def search(self, query: str, k: int = 3):
        """Semantic search returning formatted string context."""
        results = self.vectorstore.similarity_search(query, k=k)
        if not results:
            return ""
        
        context_parts = []
        for i, doc in enumerate(results):
            source = doc.metadata.get("source", "Unknown")
            context_parts.append(f"--- Document {i+1} (Source: {source}) ---\n{doc.page_content}")
            
        return "\n\n".join(context_parts)

    async def qa_query(self, query: str, history: list[dict] = None, model_id: str = None) -> dict:
        """Perform full retrieval-augmented generation."""
        # 1. Retrieve Context
        context = await self.search(query, k=4)
        if not context:
            context = "No relevant context found in wiki."
            
        # 2. Formulate QA Prompt
        system_instr = f"""IMPORTANT: PROVIDE DIRECT RESPONSES ONLY. DO NOT INCLUDE ANY INTERNAL MONOLOGUES, THINKING, OR <thought> TAGS.

You are a helpful assistant for the LLM Wiki knowledge base. 
Answer concisely and accurately based ONLY on the provided WIKI CONTEXT. 
If the context does not contain the answer, explicitly state that you cannot answer based on the context.
Use [[wikilinks]] when referencing wiki pages.

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
        
        return {
            "response": response,
            "context": context
        }
