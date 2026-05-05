from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    query: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FetchedSource:
    title: str
    url: str
    snippet: str
    query: str
    raw_content: str
    cleaned_content: str
    content_type: str
    retrieval_timestamp: str
    last_updated: str | None = None
    source_id: str = ""
    raw_file: str = ""
    cleaned_file: str = ""
    metadata_file: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PipelineRunResult:
    topic: str
    topic_slug: str
    discovered_sources: int
    fetched_sources: int
    failed_sources: int
    source_notes_written: int
    concept_pages_written: int
    raw_sources_dir: str
    obsidian_sources_dir: str
    obsidian_wiki_dir: str
    log_path: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

