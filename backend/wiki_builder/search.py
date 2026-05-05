from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import GenericJSONSearchConfig, PipelineConfig, SearxngConfig
from .models import SearchResult
from .utils import canonicalize_url, normalize_whitespace


class SearchBackend(Protocol):
    def search(self, query: str, max_results: int) -> list[SearchResult]:
        ...


def generate_search_queries(
    topic: str,
    templates: tuple[str, ...],
    max_queries: int,
) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for template in templates:
        query = normalize_whitespace(template.format(topic=topic))
        lowered = query.lower()
        if lowered and lowered not in seen:
            seen.add(lowered)
            queries.append(query)
        if len(queries) >= max_queries:
            break
    return queries


def deduplicate_results(results: list[SearchResult], limit: int) -> list[SearchResult]:
    deduplicated: list[SearchResult] = []
    seen_urls: set[str] = set()
    for result in results:
        normalized_url = canonicalize_url(result.url)
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        deduplicated.append(
            SearchResult(
                title=normalize_whitespace(result.title),
                url=normalized_url,
                snippet=normalize_whitespace(result.snippet),
                query=result.query,
            )
        )
        if len(deduplicated) >= limit:
            break
    return deduplicated


def _read_json(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


@dataclass(slots=True)
class SearxngSearchClient:
    config: SearxngConfig
    timeout: float
    user_agent: str

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        params = {
            "q": query,
            "format": "json",
            "language": self.config.language,
            "categories": self.config.categories,
        }
        if self.config.time_range:
            params["time_range"] = self.config.time_range
        url = f"{self.config.base_url.rstrip('/')}/search?{urlencode(params)}"
        payload = _read_json(
            url,
            {
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "X-Forwarded-For": "127.0.0.1",
                "X-Real-IP": "127.0.0.1",
            },
            self.timeout,
        )
        items = payload.get("results", [])
        results: list[SearchResult] = []
        for item in items[:max_results]:
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", "") or item.get("snippet", ""),
                    query=query,
                )
            )
        return results


@dataclass(slots=True)
class GenericJSONSearchClient:
    config: GenericJSONSearchConfig
    timeout: float
    user_agent: str

    def _select_path(self, payload: dict[str, Any], path: tuple[str, ...]) -> Any:
        current: Any = payload
        for segment in path:
            if not isinstance(current, dict):
                return []
            current = current.get(segment, [])
        return current

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        params = {self.config.query_param: query, **self.config.extra_params}
        url = f"{self.config.endpoint}?{urlencode(params)}"
        headers = {"User-Agent": self.user_agent, **self.config.headers}
        payload = _read_json(url, headers, self.timeout)
        items = self._select_path(payload, self.config.results_path)
        if not isinstance(items, list):
            return []
        results: list[SearchResult] = []
        for item in items[:max_results]:
            if not isinstance(item, dict):
                continue
            results.append(
                SearchResult(
                    title=str(item.get(self.config.title_field, "")),
                    url=str(item.get(self.config.url_field, "")),
                    snippet=str(item.get(self.config.snippet_field, "")),
                    query=query,
                )
            )
        return results


class SearchService:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.primary: SearchBackend | None = None
        self.fallback: SearchBackend | None = None
        if config.searxng:
            self.primary = SearxngSearchClient(
                config=config.searxng,
                timeout=config.request_timeout_seconds,
                user_agent=config.user_agent,
            )
        if config.fallback_search:
            self.fallback = GenericJSONSearchClient(
                config=config.fallback_search,
                timeout=config.request_timeout_seconds,
                user_agent=config.user_agent,
            )

    def discover(self, topic: str) -> list[SearchResult]:
        queries = generate_search_queries(topic, self.config.query_templates, self.config.max_queries)
        aggregated: list[SearchResult] = []
        for query in queries:
            results: list[SearchResult] = []
            last_error: Exception | None = None
            for backend in (self.primary, self.fallback):
                if backend is None:
                    continue
                try:
                    results = backend.search(query, self.config.results_per_query)
                    if results:
                        break
                except Exception as error:
                    last_error = error
            if not results and last_error is not None:
                raise last_error
            aggregated.extend(results)
        return deduplicate_results(aggregated, self.config.source_limit)
