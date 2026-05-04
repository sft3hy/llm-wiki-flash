import os
import re
from typing import List, Dict, Tuple
import yaml
from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage

from core.llm_provider import get_llm, call_with_fallback, TaskComplexity
from core.schema import (
    COMPILER_SYSTEM_PROMPT,
    ENTITY_EXTRACTION_PROMPT,
    SYNTHESIS_PROMPT,
    FILTERING_PROMPT,
    LOG_ENTRY_FORMAT,
)
from config import settings
from utils.git_manager import GitManager
from utils.progress import progress_manager
from langchain_text_splitters import RecursiveCharacterTextSplitter
import asyncio
import logging
from core.query import QueryEngine

# Configure detailed logging
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
        self.model_id = model_id # If None, we use tiered logic
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(wiki_dir, exist_ok=True)

        self.git_manager = GitManager(wiki_dir)

        # Chunking strategy for large documents
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=200,
        )
        self.query_engine = QueryEngine(wiki_dir)

    async def _call_llm(self, messages: list, task_type: str) -> str:
        """Invoke the LLM with fallback logic."""
        result = await call_with_fallback(messages, task_type, model_id=self.model_id)
        if not result or not result.strip():
            logger.warning(f"  ⚠️ LLM returned empty result for {task_type}")
            return ""
        
        logger.info(f"    ✅ LLM returned {len(result)} chars for {task_type}: {result[:50]}...")
        return result

    def _get_existing_pages(self) -> List[str]:
        """List all .md files in the wiki directory."""
        if not os.path.exists(self.wiki_dir):
            return []
        return [f for f in os.listdir(self.wiki_dir) if f.endswith(".md") and f not in ("SCHEMA.md",)]

    def _read_wiki_page(self, filename: str) -> str:
        """Read the content of a wiki page."""
        path = os.path.join(self.wiki_dir, filename)
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
        return ""

    def _write_wiki_page(self, filename: str, content: str):
        """Write content to a wiki page."""
        path = os.path.join(self.wiki_dir, filename)
        abs_path = os.path.abspath(path)
        logger.info(f"    💾 Writing to: {abs_path}")
        with open(path, "w") as f:
            f.write(content)

    # ─── Step 0: Filtering ─────────────────────────────────────────────
    async def _filter_content(self, content: str) -> Tuple[bool, str]:
        """Check if content contains durable knowledge or ephemeral noise."""
        # For very short content, just let it through
        if len(content.strip()) < 50:
            return False, "Content too short to contain durable knowledge."

        prompt = FILTERING_PROMPT.format(content=content[:3000])
        messages = [HumanMessage(content=prompt)]
        result = await self._call_llm(messages, "filtering")

        is_durable = result.strip().upper().startswith("DURABLE")
        return is_durable, result.strip()

    # ─── Step 1: Entity Extraction ─────────────────────────────────────
    async def _extract_entities(self, content: str) -> List[Dict[str, str]]:
        """
        Extract entities/concepts from the raw document.
        Returns a list of dicts: {name, description, action}
        """
        existing_pages = self._get_existing_pages()
        existing_list = "\n".join(f"- {p}" for p in existing_pages) if existing_pages else "(no existing pages)"

        # If document is large, chunk it and extract from each chunk
        chunks = self.splitter.split_text(content)
        all_entities = []

        for i, chunk in enumerate(chunks):
            progress_pct = 10 + int((i / max(len(chunks), 1)) * 30)
            progress_manager.broadcast(f"Analyzing chunk {i+1}/{len(chunks)} for entities", progress_pct)
            logger.info(f"  🔍 Extracting entities from chunk {i+1}/{len(chunks)}")

            prompt = ENTITY_EXTRACTION_PROMPT.format(
                content=chunk,
                existing_pages=existing_list,
            )
            messages = [HumanMessage(content=prompt)]
            try:
                result = await self._call_llm(messages, "extraction")
            except Exception as e:
                logger.error(f"  ❌ Error extracting entities from chunk {i+1}: {e}")
                continue

            if not result:
                continue

            # Parse the structured response — handle multiple formats from small models
            for line in result.strip().split("\n"):
                line = line.strip()
                # Remove leading bullets/numbers: "- ", "1. ", "* "
                cleaned = re.sub(r'^[\-\*\d]+[\.\)\s]*\s*', '', line)
                # Remove ENTITY: prefix if present
                if cleaned.upper().startswith("ENTITY:"):
                    cleaned = cleaned[7:].strip()
                
                # Try to parse "name | description | action" format
                # More robust regex matching
                # Example: "ENTITY: some-name | some description | NEW" or just "- some-name | desc"
                match = re.search(r'([a-zA-Z0-9\-]+)\s*\|\s*(.*?)(?:\s*\|\s*(NEW|UPDATE))?$', cleaned, re.IGNORECASE)
                if match:
                    name = match.group(1).strip().lower()
                    description = match.group(2).strip()
                    action = match.group(3).strip().upper() if match.group(3) else "NEW"
                else:
                    parts = cleaned.split("|")
                    if len(parts) >= 2:
                        name = parts[0].strip().lower().replace(" ", "-")
                        name = re.sub(r'[^a-z0-9\-]', '', name)
                        description = parts[1].strip() if len(parts) > 1 else "" 
                        action = parts[2].strip().upper() if len(parts) > 2 else "NEW"
                    else:
                        continue

                if action not in ("NEW", "UPDATE"):
                    action = "NEW"
                    if name and len(name) > 1:
                        all_entities.append({
                            "name": name,
                            "description": description,
                            "action": action,
                        })

        # De-duplicate entities by name
        seen = set()
        unique_entities = []
        for entity in all_entities:
            if entity["name"] not in seen:
                seen.add(entity["name"])
                unique_entities.append(entity)

        logger.info(f"  📋 Extracted {len(unique_entities)} unique entities")
        return unique_entities

    # ─── Step 2: Multi-Page Synthesis ──────────────────────────────────
    async def _synthesize_page(
        self, entity: Dict[str, str], raw_content: str, source_id: str
    ) -> str:
        """Create or update a wiki page for a single entity."""
        filename = f"{entity['name']}.md"
        existing_content = self._read_wiki_page(filename)

        if existing_content:
            existing_content_section = f"EXISTING PAGE CONTENT (preserve and integrate):\n{existing_content}"
        else:
            existing_content_section = "This is a NEW page. Create it with proper YAML frontmatter."

        # Find a relevant chunk of the raw content (search for entity name)
        entity_terms = entity['name'].replace('-', ' ').split()
        relevant_chunk = ""
        paragraphs = raw_content.split('\n\n')
        for para in paragraphs:
            para_lower = para.lower()
            if any(term in para_lower for term in entity_terms):
                relevant_chunk += para + "\n\n"
                if len(relevant_chunk) > 3000:
                    break
        
        # Fallback: use the entity description + first 2000 chars
        if not relevant_chunk.strip():
            relevant_chunk = f"{entity['description']}\n\n{raw_content[:2000]}"

        # Synthesize the page
        messages = [
            SystemMessage(content=COMPILER_SYSTEM_PROMPT),
            HumanMessage(content=SYNTHESIS_PROMPT.format(
                entity_name=entity["name"].replace("-", " ").title(),
                existing_content_section=existing_content_section,
                source_id=source_id,
                new_information=relevant_chunk[:3000],
            )),
        ]

        page_content = await self._call_llm(messages, "synthesis")
        return page_content

    # ─── Step 3: Update Index ──────────────────────────────────────────
    def _update_index(self, pages_touched: Dict[str, str]):
        """Rebuild the index.md with all wiki pages."""
        index_path = os.path.join(self.wiki_dir, "index.md")
        all_pages = self._get_existing_pages()

        lines = ["# Wiki Index\n", "## Map of Content\n"]

        for page in sorted(all_pages):
            if page in ("index.md", "log.md", "SCHEMA.md"):
                continue
            # Try to extract title from frontmatter
            content = self._read_wiki_page(page)
            title = page.replace(".md", "").replace("-", " ").title()
            try:
                if content.startswith("---"):
                    fm_end = content.index("---", 3)
                    fm = yaml.safe_load(content[3:fm_end])
                    if fm and isinstance(fm, dict):
                        title = fm.get("title", title)
            except (ValueError, yaml.YAMLError):
                pass

            status = "updated" if page in pages_touched else ""
            marker = " ✨" if status else ""
            lines.append(f"- [[{page.replace('.md', '')}]] — {title}{marker}\n")

        with open(index_path, "w") as f:
            f.writelines(lines)

    # ─── Step 4: Update Log ────────────────────────────────────────────
    def _update_log(self, source_id: str, created: List[str], updated: List[str]):
        """Append an entry to log.md."""
        log_path = os.path.join(self.wiki_dir, "log.md")

        if not os.path.exists(log_path):
            with open(log_path, "w") as f:
                f.write("# Compilation Log\n\n")

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        created_str = ", ".join(f"[[{c}]]" for c in created) if created else "none"
        updated_str = ", ".join(f"[[{u}]]" for u in updated) if updated else "none"

        entry = LOG_ENTRY_FORMAT.format(
            date=now,
            source=source_id,
            created=created_str,
            updated=updated_str,
        )

        with open(log_path, "a") as f:
            f.write(entry)

    # ─── Main Process ──────────────────────────────────────────────────
    async def process_file(self, filename: str) -> Dict:
        """
        Full Compile-and-Maintain ingestion pipeline.
        Returns a summary of what was created/updated.
        """
        logger.info(f"🚀 Starting ingestion for: {filename} (model: {self.model_id})")
        progress_manager.broadcast(f"Starting ingestion for {filename}", 5)

        raw_path = os.path.join(self.raw_dir, filename)
        with open(raw_path, "r") as f:
            content = f.read()

        source_id = os.path.splitext(filename)[0]

        # Step 0: Filter for durable knowledge
        logger.info("🔬 Filtering content for durable knowledge...")
        progress_manager.broadcast("Analyzing content quality", 8)
        is_durable, filter_reason = await self._filter_content(content)

        if not is_durable:
            logger.info(f"⏭️ Content filtered as noise: {filter_reason}")
            progress_manager.broadcast("Content filtered as noise — skipping", 100, "success")
            self._update_log(source_id, [], [])
            return {
                "status": "filtered",
                "reason": filter_reason,
                "pages_created": [],
                "pages_updated": [],
            }

        # Step 1: Extract entities
        logger.info("🔍 Extracting entities from raw document...")
        progress_manager.broadcast("Extracting entities and concepts", 10)
        entities = await self._extract_entities(content)

        if not entities:
            logger.info("⚠️ No entities extracted — creating summary page as fallback")
            entities = [{
                "name": source_id,
                "description": f"Summary of {filename}",
                "action": "NEW",
            }]

        # Step 2: Multi-page synthesis
        created_pages = []
        updated_pages = []
        pages_touched = {}

        total_entities = len(entities)
        logger.info(f"📝 Synthesizing {total_entities} wiki pages...")

        for i, entity in enumerate(entities):
            pct = 40 + int((i / max(total_entities, 1)) * 45)
            page_name = f"{entity['name']}.md"
            action = "Creating" if entity["action"] == "NEW" else "Updating"
            msg = f"{action} {page_name} ({i+1}/{total_entities})"
            logger.info(f"  ✏️ {msg}")
            progress_manager.broadcast(msg, pct)

            try:
                page_content = await self._synthesize_page(entity, content, source_id)
                if page_content and page_content.strip():
                    existing = os.path.exists(os.path.join(self.wiki_dir, page_name))
                    self._write_wiki_page(page_name, page_content)
                    pages_touched[page_name] = entity["description"]

                    # Add to Chroma VectorStore
                    self.query_engine.add_documents(
                        chunks=[page_content],
                        metadatas=[{"source": page_name}]
                    )

                    if existing:
                        updated_pages.append(entity["name"])
                    else:
                        created_pages.append(entity["name"])
                    
                    # Periodic index update for better UI feedback
                    if (len(created_pages) + len(updated_pages)) % 5 == 0:
                        self._update_index(pages_touched)
            except Exception as e:
                logger.error(f"  ❌ Error synthesizing {page_name}: {e}")
                continue

        # Step 3: Update index
        logger.info("📇 Updating index.md...")
        progress_manager.broadcast("Updating index", 88)
        self._update_index(pages_touched)

        # Step 4: Update log
        logger.info("📋 Updating log.md...")
        progress_manager.broadcast("Writing compilation log", 90)
        self._update_log(source_id, created_pages, updated_pages)

        # Step 5: Git commit
        logger.info("📦 Committing to Git...")
        progress_manager.broadcast("Committing to Git", 95)
        if self.git_manager.commit_changes(f"Ingest: {filename} — {len(created_pages)} created, {len(updated_pages)} updated"):
            logger.info("  ✅ Changes committed")

        summary = {
            "status": "success",
            "source": filename,
            "model": self.model_id,
            "pages_created": created_pages,
            "pages_updated": updated_pages,
            "total_pages_touched": len(created_pages) + len(updated_pages),
        }

        logger.info(f"✅ Ingestion complete: {summary['total_pages_touched']} pages touched")
        progress_manager.broadcast(
            f"Complete! {len(created_pages)} created, {len(updated_pages)} updated",
            100,
            "success",
        )

        return summary

    def remove_wiki_page(self, filename: str) -> bool:
        """
        Delete a wiki page and update the index/git repo.
        """
        path = os.path.join(self.wiki_dir, filename)
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"🗑️ Deleted wiki page: {filename}")
            
            # Update index (pass empty dict as no pages were 'touched' by synthesis)
            self._update_index({})
            
            # Commit
            self.git_manager.commit_changes(f"Delete wiki page: {filename}")
            return True
        return False
