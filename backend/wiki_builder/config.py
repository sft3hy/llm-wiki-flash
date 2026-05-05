from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_QUERY_TEMPLATES = (
    "{topic}",
    "{topic} overview",
    "{topic} history",
    "{topic} key concepts",
    "{topic} applications",
)


@dataclass(slots=True)
class SearxngConfig:
    base_url: str
    language: str = "en"
    categories: str = "general"
    time_range: str | None = None


@dataclass(slots=True)
class GenericJSONSearchConfig:
    endpoint: str
    query_param: str = "q"
    results_path: tuple[str, ...] = ("results",)
    title_field: str = "title"
    url_field: str = "url"
    snippet_field: str = "snippet"
    extra_params: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class PipelineConfig:
    vault_path: Path
    workspace_id: str | None = None
    model_id: str | None = None
    data_root: Path = Path("data")
    logs_dir: Path = Path("logs")
    query_templates: tuple[str, ...] = DEFAULT_QUERY_TEMPLATES
    max_queries: int = 5
    results_per_query: int = 5
    source_limit: int = 15
    minimum_sources_warning: int = 3
    request_timeout_seconds: float = 20.0
    user_agent: str = "ai-wiki-builder/0.1"
    searxng: SearxngConfig | None = None
    fallback_search: GenericJSONSearchConfig | None = None

    def validate(self) -> None:
        if not self.vault_path:
            raise ValueError("A wiki storage root is required.")
        if not self.vault_path.is_absolute():
            raise ValueError("Vault path must be absolute.")
        if self.searxng is None and self.fallback_search is None:
            raise ValueError("Configure either SearXNG or a fallback search API.")
