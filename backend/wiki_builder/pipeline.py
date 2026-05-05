from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .config import PipelineConfig
from .fetch import PageFetcher
from .logging_utils import PipelineLogger
from .models import FetchedSource, PipelineRunResult, SearchResult
from .obsidian import ObsidianWriter
from .search import SearchService
from .utils import ensure_directory, slugify
from .wiki import WikiGenerator


class PipelineRunner:
    def __init__(self, config: PipelineConfig, progress_callback: Callable[..., None] | None = None):
        self.config = config
        self.progress_callback = progress_callback
        self.config.validate()

    def _emit(self, stage: str, message: str, progress: int, status: str = "processing", **context) -> None:
        if self.progress_callback is None:
            return
        self.progress_callback(stage=stage, message=message, progress=progress, status=status, **context)

    def _topic_paths(self, topic: str) -> tuple[str, Path, Path, Path, Path]:
        topic_slug = self.config.workspace_id or slugify(topic)
        topic_root = ensure_directory(self.config.vault_path / topic_slug)
        raw_dir = ensure_directory(topic_root / "sources")
        log_path = topic_root / "pipeline.log"
        sources_dir = ensure_directory(topic_root / "sources")
        wiki_dir = ensure_directory(topic_root / "wiki")
        return topic_slug, raw_dir, log_path, sources_dir, wiki_dir

    def discover_sources(self, topic: str, logger: PipelineLogger) -> list[SearchResult]:
        logger.log("search", True, "Starting source discovery", topic=topic)
        self._emit("search", f"Generating search queries for {topic}", 8, topic=topic)
        service = SearchService(self.config)
        results = service.discover(topic)
        logger.log("search", True, "Completed source discovery", topic=topic, count=len(results))
        self._emit("search", f"Discovered {len(results)} unique sources", 22, topic=topic, count=len(results))
        return results

    def fetch_sources(self, topic: str, results: list[SearchResult], raw_dir: Path, logger: PipelineLogger) -> tuple[list[FetchedSource], int]:
        logger.log("fetch", True, "Starting content acquisition", topic=topic, count=len(results))
        self._emit("fetch", f"Fetching {len(results)} sources", 28, topic=topic, count=len(results))
        for existing_file in raw_dir.iterdir():
            if existing_file.is_file():
                existing_file.unlink()
        fetcher = PageFetcher(raw_root=raw_dir, timeout=self.config.request_timeout_seconds, user_agent=self.config.user_agent)
        fetched: list[FetchedSource] = []
        failures = 0
        total = max(len(results), 1)
        for index, result in enumerate(results):
            try:
                source = fetcher.fetch(topic, result)
                fetched.append(source)
                logger.log("fetch", True, "Fetched source", url=result.url, source_id=source.source_id)
                logger.log("parse", True, "Extracted cleaned content", url=result.url, characters=len(source.cleaned_content))
                progress = 28 + int(((index + 1) / total) * 36)
                self._emit("fetch", f"Fetched {source.title}", progress, topic=topic, url=result.url, source_id=source.source_id)
            except Exception as error:
                failures += 1
                logger.log("fetch", False, "Failed to fetch source", url=result.url, error=str(error))
                progress = 28 + int(((index + 1) / total) * 36)
                self._emit("fetch", f"Skipped a source after a fetch failure", progress, topic=topic, url=result.url, error=str(error))
        manifest_path = raw_dir / "sources.json"
        manifest_path.write_text(json.dumps([item.to_dict() for item in fetched], indent=2), encoding="utf-8")
        logger.log("fetch", True, "Stored source manifest", path=str(manifest_path), count=len(fetched))
        self._emit("parse", f"Prepared {len(fetched)} cleaned source documents", 66, topic=topic, count=len(fetched), failures=failures)
        return fetched, failures

    def ingest_sources(self, topic: str, sources: list[FetchedSource], logger: PipelineLogger) -> list[Path]:
        logger.log("ingest", True, "Writing source notes to the vault", topic=topic, count=len(sources))
        self._emit("ingest", f"Writing {len(sources)} source notes into the vault", 74, topic=topic, count=len(sources))
        writer = ObsidianWriter(self.config.vault_path)
        note_paths = writer.write_source_notes(topic, sources, workspace_id=self.config.workspace_id)
        logger.log("ingest", True, "Completed source note ingestion", count=len(note_paths))
        self._emit("ingest", f"Stored {len(note_paths)} source notes", 84, topic=topic, count=len(note_paths))
        return note_paths

    def generate_wiki(self, topic: str, sources: list[FetchedSource], logger: PipelineLogger) -> list[Path]:
        logger.log("generate", True, "Generating concept wiki", topic=topic, count=len(sources))
        self._emit("generate", "Synthesizing concept pages and cross-links", 90, topic=topic, count=len(sources))
        generator = WikiGenerator(self.config.vault_path, model_id=self.config.model_id)
        page_paths = generator.write_wiki(topic, sources, workspace_id=self.config.workspace_id)
        logger.log("generate", True, "Completed concept wiki generation", count=len(page_paths))
        self._emit("generate", f"Generated {len(page_paths)} wiki files", 97, topic=topic, count=len(page_paths))
        return page_paths

    def run_pipeline(self, topic: str) -> PipelineRunResult:
        topic_slug, raw_dir, log_path, sources_dir, wiki_dir = self._topic_paths(topic)
        logger = PipelineLogger(log_path)
        warnings: list[str] = []
        results = self.discover_sources(topic, logger)
        if len(results) < self.config.minimum_sources_warning:
            warning = f"Only discovered {len(results)} sources for topic '{topic}'."
            warnings.append(warning)
            logger.log("search", True, "Discovered fewer sources than recommended", warning=warning)
            self._emit("search", warning, 24, topic=topic, warning=warning)
        fetched, failures = self.fetch_sources(topic, results, raw_dir, logger)
        note_paths = self.ingest_sources(topic, fetched, logger)
        wiki_paths = self.generate_wiki(topic, fetched, logger)
        logger.log("generate", True, "Pipeline finished", topic=topic, warnings=warnings)
        self._emit("generate", f"Finished building wiki for {topic}", 100, status="success", topic=topic, warnings=warnings)
        concept_pages = [path for path in wiki_paths if path.name != "index.md"]
        return PipelineRunResult(
            topic=topic,
            topic_slug=topic_slug,
            discovered_sources=len(results),
            fetched_sources=len(fetched),
            failed_sources=failures,
            source_notes_written=len(note_paths),
            concept_pages_written=len(concept_pages),
            raw_sources_dir=str(raw_dir),
            obsidian_sources_dir=str(sources_dir),
            obsidian_wiki_dir=str(wiki_dir),
            log_path=str(log_path),
            warnings=warnings,
        )
