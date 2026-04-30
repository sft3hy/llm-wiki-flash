"""
The Librarian — Enhanced Lint Engine
Performs de-duplication, conflict detection, orphan detection, and link health checks.
"""

import os
import re
import yaml
from typing import List, Dict, Any
from langchain_core.prompts import ChatPromptTemplate

from core.llm_provider import get_llm
from core.schema import CLEANUP_PROMPT
import logging

logger = logging.getLogger("llm-wiki")


class LintEngine:
    def __init__(self, wiki_dir: str, model_id: str = None):
        self.wiki_dir = wiki_dir
        self.model_id = model_id

    def _get_all_pages(self) -> List[str]:
        """List all .md wiki pages (excluding system files)."""
        if not os.path.exists(self.wiki_dir):
            return []
        return [
            f for f in os.listdir(self.wiki_dir)
            if f.endswith(".md") and f not in ("SCHEMA.md",)
        ]

    def _read_page(self, filename: str) -> str:
        path = os.path.join(self.wiki_dir, filename)
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
        return ""

    def _extract_wikilinks(self, content: str) -> List[str]:
        """Extract all [[wikilink]] references from content."""
        return re.findall(r"\[\[(.*?)\]\]", content)

    def _parse_frontmatter(self, content: str) -> dict:
        """Parse YAML frontmatter from a wiki page."""
        try:
            if content.startswith("---"):
                end = content.index("---", 3)
                return yaml.safe_load(content[3:end]) or {}
        except (ValueError, yaml.YAMLError):
            pass
        return {}

    async def run_full_lint(self) -> Dict[str, Any]:
        """
        Run all lint checks and return a comprehensive report.
        """
        logger.info("🔍 Starting full wiki lint...")
        all_pages = self._get_all_pages()

        results = {
            "total_pages": len(all_pages),
            "broken_links": [],
            "orphan_pages": [],
            "conflicting_pages": [],
            "stub_pages": [],
            "missing_frontmatter": [],
            "oversized_pages": [],
            "duplicate_candidates": [],
            "suggestions": [],
        }

        # Build link graph
        inbound_links: Dict[str, List[str]] = {p: [] for p in all_pages}
        all_outbound: Dict[str, List[str]] = {}

        for page in all_pages:
            content = self._read_page(page)
            links = self._extract_wikilinks(content)
            all_outbound[page] = links

            # Check broken links
            for link in links:
                link_file = f"{link}.md"
                if link_file in all_pages:
                    inbound_links[link_file].append(page)
                else:
                    results["broken_links"].append({
                        "source": page,
                        "target": link,
                        "suggestion": f"Create page [[{link}]]",
                    })

            # Check frontmatter
            fm = self._parse_frontmatter(content)
            if not fm or "title" not in fm:
                results["missing_frontmatter"].append(page)

            # Check status
            status = fm.get("status", "")
            if status == "stub":
                results["stub_pages"].append(page)
            if status == "conflicting":
                results["conflicting_pages"].append(page)

            # Check for ## Conflict sections
            if "## Conflict" in content:
                if page not in results["conflicting_pages"]:
                    results["conflicting_pages"].append(page)

            # Check word count
            # Strip frontmatter for word count
            body = content
            if content.startswith("---"):
                try:
                    end = content.index("---", 3)
                    body = content[end + 3:]
                except ValueError:
                    pass
            word_count = len(body.split())
            if word_count > 1000:
                results["oversized_pages"].append({
                    "page": page,
                    "word_count": word_count,
                    "suggestion": f"Split into sub-pages (currently {word_count} words)",
                })

        # Check orphan pages (no inbound links, not index/log)
        for page, inbound in inbound_links.items():
            if page in ("index.md", "log.md", "SCHEMA.md"):
                continue
            if len(inbound) == 0:
                results["orphan_pages"].append(page)

        # Generate suggestions
        if results["broken_links"]:
            results["suggestions"].append(
                f"Create {len(results['broken_links'])} missing pages referenced by wikilinks"
            )
        if results["orphan_pages"]:
            results["suggestions"].append(
                f"Link to {len(results['orphan_pages'])} orphan pages from other pages or index.md"
            )
        if results["conflicting_pages"]:
            results["suggestions"].append(
                f"Review {len(results['conflicting_pages'])} pages with conflicts"
            )
        if results["oversized_pages"]:
            results["suggestions"].append(
                f"Refactor {len(results['oversized_pages'])} oversized pages (>1000 words)"
            )
        if results["stub_pages"]:
            results["suggestions"].append(
                f"Expand {len(results['stub_pages'])} stub pages with more content"
            )

        # Simple duplicate detection (title-based, no LLM needed)
        titles_seen: Dict[str, List[str]] = {}
        for page in all_pages:
            content = self._read_page(page)
            fm = self._parse_frontmatter(content)
            title = fm.get("title", page.replace(".md", "").replace("-", " ").lower())
            normalized = title.lower().strip()
            if normalized not in titles_seen:
                titles_seen[normalized] = []
            titles_seen[normalized].append(page)

        for title, pages in titles_seen.items():
            if len(pages) > 1:
                results["duplicate_candidates"].append({
                    "title": title,
                    "pages": pages,
                    "suggestion": f"Merge {', '.join(pages)} — they share the title '{title}'",
                })

        logger.info(f"✅ Lint complete: {len(results['broken_links'])} broken links, "
                     f"{len(results['orphan_pages'])} orphans, "
                     f"{len(results['conflicting_pages'])} conflicts")

        return results
