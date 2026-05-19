"""
Token Search Service — Phase 1 lexical retrieval.

Scores wiki pages and source documents via:
  +1  per matching token
  +5  exact phrase match in content
  +10 title / filename match
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ─── Stop-words ────────────────────────────────────────────────────────

STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by",
    "do", "for", "from", "had", "has", "have", "how", "in", "into",
    "is", "it", "its", "not", "of", "on", "or", "that", "the", "their",
    "them", "there", "these", "they", "this", "those", "to", "was",
    "were", "what", "when", "where", "which", "who", "will", "with",
    "would", "you", "your",
})

SYSTEM_PAGES = frozenset({"index.md", "log.md", "SCHEMA.md", "purpose.md"})


# ─── Data Models ───────────────────────────────────────────────────────

@dataclass
class SearchHit:
    path: str                         # Absolute or relative file path
    title: str                        # Display title
    score: float                      # Combined lexical score
    matched_tokens: list[str]         # Which query tokens matched
    content: str                      # Full page content
    page_type: str = "wiki"           # "wiki" | "source"
    snippet: str = ""                 # Short extract for debugging


# ─── Tokenization ──────────────────────────────────────────────────────

def _has_cjk(text: str) -> bool:
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
                0x20000 <= cp <= 0x2A6DF or 0xF900 <= cp <= 0xFAFF):
            return True
    return False


def _cjk_bigrams(text: str) -> list[str]:
    """Generate CJK character bigrams for mixed-language retrieval."""
    cjk_chars = [
        ch for ch in text
        if 0x4E00 <= ord(ch) <= 0x9FFF or 0x3400 <= ord(ch) <= 0x4DBF
    ]
    return [cjk_chars[i] + cjk_chars[i + 1] for i in range(len(cjk_chars) - 1)]


def tokenize(text: str) -> list[str]:
    """
    Tokenize text into meaningful search terms.
    - Lowercases + strips punctuation
    - Removes stop-words
    - Adds CJK bigrams for mixed-language content
    """
    # Normalize unicode
    text = unicodedata.normalize("NFKC", text)
    lowered = text.lower()

    # Strip punctuation, keep hyphens inside words
    cleaned = re.sub(r"[^\w\s\-]", " ", lowered)
    tokens = [t.strip("-") for t in cleaned.split() if t.strip("-")]
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 1]

    if _has_cjk(text):
        tokens.extend(_cjk_bigrams(text))

    return tokens


# ─── File Loader ───────────────────────────────────────────────────────

def _read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def _title_from_path(path: str) -> str:
    stem = Path(path).stem
    return stem.replace("-", " ").replace("_", " ").title()


# ─── Scorer ────────────────────────────────────────────────────────────

def _score_document(
    query_tokens: list[str],
    raw_query: str,
    title: str,
    content: str,
) -> tuple[float, list[str]]:
    """Return (score, matched_tokens)."""
    content_lower = content.lower()
    title_lower = title.lower()
    raw_query_lower = raw_query.lower()

    matched: list[str] = []
    score = 0.0

    for token in query_tokens:
        if token in content_lower:
            score += 1.0
            matched.append(token)

    # Exact phrase bonus
    if len(raw_query_lower) > 3 and raw_query_lower in content_lower:
        score += 5.0

    # Title match bonus
    for token in query_tokens:
        if token in title_lower:
            score += 10.0
            if token not in matched:
                matched.append(token)

    return score, list(set(matched))


# ─── Search Service ────────────────────────────────────────────────────

class TokenSearchService:
    def search(
        self,
        query: str,
        wiki_dir: str,
        sources_dir: Optional[str] = None,
        top_k: int = 12,
    ) -> list[SearchHit]:
        """
        Lexical search across wiki pages and optionally source documents.
        Returns top_k results sorted by descending score.
        """
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        hits: list[SearchHit] = []

        # ── Wiki pages ──
        if os.path.isdir(wiki_dir):
            for fname in os.listdir(wiki_dir):
                if not fname.endswith(".md") or fname in SYSTEM_PAGES:
                    continue
                fpath = os.path.join(wiki_dir, fname)
                content = _read_file(fpath)
                if not content.strip():
                    continue
                title = _title_from_path(fpath)
                score, matched = _score_document(query_tokens, query, title, content)
                if score > 0:
                    hits.append(SearchHit(
                        path=fpath,
                        title=title,
                        score=score,
                        matched_tokens=matched,
                        content=content,
                        page_type="wiki",
                        snippet=content[:200].strip(),
                    ))

        # ── Source documents ──
        if sources_dir and os.path.isdir(sources_dir):
            for fname in os.listdir(sources_dir):
                if not fname.endswith((".md", ".txt")):
                    continue
                fpath = os.path.join(sources_dir, fname)
                content = _read_file(fpath)
                if not content.strip():
                    continue
                title = _title_from_path(fpath)
                score, matched = _score_document(query_tokens, query, title, content)
                if score > 0:
                    hits.append(SearchHit(
                        path=fpath,
                        title=title,
                        score=score,
                        matched_tokens=matched,
                        content=content,
                        page_type="source",
                        snippet=content[:200].strip(),
                    ))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]
