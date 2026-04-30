import os
import re
from typing import List, Dict, Tuple
import yaml
from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage

from core.llm_provider import get_llm
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
        self.model_id = model_id or settings.DEFAULT_MODEL
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(wiki_dir, exist_ok=True)

        self.git_manager = GitManager(wiki_dir)

        # Get LLM via provider factory
        self.llm = get_llm(self.model_id)

        # Chunking strategy for large documents
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=6000,
            chunk_overlap=300,
        )

    async def _call_llm(self, messages: list) -> str:
        """Invoke the LLM with a list of messages and return the content string."""
        response = await self.llm.ainvoke(messages)
        return response.content

    async def _call_chain(self, chain, inputs: dict) -> str:
        """Invoke a LangChain chain (prompt | llm) and return the content string."""
        response = await chain.ainvoke(inputs)
        return response.content

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
        with open(path, "w") as f:
            f.write(content)

    # ─── Step 0: Filtering ─────────────────────────────────────────────
    async def _filter_content(self, content: str) -> Tuple[bool, str]:
        """Check if content contains durable knowledge or ephemeral noise."""
        # For very short content, just let it through
        if len(content.strip()) < 50:
            return False, "Content too short to contain durable knowledge."

        prompt = ChatPromptTemplate.from_template(FILTERING_PROMPT)
        chain = prompt | self.llm
        result = await self._call_chain(chain, {"content": content[:3000]})

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

            prompt = ChatPromptTemplate.from_template(ENTITY_EXTRACTION_PROMPT)
            chain = prompt | self.llm
            result = await self._call_chain(chain, {
                "content": chunk,
                "existing_pages": existing_list,
            })

            # Parse the structured response
            for line in result.strip().split("\n"):
                line = line.strip()
                if line.upper().startswith("ENTITY:"):
                    parts = line[7:].strip().split("|")
                    if len(parts) >= 3:
                        name = parts[0].strip().lower().replace(" ", "-")
                        # Clean up the name: remove .md if present, ensure kebab-case
                        name = re.sub(r'[^a-z0-9\-]', '', name)
                        if name:
                            all_entities.append({
                                "name": name,
                                "description": parts[1].strip(),
                                "action": parts[2].strip().upper(),
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

        # Extract relevant sections from raw content for this entity
        # Use the LLM to find the relevant portions
        extract_prompt = ChatPromptTemplate.from_template(
            """Extract the portions of this document that are relevant to the concept "{entity_name}": {entity_description}

Document:
{content}

Return only the relevant text, preserving important details. If nothing is relevant, say "NO_RELEVANT_CONTENT"."""
        )
        chain = extract_prompt | self.llm
        relevant_info = await self._call_chain(chain, {
            "entity_name": entity["name"].replace("-", " "),
            "entity_description": entity["description"],
            "content": raw_content[:8000],  # Limit context window
        })

        if "NO_RELEVANT_CONTENT" in relevant_info.upper():
            return ""

        # Now synthesize the page
        messages = [
            SystemMessage(content=COMPILER_SYSTEM_PROMPT),
            HumanMessage(content=SYNTHESIS_PROMPT.format(
                entity_name=entity["name"].replace("-", " ").title(),
                existing_content_section=existing_content_section,
                source_id=source_id,
                new_information=relevant_info,
            )),
        ]

        page_content = await self._call_llm(messages)
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

                    if existing:
                        updated_pages.append(entity["name"])
                    else:
                        created_pages.append(entity["name"])
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
