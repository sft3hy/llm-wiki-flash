"""
Context Assembly Service — Phase 4.

Builds a deterministic, citation-numbered LLM context block from
retrieved pages. Each page is numbered [1], [2], ... for in-response citation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .budget import RetrievedPage


# ─── Data Models ───────────────────────────────────────────────────────

@dataclass
class AssembledContext:
    context_str: str                     # Final context block for the LLM
    citation_map: dict[int, str]         # { 1: "path/to/page.md", ... }
    page_count: int
    total_tokens: int


# ─── Assembly Service ──────────────────────────────────────────────────

class ContextAssemblyService:
    def assemble(
        self,
        pages: list[RetrievedPage],
        purpose_content: str = "",
        index_content: str = "",
    ) -> AssembledContext:
        """
        Build the final context block for injection into the LLM system prompt.

        Structure:
            [Purpose]
            [Index]
            [1] path/to/page.md
            <content>
            ...
        """
        from .budget import approx_tokens

        parts: list[str] = []
        citation_map: dict[int, str] = {}
        total_tokens = 0

        # ── Purpose ──
        if purpose_content and purpose_content.strip():
            parts.append(f"## Wiki Purpose\n\n{purpose_content.strip()}")
            total_tokens += approx_tokens(purpose_content)

        # ── Index (table of contents) ──
        if index_content and index_content.strip():
            parts.append(f"## Wiki Index\n\n{index_content.strip()}")
            total_tokens += approx_tokens(index_content)

        # ── Retrieved Pages ──
        for idx, page in enumerate(pages, start=1):
            citation_map[idx] = page.path
            relative_path = _display_path(page.path)
            truncation_note = " *(truncated)*" if page.truncated else ""
            header = f"[{idx}] {relative_path}{truncation_note}"
            block = f"{header}\n\n{page.content.strip()}"
            parts.append(block)
            total_tokens += page.token_count

        context_str = "\n\n---\n\n".join(parts)

        return AssembledContext(
            context_str=context_str,
            citation_map=citation_map,
            page_count=len(pages),
            total_tokens=total_tokens,
        )

    def build_citation_instructions(self, citation_map: dict[int, str]) -> str:
        """Return a short instruction block telling the LLM how to cite sources."""
        if not citation_map:
            return ""
        entries = "\n".join(
            f"  [{n}] {_display_path(path)}"
            for n, path in sorted(citation_map.items())
        )
        return (
            "CITATION RULES:\n"
            "When referencing specific information, cite sources using [N] notation.\n"
            "Available sources:\n"
            f"{entries}\n"
            "Example: 'Energy grids operate at high voltage [1][3].'"
        )


def _display_path(path: str) -> str:
    """Return a short relative-looking display path."""
    # Normalise to forward slashes and take the last 2 segments
    parts = path.replace("\\", "/").split("/")
    meaningful = [p for p in parts if p not in ("", ".", "..")]
    if len(meaningful) >= 2:
        return "/".join(meaningful[-2:])
    return parts[-1] if parts else path
