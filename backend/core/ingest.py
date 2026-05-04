import os
import re
from typing import List, Dict, Tuple
import yaml
import json
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.llm_provider import call_with_fallback
from core.schema import (
    COMPILER_SYSTEM_PROMPT,
    CORPUS_SUMMARY_PROMPT,
    CONCEPT_EXTRACTION_PROMPT,
    CONCEPT_ARTICLE_PROMPT,
    LOG_ENTRY_FORMAT,
)
from utils.git_manager import GitManager
from utils.progress import progress_manager
import logging
from core.query import QueryEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("llm-wiki")

class IngestEngine:
    def __init__(self, raw_dir: str, wiki_dir: str, model_id: str = None):
        self.raw_dir = raw_dir
        self.wiki_dir = wiki_dir
        self.model_id = model_id
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(wiki_dir, exist_ok=True)

        self.git_manager = GitManager(wiki_dir)
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
        self.query_engine = QueryEngine(wiki_dir)

    async def _call_llm(self, messages: list, task_type: str) -> str:
        logger.info(f"  🤖 Calling LLM for task: {task_type} (model: {self.model_id})")
        try:
            result = await call_with_fallback(messages, task_type, model_id=self.model_id)
        except Exception as e:
            logger.error(f"  ❌ LLM call FAILED for {task_type}: {e}")
            return ""
        if not result or not result.strip():
            logger.warning(f"  ⚠️ LLM returned empty result for {task_type}")
            return ""
        logger.info(f"  ✅ LLM returned {len(result)} chars for {task_type}")
        logger.debug(f"  📄 LLM output preview: {result[:200]}")
        return result

    def _get_existing_pages(self) -> List[str]:
        if not os.path.exists(self.wiki_dir):
            return []
        return [f for f in os.listdir(self.wiki_dir) if f.endswith(".md") and f not in ("SCHEMA.md",)]

    def _read_wiki_page(self, filename: str) -> str:
        path = os.path.join(self.wiki_dir, filename)
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
        return ""

    def _write_wiki_page(self, filename: str, content: str):
        path = os.path.join(self.wiki_dir, filename)
        with open(path, "w") as f:
            f.write(content)

    async def _generate_summary(self, content: str) -> str:
        """Generate a short summary of a single document."""
        content_len = len(content)
        if content_len < 200:
            logger.info(f"    📋 Content too short ({content_len} chars), using raw text as summary")
            return content
        
        # Use more content for the summary if available
        truncated = content[:6000]
        prompt = CORPUS_SUMMARY_PROMPT.format(content=truncated)
        messages = [HumanMessage(content=prompt)]
        summary = await self._call_llm(messages, "summarization")
        if not summary:
            logger.warning(f"    ⚠️ Summary generation returned empty, using first 1000 chars as fallback")
            return content[:1000]
        logger.info(f"    📋 Generated summary: {summary[:100]}...")
        return summary

    def _parse_concepts_from_text(self, result: str) -> List[Dict[str, str]]:
        """Try to parse a JSON concept list from raw LLM output."""
        if not result or not result.strip():
            logger.error("  ❌ Cannot parse concepts from empty result")
            return []

        # Strip markdown code fences if present
        cleaned = result.strip()
        if cleaned.startswith('```'):
            # Remove opening fence (```json or ```)
            first_newline = cleaned.find('\n')
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1:]
            # Remove closing fence
            if cleaned.rstrip().endswith('```'):
                cleaned = cleaned.rstrip()[:-3].rstrip()

        # Find JSON array
        start = cleaned.find('[')
        end = cleaned.rfind(']') + 1
        if start == -1 or end == 0:
            logger.error(f"  ❌ No JSON array found in LLM output. Full output:\n{result}")
            return []

        json_str = cleaned[start:end]
        try:
            concepts = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"  ❌ JSON parse error: {e}\n  Raw JSON string: {json_str[:500]}")
            return []

        # Filter and normalize
        valid = [c for c in concepts if isinstance(c, dict) and 'name' in c]
        for c in valid:
            c['name'] = c['name'].lower().replace(" ", "-")
            c['name'] = re.sub(r'[^a-z0-9\-]', '', c['name'])
        
        logger.info(f"  ✅ Parsed {len(valid)} valid concepts: {[c['name'] for c in valid]}")
        return valid

    async def _extract_global_concepts(self, topic: str, source_summaries: str) -> List[Dict[str, str]]:
        """Extract a global list of concepts from the combined document summaries."""
        logger.info(f"  📊 Summaries length: {len(source_summaries)} chars")
        logger.info(f"  📊 Summaries preview: {source_summaries[:300]}...")

        prompt = CONCEPT_EXTRACTION_PROMPT.format(
            topic=topic,
            source_summaries=source_summaries
        )
        messages = [HumanMessage(content=prompt)]
        result = await self._call_llm(messages, "concept-extraction")
        
        logger.info(f"  📊 Raw concept extraction output ({len(result)} chars):\n{result}")

        concepts = self._parse_concepts_from_text(result)

        # Retry once if parsing failed
        if not concepts:
            logger.warning("  🔄 First attempt failed to extract concepts, retrying...")
            result = await self._call_llm(messages, "concept-extraction-retry")
            logger.info(f"  📊 Retry output ({len(result)} chars):\n{result}")
            concepts = self._parse_concepts_from_text(result)

        return concepts

    async def _synthesize_concept_article(self, concept: Dict[str, str]) -> str:
        """Write a standalone article for a specific concept using RAG."""
        filename = f"{concept['name']}.md"
        existing_content = self._read_wiki_page(filename)

        if existing_content:
            existing_content_section = f"EXISTING PAGE CONTENT (preserve and integrate):\n{existing_content}"
            logger.info(f"    📄 Found existing page for {concept['name']} ({len(existing_content)} chars)")
        else:
            existing_content_section = ""

        # Retrieve relevant context from ChromaDB
        query = f"{concept['name'].replace('-', ' ')} {concept.get('description', '')}"
        logger.info(f"    🔎 RAG query: {query[:100]}")
        retrieved_context = await self.query_engine.search(query, k=8)
        if not retrieved_context:
            logger.warning(f"    ⚠️ No RAG results for concept: {concept['name']}")
            retrieved_context = "No specific details found in the provided sources."
        else:
            logger.info(f"    🔎 RAG returned {len(retrieved_context)} chars of context")

        messages = [
            SystemMessage(content=COMPILER_SYSTEM_PROMPT),
            HumanMessage(content=CONCEPT_ARTICLE_PROMPT.format(
                concept_name=concept["name"].replace("-", " ").title(),
                retrieved_context=retrieved_context,
                existing_content_section=existing_content_section
            ))
        ]

        return await self._call_llm(messages, "article-writing")

    def _update_index(self, touched_pages: List[str] = None):
        index_path = os.path.join(self.wiki_dir, "index.md")
        all_pages = self._get_existing_pages()
        lines = ["# Wiki Index\n", "## Map of Content\n"]
        touched = set(touched_pages or [])

        for page in sorted(all_pages):
            if page in ("index.md", "log.md", "SCHEMA.md"): continue
            content = self._read_wiki_page(page)
            title = page.replace(".md", "").replace("-", " ").title()
            try:
                if content.startswith("---"):
                    fm_end = content.index("---", 3)
                    fm = yaml.safe_load(content[3:fm_end])
                    if fm and isinstance(fm, dict): title = fm.get("title", title)
            except:
                pass

            marker = " ✨" if page.replace(".md", "") in touched else ""
            lines.append(f"- [[{page.replace('.md', '')}]] — {title}{marker}\n")

        with open(index_path, "w") as f:
            f.writelines(lines)

    def _update_log(self, source_id: str, created: List[str], updated: List[str]):
        log_path = os.path.join(self.wiki_dir, "log.md")
        if not os.path.exists(log_path):
            with open(log_path, "w") as f:
                f.write("# Compilation Log\n\n")

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        created_str = ", ".join(f"[[{c}]]" for c in created) if created else "none"
        updated_str = ", ".join(f"[[{u}]]" for u in updated) if updated else "none"
        entry = LOG_ENTRY_FORMAT.format(date=now, source=source_id, created=created_str, updated=updated_str)
        with open(log_path, "a") as f:
            f.write(entry)

    async def process_corpus(self, topic: str, documents: List[Dict[str, str]]) -> Dict:
        """
        Process a full corpus of documents (from folder, vault, or clippings).
        documents: List of dicts with 'filename', 'content', 'source_type'
        """
        logger.info(f"🚀 Starting corpus ingestion for topic: '{topic}' with {len(documents)} docs.")
        for i, doc in enumerate(documents):
            logger.info(f"  📄 Doc {i+1}: {doc['filename']} ({len(doc['content'])} chars, type={doc.get('source_type', '?')})")
        progress_manager.broadcast("Initializing corpus ingestion", 5)

        # 1. Normalize, Save, and Embed
        all_summaries = []
        for i, doc in enumerate(documents):
            logger.info(f"\n{'='*60}")
            logger.info(f"📂 Processing document {i+1}/{len(documents)}: {doc['filename']}")
            logger.info(f"{'='*60}")
            progress_manager.broadcast(f"Processing source {i+1}/{len(documents)}: {doc['filename']}", 10 + int((i/len(documents))*20))
            
            # Save raw
            raw_path = os.path.join(self.raw_dir, doc['filename'])
            with open(raw_path, "w") as f:
                f.write(doc['content'])
            logger.info(f"  💾 Saved raw file to: {raw_path}")
            
            # Embed in Chroma
            chunks = self.splitter.split_text(doc['content'])
            logger.info(f"  🧩 Split into {len(chunks)} chunks")
            metadatas = [{"source": doc['filename'], "type": doc.get('source_type', 'upload')} for _ in chunks]
            self.query_engine.add_documents(chunks=chunks, metadatas=metadatas)
            logger.info(f"  📦 Embedded {len(chunks)} chunks into ChromaDB")

            # Summarize
            summary = await self._generate_summary(doc['content'])
            all_summaries.append(f"--- Source: {doc['filename']} ---\n{summary}")

        # 2. Extract Global Concepts
        logger.info(f"\n{'='*60}")
        logger.info(f"🔍 CONCEPT EXTRACTION PHASE")
        logger.info(f"{'='*60}")
        progress_manager.broadcast("Extracting global concepts", 40)
        combined_summaries = "\n\n".join(all_summaries)
        logger.info(f"📊 Combined summaries ({len(combined_summaries)} chars):\n{combined_summaries[:500]}")
        concepts = await self._extract_global_concepts(topic, combined_summaries)

        if not concepts:
            logger.warning("⚠️ No concepts extracted even after retry. Falling back to generic topic concept.")
            concepts = [{"name": topic.lower().replace(" ", "-"), "description": f"Main entry for {topic}"}]

        # 3. Write Concept Articles using RAG
        created_pages = []
        updated_pages = []
        
        for i, concept in enumerate(concepts):
            pct = 50 + int((i/max(len(concepts), 1)) * 40)
            logger.info(f"📝 Writing article for concept: {concept['name']}")
            progress_manager.broadcast(f"Writing article: {concept['name']}", pct)
            
            page_content = await self._synthesize_concept_article(concept)
            if page_content:
                page_name = f"{concept['name']}.md"
                existing = os.path.exists(os.path.join(self.wiki_dir, page_name))
                self._write_wiki_page(page_name, page_content)

                # Embed the new wiki page back into Chroma so it can be queried
                self.query_engine.add_documents(
                    chunks=[page_content],
                    metadatas=[{"source": page_name, "type": "wiki_page"}]
                )

                if existing:
                    updated_pages.append(concept['name'])
                else:
                    created_pages.append(concept['name'])
            
            if (i+1) % 5 == 0:
                self._update_index(created_pages + updated_pages)

        # 4. Finalize
        progress_manager.broadcast("Updating index and log", 95)
        self._update_index(created_pages + updated_pages)
        self._update_log(f"Corpus: {topic}", created_pages, updated_pages)

        if self.git_manager.commit_changes(f"Ingest Corpus: {topic} — {len(created_pages)} created, {len(updated_pages)} updated"):
            logger.info("  ✅ Changes committed")

        summary_result = {
            "status": "success",
            "topic": topic,
            "documents_processed": len(documents),
            "pages_created": created_pages,
            "pages_updated": updated_pages,
        }
        
        progress_manager.broadcast(f"Complete! {len(created_pages)} created.", 100, "success")
        return summary_result

    def remove_wiki_page(self, filename: str) -> bool:
        path = os.path.join(self.wiki_dir, filename)
        if os.path.exists(path):
            os.remove(path)
            self._update_index([])
            self.git_manager.commit_changes(f"Delete wiki page: {filename}")
            return True
        return False
