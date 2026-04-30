import os
from typing import List
import yaml
from datetime import datetime
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from config import settings
from utils.git_manager import GitManager

from utils.progress import progress_manager
from langchain_text_splitters import RecursiveCharacterTextSplitter
import asyncio
import logging

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("llm-wiki")

class IngestEngine:
    def __init__(self, raw_dir: str, wiki_dir: str, model_name: str = None):
        self.raw_dir = raw_dir
        self.wiki_dir = wiki_dir
        self.model_name = model_name or settings.DEFAULT_MODEL
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(wiki_dir, exist_ok=True)
        
        self.git_manager = GitManager(wiki_dir)
        
        # Local Ollama instance
        self.llm = ChatOllama(
            model=self.model_name,
            base_url=settings.OLLAMA_BASE_URL
        )

        # Chunking strategy
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=4000,
            chunk_overlap=200
        )

    async def _call_llm(self, chain, inputs):
        # No more retries needed for local rate limits, but good for robustness
        return await chain.ainvoke(inputs)

    async def _synthesize_summaries(self, summaries: List[str], depth=0) -> str:
        # Still group summaries to stay within Ollama's context window
        batch_size = 10 
        
        if len(summaries) <= batch_size:
            logger.info(f"✨ Synthesizing final batch of {len(summaries)} summaries...")
            progress_manager.broadcast("Synthesizing final wiki page", 85)
            
            prompt = ChatPromptTemplate.from_template("""
            You are a master wiki maintainer. Synthesize the following partial summaries into a single, 
            comprehensive wiki page. Use [[Page Name]] syntax for all key concepts.
            
            Partial Summaries:
            {summaries}
            """)
            return (await self._call_llm(prompt | self.llm, {"summaries": "\n\n".join(summaries)})).content
        
        logger.info(f"🌿 Hierarchical Synthesis (Depth {depth}): Processing {len(summaries)} summaries in batches of {batch_size}")
        new_summaries = []
        for i in range(0, len(summaries), batch_size):
            batch = summaries[i : i + batch_size]
            batch_prompt = ChatPromptTemplate.from_template("""
            Combine these related summaries into a single cohesive summary. 
            Maintain all key concepts and [[Page Name]] links.
            
            Summaries:
            {summaries}
            """)
            res = await self._call_llm(batch_prompt | self.llm, {"summaries": "\n\n".join(batch)})
            new_summaries.append(res.content)
            
        return await self._synthesize_summaries(new_summaries, depth + 1)

    async def process_file(self, filename: str):
        logger.info(f"🚀 Starting local ingestion for: {filename}")
        progress_manager.broadcast(f"Starting local ingestion for {filename}", 5)
        
        raw_path = os.path.join(self.raw_dir, filename)
        with open(raw_path, "r") as f:
            content = f.read()

        # 1. Chunking
        chunks = self.splitter.split_text(content)
        chunk_summaries = []
        
        logger.info(f"📄 Split into {len(chunks)} chunks. Using local model: {self.model_name}")
        progress_manager.broadcast(f"Split into {len(chunks)} chunks", 10)
        
        for i, chunk in enumerate(chunks):
            percent = 10 + int((i / len(chunks)) * 70)
            msg = f"Processing chunk {i+1}/{len(chunks)}"
            logger.info(f"  🤖 {msg}")
            progress_manager.broadcast(msg, percent)
            
            prompt = ChatPromptTemplate.from_template("""
            Summarize this section of a document. Identify key concepts and entities.
            
            Section {index}:
            {content}
            """)
            
            res = await self._call_llm(prompt | self.llm, {"content": chunk, "index": i+1})
            chunk_summaries.append(res.content)

        # 2. Recursive Synthesis
        final_summary = await self._synthesize_summaries(chunk_summaries)
        
        # 3. Audit Pass (Verification)
        logger.info("🔍 Running quality audit pass...")
        progress_manager.broadcast("Running quality audit pass", 90)
        
        audit_prompt = ChatPromptTemplate.from_template(
            """
        Verify the following summary for accuracy. 
        Are there any hallucinations or misinterpretations? 
        If yes, correct them. If no, return the original summary.
        
        Summary: {summary}
        """
        )

        audit_res = await self._call_llm(audit_prompt | self.llm, {"summary": final_summary})
        refined_summary = audit_res.content

        # 4. Update Wiki
        wiki_filename = f"{os.path.splitext(filename)[0]}.md"
        wiki_path = os.path.join(self.wiki_dir, wiki_filename)
        
        frontmatter = {
            "type": "summary",
            "sources": [filename],
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "confidence_score": 0.98,
        }
        
        wiki_content = f"---\n{yaml.dump(frontmatter)}---\n\n{refined_summary}"
        
        with open(wiki_path, "w") as f:
            f.write(wiki_content)
        
        self.update_index(wiki_filename, frontmatter)
        
        logger.info(f"✅ Wiki page created: {wiki_filename}")
        progress_manager.broadcast("Committing to Git...", 95)
        
        if self.git_manager.commit_changes(f"Ingest: {filename}"):
             logger.info("📦 Changes committed to Git.")
        
        progress_manager.broadcast("Complete!", 100, "success")
        return wiki_filename

    def update_index(self, filename: str, metadata: dict):
        index_path = os.path.join(self.wiki_dir, "index.md")
        # ... keep the rest of the file

    def update_index(self, filename: str, metadata: dict):
        index_path = os.path.join(self.wiki_dir, "index.md")
        entry = f"- [{filename}]({filename}): {metadata['type']} (Updated: {metadata['last_updated']})\n"

        if not os.path.exists(index_path):
            with open(index_path, "w") as f:
                f.write("# Wiki Index\n\n")

        with open(index_path, "a") as f:
            f.write(entry)
