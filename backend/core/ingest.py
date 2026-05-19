import os
import re
import hashlib
from typing import List, Dict, Tuple, Optional
import yaml
import json
from datetime import datetime
from time import perf_counter
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
import ingest_db
import logging
from core.query import QueryEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("llm-wiki")

class IngestEngine:
    def __init__(self, raw_dir: str, wiki_dir: str, model_id: str = None,
                 embeddings_dir: str = None, wiki_id: str = None):
        self.raw_dir = raw_dir
        self.wiki_dir = wiki_dir
        self.model_id = model_id
        self.embeddings_dir = embeddings_dir
        self.wiki_id = wiki_id or "default"
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(wiki_dir, exist_ok=True)
        if embeddings_dir:
            os.makedirs(embeddings_dir, exist_ok=True)

        self.git_manager = GitManager(wiki_dir)
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=150)
        self.query_engine = QueryEngine(wiki_dir, embeddings_dir=embeddings_dir)

    # ─── Logging & Progress ────────────────────────────────────────────

    def _log_step_event(self, stage: str, step: str, status: str, **context):
        payload = {
            "stage": stage, "step": step, "status": status,
            "timestamp": datetime.utcnow().isoformat() + "Z", **context,
        }
        logger.info(json.dumps(payload, default=str))

    def _emit_progress(self, message: str, progress: int, stage: str, step: str, **context):
        progress_manager.broadcast(message, progress, "processing", stage=stage, step=step, **context)

    def _progress_percent(self, completed_steps: int, total_steps: int) -> int:
        if total_steps <= 0:
            return 0
        return max(1, min(99, int((completed_steps / total_steps) * 100)))

    # ─── LLM ───────────────────────────────────────────────────────────

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

    # ─── Wiki Helpers ──────────────────────────────────────────────────

    def _get_existing_pages(self) -> List[str]:
        if not os.path.exists(self.wiki_dir):
            return []
        system_pages = {"SCHEMA.md", "purpose.md", "index.md", "log.md"}
        return [f for f in os.listdir(self.wiki_dir) if f.endswith(".md") and f not in system_pages]

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

    # ─── Content Processing ────────────────────────────────────────────

    async def _generate_summary(self, content: str) -> str:
        """Generate a short summary of a single document."""
        content_len = len(content)
        if content_len < 200:
            return content
        truncated = content[:6000]
        prompt = CORPUS_SUMMARY_PROMPT.format(content=truncated)
        messages = [HumanMessage(content=prompt)]
        summary = await self._call_llm(messages, "summarization")
        if not summary:
            return content[:1000]
        return summary

    def _parse_concepts_from_text(self, result: str) -> List[Dict[str, str]]:
        """Try to parse a JSON concept list from raw LLM output."""
        if not result or not result.strip():
            return []
        cleaned = result.strip()
        if cleaned.startswith('```'):
            first_newline = cleaned.find('\n')
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1:]
            if cleaned.rstrip().endswith('```'):
                cleaned = cleaned.rstrip()[:-3].rstrip()
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
        valid = [c for c in concepts if isinstance(c, dict) and 'name' in c]
        for c in valid:
            c['name'] = c['name'].lower().replace(" ", "-")
            c['name'] = re.sub(r'[^a-z0-9\-]', '', c['name'])
        logger.info(f"  ✅ Parsed {len(valid)} valid concepts: {[c['name'] for c in valid]}")
        return valid

    async def _extract_global_concepts(self, topic: str, source_summaries: str) -> List[Dict[str, str]]:
        """Extract a global list of concepts from the combined document summaries."""
        purpose_content = self._read_wiki_page("purpose.md")
        prompt = CONCEPT_EXTRACTION_PROMPT.format(topic=topic, source_summaries=source_summaries)
        messages = [HumanMessage(content=prompt)]
        if purpose_content:
            messages.insert(0, SystemMessage(content=f"WIKI PURPOSE & DIRECTION:\n{purpose_content}\n\nAlign all concept extraction with the above purpose."))
        result = await self._call_llm(messages, "concept-extraction")
        concepts = self._parse_concepts_from_text(result)
        if not concepts:
            logger.warning("  🔄 First attempt failed to extract concepts, retrying...")
            result = await self._call_llm(messages, "concept-extraction-retry")
            concepts = self._parse_concepts_from_text(result)
        return concepts

    async def _synthesize_concept_article(self, concept: Dict[str, str]) -> str:
        """Write a standalone article for a specific concept using RAG."""
        filename = f"{concept['name']}.md"
        existing_content = self._read_wiki_page(filename)
        existing_content_section = f"EXISTING PAGE CONTENT (preserve and integrate):\n{existing_content}" if existing_content else ""
        query = f"{concept['name'].replace('-', ' ')} {concept.get('description', '')}"
        retrieved_context = await self.query_engine.search(query, k=8)
        if not retrieved_context:
            retrieved_context = "No specific details found in the provided sources."
        index_content = self._read_wiki_page("index.md")
        purpose_content = self._read_wiki_page("purpose.md")
        system_content = COMPILER_SYSTEM_PROMPT
        if purpose_content:
            system_content += f"\n\nWIKI PURPOSE & DIRECTION:\n{purpose_content}\n\nAlign all synthesis with the above purpose."
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=CONCEPT_ARTICLE_PROMPT.format(
                concept_name=concept["name"].replace("-", " ").title(),
                retrieved_context=retrieved_context,
                existing_content_section=existing_content_section,
                index_content=index_content if index_content else "None (Wiki is currently empty)"
            ))
        ]
        return await self._call_llm(messages, "article-writing")

    def _update_index(self, touched_pages: List[str] = None):
        index_path = os.path.join(self.wiki_dir, "index.md")
        all_pages = self._get_existing_pages()
        lines = ["# Wiki Index\n", "## Map of Content\n"]
        touched = set(touched_pages or [])
        for page in sorted(all_pages):
            if page in ("index.md", "log.md", "SCHEMA.md", "purpose.md"): continue
            content = self._read_wiki_page(page)
            title = page.replace(".md", "").replace("-", " ").title()
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

    async def _auto_draft_purpose(self, topic: str, summaries: List[str]):
        """Draft a contextual purpose.md if it's currently empty/boilerplate."""
        purpose_content = self._read_wiki_page("purpose.md")
        # Check if empty or contains the default boilerplate
        if not purpose_content.strip() or "Defines goals, key questions" in purpose_content:
            logger.info("  📝 Drafting contextual purpose.md...")
            context = "\n".join(summaries[:5])
            messages = [
                SystemMessage(content="You are defining the core purpose and research thesis for a new local knowledge base."),
                HumanMessage(content=f"Topic: {topic}\nSource Context:\n{context}\n\nDraft a concise 2-paragraph purpose statement defining the goals, key questions, and research scope for this wiki. Output ONLY the markdown text, starting with a # Wiki Purpose header.")
            ]
            response = await self._call_llm(messages, "purpose-draft")
            if response:
                self._write_wiki_page("purpose.md", response.strip())
                logger.info("  ✅ Drafted purpose.md")

    # ─── SHA256 Hashing ────────────────────────────────────────────────

    @staticmethod
    def _sha256(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_folder_context(filename: str) -> list[str]:
        """Extract folder hierarchy from a filename like 'papers-energy-grid.md'."""
        parts = filename.replace("/", "-").split("-")
        return parts[:-1] if len(parts) > 1 else []

    # ─── Queue-Based Entry Point ───────────────────────────────────────

    def enqueue_documents(self, topic: str, documents: List[Dict[str, str]],
                          force: bool = False) -> Dict:
        """
        Hash, cache-check, and enqueue documents for processing.
        Returns { queued, skipped, task_ids }.
        """
        queued = 0
        skipped = 0
        task_ids = []

        for doc in documents:
            content = doc["content"]
            filename = doc["filename"]
            sha = self._sha256(content)

            # Cache check — skip unchanged files
            if not force and ingest_db.check_cache(self.wiki_id, filename, sha):
                logger.info(f"  ⏭️ Cache hit (unchanged): {filename}")
                skipped += 1
                continue

            # Save raw file
            raw_path = os.path.join(self.raw_dir, filename)
            os.makedirs(os.path.dirname(raw_path), exist_ok=True)
            with open(raw_path, "w") as f:
                f.write(content)

            folder_context = self._extract_folder_context(filename)
            task_id = ingest_db.enqueue_task(
                wiki_id=self.wiki_id,
                filename=filename,
                source_path=raw_path,
                topic=topic,
                model_id=self.model_id,
                folder_context=folder_context,
            )
            task_ids.append(task_id)
            queued += 1
            logger.info(f"  📥 Queued: {filename} (task={task_id[:8]})")

        return {"queued": queued, "skipped": skipped, "task_ids": task_ids}

    # ─── Queue Processor ───────────────────────────────────────────────

    async def process_queue(self, topic: str) -> Dict:
        """
        Process all pending tasks in the queue for this wiki.
        Runs serialized — one task at a time with retry support.
        """
        started_at = perf_counter()
        all_created = []
        all_updated = []
        tasks_completed = 0
        tasks_failed = 0

        pending = ingest_db.get_pending_tasks(self.wiki_id)
        if not pending:
            return {"status": "success", "message": "No pending tasks.", "tasks_completed": 0}

        total_tasks = len(pending)
        logger.info(f"🚀 Processing queue: {total_tasks} pending tasks for wiki={self.wiki_id}")

        # Phase 1: Process each document — summarize, embed raw chunks
        all_summaries = []
        processed_filenames = []

        for task_idx, task in enumerate(pending):
            task_id = task["id"]
            filename = task["filename"]
            source_path = task["source_path"]

            try:
                ingest_db.update_task_status(task_id, "processing")
                self._emit_progress(
                    f"Processing {task_idx+1}/{total_tasks}: {filename}",
                    self._progress_percent(task_idx, total_tasks * 2),
                    "document", "processing",
                    document_name=filename, document_index=task_idx+1,
                    total_documents=total_tasks, active_model=self.model_id,
                )

                # Read content
                with open(source_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Chunk & embed
                chunks = self.splitter.split_text(content)
                metadatas = [{"source": filename, "type": "source"} for _ in chunks]
                self.query_engine.add_documents(chunks=chunks, metadatas=metadatas)
                logger.info(f"  📦 Embedded {len(chunks)} chunks for {filename}")

                # Summarize
                summary = await self._generate_summary(content)
                all_summaries.append(f"--- Source: {filename} ---\n{summary}")
                processed_filenames.append(filename)

                # Mark task as ready for synthesis (still processing)
                ingest_db.update_task_status(task_id, "processing")

            except Exception as e:
                logger.error(f"  ❌ Task {task_id[:8]} failed: {e}")
                retry_count = ingest_db.increment_retry(task_id)
                if retry_count > ingest_db.MAX_RETRIES:
                    ingest_db.update_task_status(task_id, "failed", error=str(e))
                    tasks_failed += 1
                continue

        if not all_summaries:
            # All tasks failed during document phase
            for task in pending:
                if task["status"] == "processing":
                    ingest_db.update_task_status(task["id"], "failed", error="No summaries generated")
            return {"status": "error", "message": "All documents failed processing.", "tasks_failed": tasks_failed}

        # Phase 2: Global concept extraction + article synthesis
        self._emit_progress(
            "Extracting concepts from all documents",
            self._progress_percent(total_tasks, total_tasks * 2),
            "concepts", "extract_concepts",
            topic=topic, processed_documents=len(all_summaries),
        )

        combined_summaries = "\n\n".join(all_summaries)
        
        # Auto-draft purpose if needed
        await self._auto_draft_purpose(topic, all_summaries)

        concepts = await self._extract_global_concepts(topic, combined_summaries)
        if not concepts:
            concepts = [{"name": topic.lower().replace(" ", "-"), "description": f"Main entry for {topic}"}]

        # Write concept articles
        created_pages = []
        updated_pages = []
        total_write_steps = len(concepts)

        for i, concept in enumerate(concepts):
            self._emit_progress(
                f"Writing wiki page {i+1}/{total_write_steps}: {concept['name']}",
                self._progress_percent(total_tasks + i, total_tasks + total_write_steps),
                "wiki", "write_page",
                concept_name=concept["name"], concept_index=i+1,
                total_concepts=total_write_steps, active_model=self.model_id,
            )

            page_content = await self._synthesize_concept_article(concept)
            if page_content:
                page_name = f"{concept['name']}.md"
                existing = os.path.exists(os.path.join(self.wiki_dir, page_name))
                self._write_wiki_page(page_name, page_content)

                # Embed generated page
                page_chunks = self.splitter.split_text(page_content) or [page_content]
                self.query_engine.add_documents(
                    chunks=page_chunks,
                    metadatas=[{"source": page_name, "type": "wiki_page"} for _ in page_chunks]
                )

                # Record traceability
                for fn in processed_filenames:
                    ingest_db.record_generated_page(self.wiki_id, page_name, fn)

                if existing:
                    updated_pages.append(concept['name'])
                else:
                    created_pages.append(concept['name'])

            if (i+1) % 5 == 0:
                self._update_index(created_pages + updated_pages)

        # Finalize — update index, log, cache, and mark tasks complete
        self._update_index(created_pages + updated_pages)
        self._update_log(f"Corpus: {topic}", created_pages, updated_pages)

        generated_page_names = [f"{p}.md" for p in created_pages + updated_pages]
        for task in pending:
            task_id = task["id"]
            filename = task["filename"]
            if filename in processed_filenames:
                # Read content for SHA
                try:
                    with open(task["source_path"], "r", encoding="utf-8") as f:
                        content = f.read()
                    sha = self._sha256(content)
                    ingest_db.update_cache(self.wiki_id, filename, sha, generated_page_names)
                except Exception:
                    pass
                ingest_db.update_task_status(task_id, "completed", result={
                    "pages_created": created_pages,
                    "pages_updated": updated_pages,
                })
                tasks_completed += 1

        if self.git_manager.commit_changes(f"Ingest Corpus: {topic} — {len(created_pages)} created, {len(updated_pages)} updated"):
            logger.info("  ✅ Changes committed")

        result = {
            "status": "success",
            "topic": topic,
            "documents_processed": len(processed_filenames),
            "pages_created": created_pages,
            "pages_updated": updated_pages,
            "tasks_completed": tasks_completed,
            "tasks_failed": tasks_failed,
            "duration_ms": round((perf_counter() - started_at) * 1000, 2),
        }

        progress_manager.broadcast(
            f"Complete! {len(created_pages)} pages created or refreshed.",
            100, "success", stage="complete", step="done",
            topic=topic, documents_processed=len(processed_filenames),
            pages_created=len(created_pages), pages_updated=len(updated_pages),
            duration_ms=result["duration_ms"], active_model=self.model_id,
        )
        return result

    # ─── Legacy Convenience Wrapper ────────────────────────────────────

    async def process_corpus(self, topic: str, documents: List[Dict[str, str]]) -> Dict:
        """
        Legacy entry point — enqueues documents and processes them immediately.
        Preserves backward compatibility with existing /ingest and /meditate endpoints.
        """
        started_at = perf_counter()
        logger.info(f"🚀 Starting corpus ingestion for topic: '{topic}' with {len(documents)} docs.")

        # Enqueue with cache check
        enqueue_result = self.enqueue_documents(topic, documents)
        logger.info(f"  📊 Enqueue result: {enqueue_result['queued']} queued, {enqueue_result['skipped']} skipped")

        if enqueue_result["queued"] == 0:
            progress_manager.broadcast(
                f"All {enqueue_result['skipped']} documents already cached. No changes needed.",
                100, "success", stage="complete", step="cached",
                topic=topic, documents_skipped=enqueue_result["skipped"],
            )
            return {
                "status": "success",
                "topic": topic,
                "documents_processed": 0,
                "documents_skipped": enqueue_result["skipped"],
                "pages_created": [],
                "pages_updated": [],
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            }

        # Process the queue
        result = await self.process_queue(topic)
        result["documents_skipped"] = enqueue_result["skipped"]
        return result

    def remove_wiki_page(self, filename: str) -> bool:
        path = os.path.join(self.wiki_dir, filename)
        if os.path.exists(path):
            os.remove(path)
            self._update_index([])
            self.git_manager.commit_changes(f"Delete wiki page: {filename}")
            return True
        return False
