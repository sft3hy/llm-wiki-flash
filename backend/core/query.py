import os
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
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

    async def search(self, query: str):
        # 1. Semantic search via LangChain Chroma
        results = self.vectorstore.similarity_search(query, k=3)
        
        # 2. Return results
        if results:
            return f"Found relevant information in wiki: {results[0].page_content}"
        return f"No specific matches found for '{query}'. Searching raw sources..."
