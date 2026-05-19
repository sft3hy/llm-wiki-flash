"""
Graph Expansion Service — Phase 2 retrieval.

Parses [[wiki-links]] from pages to build an adjacency graph,
then expands from seed hits with 2-hop traversal and decay weighting.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .token_search import SearchHit, _read_file, SYSTEM_PAGES

WIKI_LINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]")


# ─── Data Models ───────────────────────────────────────────────────────

@dataclass
class GraphHit:
    path: str
    title: str
    score: float          # Decayed score
    content: str
    page_type: str = "wiki"
    hop: int = 1          # 1 = direct neighbor, 2 = 2-hop


# ─── Graph Builder ─────────────────────────────────────────────────────

def _slug_from_link(link_text: str) -> str:
    """Normalise a [[Link Text]] to a filename slug."""
    return link_text.strip().lower().replace(" ", "-")


def _path_for_slug(slug: str, wiki_dir: str) -> Optional[str]:
    """Find the .md file for a slug (case-insensitive)."""
    candidates = [
        os.path.join(wiki_dir, f"{slug}.md"),
        os.path.join(wiki_dir, f"{slug.replace('-', '_')}.md"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    # Case-insensitive fallback
    try:
        for fname in os.listdir(wiki_dir):
            if fname.lower() == f"{slug}.md":
                return os.path.join(wiki_dir, fname)
    except OSError:
        pass
    return None


def build_graph(wiki_dir: str) -> dict[str, set[str]]:
    """
    Parse all wiki pages and build an adjacency dict.
    Returns: { page_path: {linked_page_path, ...} }
    """
    graph: dict[str, set[str]] = {}

    if not os.path.isdir(wiki_dir):
        return graph

    for fname in os.listdir(wiki_dir):
        if not fname.endswith(".md") or fname in SYSTEM_PAGES:
            continue
        page_path = os.path.join(wiki_dir, fname)
        content = _read_file(page_path)
        neighbors: set[str] = set()

        for match in WIKI_LINK_RE.finditer(content):
            slug = _slug_from_link(match.group(1))
            target = _path_for_slug(slug, wiki_dir)
            if target and target != page_path:
                neighbors.add(target)

        graph[page_path] = neighbors

    return graph


# ─── Expansion Service ─────────────────────────────────────────────────

class GraphExpansionService:
    def expand(
        self,
        seed_hits: list[SearchHit],
        wiki_dir: str,
        graph: Optional[dict[str, set[str]]] = None,
        max_hops: int = 2,
        max_pages: int = 10,
        decay: float = 0.5,
        min_score: float = 0.1,
    ) -> list[GraphHit]:
        """
        Expand from seed pages via wiki link graph.
        - 1-hop neighbors get seed_score × 1.0
        - 2-hop neighbors get seed_score × decay (default 0.5)
        Returns new pages not already in the seed set.
        """
        if graph is None:
            graph = build_graph(wiki_dir)

        seed_paths = {h.path for h in seed_hits}
        # Map path → best seed score (for seeding expansion weight)
        seed_scores: dict[str, float] = {}
        for h in seed_hits:
            if h.path not in seed_scores or h.score > seed_scores[h.path]:
                seed_scores[h.path] = h.score

        # Accumulate scores for expanded pages
        expanded_scores: dict[str, float] = {}
        expanded_hop: dict[str, int] = {}

        # Hop 1 — direct neighbors of seeds
        for seed_path, seed_score in seed_scores.items():
            for neighbor in graph.get(seed_path, set()):
                if neighbor in seed_paths:
                    continue
                contribution = seed_score * 1.0
                if contribution > expanded_scores.get(neighbor, 0):
                    expanded_scores[neighbor] = contribution
                    expanded_hop[neighbor] = 1

        if max_hops >= 2:
            # Hop 2 — neighbors of neighbors
            hop1_paths = set(expanded_scores.keys())
            for hop1_path in hop1_paths:
                hop1_score = expanded_scores[hop1_path]
                for neighbor in graph.get(hop1_path, set()):
                    if neighbor in seed_paths or neighbor in hop1_paths:
                        continue
                    contribution = hop1_score * decay
                    if contribution > expanded_scores.get(neighbor, 0):
                        expanded_scores[neighbor] = contribution
                        expanded_hop[neighbor] = 2

        # Filter, sort, load content
        ranked = sorted(expanded_scores.items(), key=lambda x: x[1], reverse=True)
        hits: list[GraphHit] = []

        for path, score in ranked:
            if score < min_score:
                break
            if len(hits) >= max_pages:
                break
            content = _read_file(path)
            if not content.strip():
                continue
            title = Path(path).stem.replace("-", " ").replace("_", " ").title()
            hits.append(GraphHit(
                path=path,
                title=title,
                score=score,
                content=content,
                page_type="wiki",
                hop=expanded_hop.get(path, 1),
            ))

        return hits
