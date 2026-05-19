"""
Budget Allocator — Phase 3 token budget control.

Allocates the available context window across wiki pages, chat history,
index, and system prompt. Trims lowest-ranked pages to stay within budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ─── Budget Constants ──────────────────────────────────────────────────

# Approximate token count from word count (1 token ≈ 0.75 words)
WORDS_PER_TOKEN = 0.75

DEFAULT_BUDGET_TOKENS = 8192

DEFAULT_ALLOCATION = {
    "wiki": 0.60,
    "history": 0.20,
    "index": 0.05,
    "system": 0.15,
}


# ─── Data Models ───────────────────────────────────────────────────────

@dataclass
class RetrievedPage:
    path: str
    title: str
    content: str
    combined_score: float
    page_type: str          # "wiki" | "source"
    token_count: int = 0
    truncated: bool = False


# ─── Helpers ───────────────────────────────────────────────────────────

def _word_count(text: str) -> int:
    return len(text.split())


def approx_tokens(text: str) -> int:
    """Fast approximation: words / 0.75."""
    return max(1, int(_word_count(text) / WORDS_PER_TOKEN))


def _extract_header(content: str) -> str:
    """Preserve the first heading + any YAML frontmatter block."""
    lines = content.splitlines()
    header_lines: list[str] = []
    in_frontmatter = False

    for line in lines:
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            header_lines.append(line)
            continue
        if in_frontmatter:
            header_lines.append(line)
            continue
        if line.startswith("#"):
            header_lines.append(line)
            break

    return "\n".join(header_lines)


def _truncate_to_tokens(content: str, max_tokens: int) -> tuple[str, bool]:
    """Truncate content to approximately max_tokens. Returns (content, was_truncated)."""
    words = content.split()
    max_words = int(max_tokens * WORDS_PER_TOKEN)
    if len(words) <= max_words:
        return content, False
    truncated = " ".join(words[:max_words]) + "\n\n*[content truncated for context budget]*"
    return truncated, True


# ─── Budget Allocator ──────────────────────────────────────────────────

class BudgetAllocator:
    def __init__(
        self,
        budget_tokens: int = DEFAULT_BUDGET_TOKENS,
        allocation: dict[str, float] | None = None,
    ):
        self.budget_tokens = budget_tokens
        self.allocation = allocation or DEFAULT_ALLOCATION

    @property
    def wiki_budget(self) -> int:
        return int(self.budget_tokens * self.allocation.get("wiki", 0.60))

    @property
    def history_budget(self) -> int:
        return int(self.budget_tokens * self.allocation.get("history", 0.20))

    def allocate(
        self,
        pages: list[Any],   # list of SearchHit | GraphHit with .path, .content, .score
        max_pages: int = 15,
    ) -> list[RetrievedPage]:
        """
        Select and (if needed) truncate pages to fit within the wiki context budget.

        Pages are sorted by combined_score descending — highest-value content
        consumes the budget first. Lowest-ranked pages are trimmed or truncated.
        """
        budget_remaining = self.wiki_budget
        result: list[RetrievedPage] = []

        # Sort by score descending
        sorted_pages = sorted(pages, key=lambda p: getattr(p, "score", 0), reverse=True)
        seen_paths: set[str] = set()

        for page in sorted_pages:
            if len(result) >= max_pages:
                break
            if page.path in seen_paths:
                continue
            seen_paths.add(page.path)

            token_count = approx_tokens(page.content)

            if token_count <= budget_remaining:
                # Full page fits
                result.append(RetrievedPage(
                    path=page.path,
                    title=page.title,
                    content=page.content,
                    combined_score=page.score,
                    page_type=getattr(page, "page_type", "wiki"),
                    token_count=token_count,
                    truncated=False,
                ))
                budget_remaining -= token_count
            elif budget_remaining > 100:
                # Partial fit — truncate
                header = _extract_header(page.content)
                available = max(budget_remaining - approx_tokens(header) - 20, 50)
                body = page.content[len(header):]
                truncated_body, _ = _truncate_to_tokens(body, available)
                final_content = header + "\n" + truncated_body
                final_tokens = approx_tokens(final_content)
                result.append(RetrievedPage(
                    path=page.path,
                    title=page.title,
                    content=final_content,
                    combined_score=page.score,
                    page_type=getattr(page, "page_type", "wiki"),
                    token_count=final_tokens,
                    truncated=True,
                ))
                budget_remaining -= final_tokens
            else:
                # Budget exhausted
                break

        return result

    def fits_history(self, history_text: str) -> str:
        """Trim chat history to the history budget."""
        content, _ = _truncate_to_tokens(history_text, self.history_budget)
        return content
