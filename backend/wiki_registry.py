from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.query import QueryEngine
from wiki_builder.utils import ensure_directory, slugify


SYSTEM_PAGES = {"index.md", "log.md", "SCHEMA.md", "purpose.md"}
EMBED_CHUNK_SIZE = 1200
EMBED_CHUNK_OVERLAP = 150
DEFAULT_INDEX_CONTENT = "# Wiki Index\n## Map of Content\n"
DEFAULT_LOG_CONTENT = "# Compilation Log\n\n"
DEFAULT_PURPOSE_CONTENT = "# Wiki Purpose\n\nDefines goals, key questions, research scope, and evolving thesis.\n"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def wiki_id_from_name(name: str) -> str:
    return slugify(name).replace("-", "_")


@dataclass(slots=True)
class WikiPaths:
    wiki_id: str
    root_dir: Path
    sources_dir: Path
    wiki_dir: Path
    embeddings_dir: Path
    metadata_file: Path
    log_file: Path


class WikiRegistry:
    def __init__(
        self,
        wikis_root: Path,
        legacy_raw_dir: Path,
        legacy_wiki_dir: Path,
        canonical_schema_path: Path | None = None,
        canonical_purpose_path: Path | None = None,
        legacy_index_template_path: Path | None = None,
        legacy_log_template_path: Path | None = None,
    ):
        self.wikis_root = Path(wikis_root)
        self.legacy_raw_dir = Path(legacy_raw_dir)
        self.legacy_wiki_dir = Path(legacy_wiki_dir)
        self.canonical_schema_path = Path(canonical_schema_path) if canonical_schema_path else self.legacy_wiki_dir / "SCHEMA.md"
        self.canonical_purpose_path = Path(canonical_purpose_path) if canonical_purpose_path else self.legacy_wiki_dir / "purpose.md"
        self.legacy_index_template_path = Path(legacy_index_template_path) if legacy_index_template_path else self.legacy_wiki_dir / "index.md"
        self.legacy_log_template_path = Path(legacy_log_template_path) if legacy_log_template_path else self.legacy_wiki_dir / "log.md"
        ensure_directory(self.wikis_root)
        self._migrate_legacy_data()

    def default_wiki_id(self) -> str | None:
        wikis = self.list_wikis()
        return wikis[0]["wiki_id"] if wikis else None

    def resolve_wiki_id(self, wiki_id: str | None) -> str:
        resolved = wiki_id or self.default_wiki_id()
        if not resolved:
            created = self.create_wiki("Main Wiki")
            return created["wiki_id"]
        return resolved

    def get_paths(self, wiki_id: str) -> WikiPaths:
        root_dir = self.wikis_root / wiki_id
        return WikiPaths(
            wiki_id=wiki_id,
            root_dir=root_dir,
            sources_dir=root_dir / "sources",
            wiki_dir=root_dir / "wiki",
            embeddings_dir=root_dir / "embeddings",
            metadata_file=root_dir / "metadata.json",
            log_file=root_dir / "pipeline.log",
        )

    def create_wiki(self, name: str, wiki_id: str | None = None, models: dict[str, Any] | None = None) -> dict[str, Any]:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Wiki name is required.")
        normalized_id = wiki_id_from_name(clean_name) if wiki_id is None else wiki_id
        paths = self.get_paths(normalized_id)
        if paths.root_dir.exists():
            self._ensure_wiki_scaffold(paths)
            metadata = self._read_metadata(paths)
            return self._serialize_wiki(paths, metadata)

        ensure_directory(paths.root_dir)
        ensure_directory(paths.sources_dir)
        ensure_directory(paths.wiki_dir)
        ensure_directory(paths.embeddings_dir)
        self._ensure_wiki_scaffold(paths)
        metadata = {
            "wiki_id": normalized_id,
            "name": clean_name,
            "created_at": _timestamp(),
            "last_updated": _timestamp(),
            "models": models or {},
        }
        self._write_metadata(paths, metadata)
        return self._serialize_wiki(paths, metadata)

    def delete_wiki(self, wiki_id: str) -> None:
        paths = self.get_paths(wiki_id)
        if not paths.root_dir.exists():
            raise FileNotFoundError(wiki_id)
        shutil.rmtree(paths.root_dir)

    def rename_wiki(self, wiki_id: str, name: str) -> dict[str, Any]:
        paths = self.get_paths(wiki_id)
        metadata = self._read_metadata(paths)
        metadata["name"] = name.strip() or metadata["name"]
        metadata["last_updated"] = _timestamp()
        self._write_metadata(paths, metadata)
        return self._serialize_wiki(paths, metadata)

    def update_models(self, wiki_id: str, models: dict[str, Any]) -> dict[str, Any]:
        paths = self.get_paths(wiki_id)
        metadata = self._read_metadata(paths)
        metadata["models"] = {**metadata.get("models", {}), **models}
        metadata["last_updated"] = _timestamp()
        self._write_metadata(paths, metadata)
        return self._serialize_wiki(paths, metadata)

    def touch(self, wiki_id: str) -> None:
        paths = self.get_paths(wiki_id)
        metadata = self._read_metadata(paths)
        metadata["last_updated"] = _timestamp()
        self._write_metadata(paths, metadata)

    def list_wikis(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for root in sorted(self.wikis_root.iterdir()) if self.wikis_root.exists() else []:
            if not root.is_dir():
                continue
            paths = self.get_paths(root.name)
            self._ensure_wiki_scaffold(paths)
            metadata = self._read_metadata(paths)
            items.append(self._serialize_wiki(paths, metadata))
        return sorted(items, key=lambda item: item.get("last_updated") or "", reverse=True)

    def load_wiki(self, wiki_id: str) -> dict[str, Any]:
        paths = self.get_paths(wiki_id)
        if not paths.root_dir.exists():
            raise FileNotFoundError(wiki_id)
        self._ensure_wiki_scaffold(paths)
        metadata = self._read_metadata(paths)
        payload = self._serialize_wiki(paths, metadata)
        payload["pages"] = self.list_pages(wiki_id)
        payload["sources"] = self.list_sources(wiki_id)
        return payload

    def list_pages(self, wiki_id: str) -> list[dict[str, Any]]:
        paths = self.get_paths(wiki_id)
        pages: list[dict[str, Any]] = []
        if not paths.wiki_dir.exists():
            return pages

        # First pass: collect pages and their explicit links
        page_contents: dict[str, str] = {}
        for file_path in sorted(paths.wiki_dir.glob("*.md")):
            content = file_path.read_text(encoding="utf-8")
            page_contents[file_path.name] = content

            links = set()
            for match in re.findall(r"\[\[(.*?)\]\]", content):
                link_target = match.split("|", 1)[0].strip()
                if not link_target.startswith("sources/"):
                    target_name = f"{link_target}.md" if not link_target.endswith(".md") else link_target
                    links.add(target_name)
                    
            for match in re.findall(r"\[.*?\]\((.*?)\)", content):
                link_target = match.strip()
                if link_target.startswith("wiki://"):
                    target_name = link_target.replace("wiki://", "")
                    target_name = f"{target_name}.md" if not target_name.endswith(".md") else target_name
                    links.add(target_name)
                elif not link_target.startswith("http") and not link_target.startswith("source://") and not link_target.startswith("#") and not link_target.startswith("mailto:") and not link_target.startswith("tel:"):
                    target_name = f"{link_target}.md" if not link_target.endswith(".md") else link_target
                    links.add(target_name)

            pages.append(
                {
                    "name": file_path.name,
                    "title": file_path.stem.replace("-", " ").title(),
                    "links": list(links)
                }
            )

        # Second pass: detect implicit content-based cross-references
        # If page A's body text mentions page B's slug (humanized), add a link.
        all_names = {p["name"] for p in pages}
        system_names = {"SCHEMA.md", "index.md", "log.md", "purpose.md"}
        content_pages = [p for p in pages if p["name"] not in system_names]

        for page in content_pages:
            content_lower = page_contents.get(page["name"], "").lower()
            existing_links = set(page["links"])
            for other in content_pages:
                if other["name"] == page["name"]:
                    continue
                if other["name"] in existing_links:
                    continue
                other_slug = other["name"].replace(".md", "")
                other_human = other_slug.replace("-", " ")
                # Check if the other page's humanized slug appears in this page's content
                if other_human in content_lower:
                    page["links"].append(other["name"])

        return pages

    def list_sources(self, wiki_id: str) -> list[dict[str, Any]]:
        paths = self.get_paths(wiki_id)
        sources: list[dict[str, Any]] = []
        if not paths.sources_dir.exists():
            return sources
        for file_path in sorted(paths.sources_dir.iterdir()):
            if file_path.suffix not in {".md", ".txt", ".html"}:
                continue
            if "__metadata" in file_path.name or "__raw" in file_path.name or "__cleaned" in file_path.name:
                continue
            preview = file_path.read_text(encoding="utf-8", errors="ignore")
            sources.append(
                {
                    "name": file_path.name,
                    "title": file_path.stem.replace("-", " ").title(),
                    "snippet": preview[:240],
                }
            )
        return sources

    def validate_wiki(self, wiki_id: str) -> dict[str, Any]:
        paths = self.get_paths(wiki_id)
        metadata = self._read_metadata(paths)
        missing = [
            label for label, path in (
                ("sources", paths.sources_dir),
                ("wiki", paths.wiki_dir),
                ("embeddings", paths.embeddings_dir),
                ("metadata", paths.metadata_file),
            ) if not path.exists()
        ]
        pages = self.list_pages(wiki_id)
        page_names = {page["name"].replace(".md", "") for page in pages}
        broken_links = []
        for page in pages:
            if page["name"] in ("SCHEMA.md", "purpose.md"):
                continue
            content = (paths.wiki_dir / page["name"]).read_text(encoding="utf-8")
            for match in re.findall(r"\[\[(.*?)\]\]", content):
                link_target = match.split("|", 1)[0].strip()
                if link_target.startswith("sources/"):
                    source_target = f"{link_target.split('/', 1)[1]}.md"
                    if not (paths.sources_dir / source_target).exists():
                        broken_links.append({"source": page["name"], "target": link_target})
                    continue
                if link_target not in page_names:
                    broken_links.append({"source": page["name"], "target": link_target})
        return {
            "wiki_id": wiki_id,
            "name": metadata.get("name", wiki_id),
            "missing": missing,
            "broken_links": broken_links,
            "page_count": len(pages),
            "source_count": len(self.list_sources(wiki_id)),
            "embeddings_present": paths.embeddings_dir.exists() and any(paths.embeddings_dir.iterdir()),
        }

    def rebuild_embeddings(self, wiki_id: str) -> dict[str, Any]:
        paths = self.get_paths(wiki_id)
        if paths.embeddings_dir.exists():
            shutil.rmtree(paths.embeddings_dir)
        ensure_directory(paths.embeddings_dir)

        query_engine = QueryEngine(str(paths.wiki_dir), embeddings_dir=str(paths.embeddings_dir))
        indexed_documents = 0

        for file_path in sorted(paths.sources_dir.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.suffix not in {".md", ".txt", ".html"}:
                continue
            if file_path.name.endswith("__metadata.json") or "__raw" in file_path.name:
                continue
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                continue
            chunks = self._chunk_text(content)
            query_engine.add_documents(
                chunks=chunks,
                metadatas=[{"source": file_path.name, "type": "source"} for _ in chunks],
            )
            indexed_documents += 1

        for file_path in sorted(paths.wiki_dir.glob("*.md")):
            if file_path.name in SYSTEM_PAGES:
                continue
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                continue
            chunks = self._chunk_text(content)
            query_engine.add_documents(
                chunks=chunks,
                metadatas=[{"source": file_path.name, "type": "wiki_page"} for _ in chunks],
            )
            indexed_documents += 1

        self.touch(wiki_id)
        return {
            "status": "success",
            "wiki_id": wiki_id,
            "indexed_documents": indexed_documents,
            "embeddings_dir": str(paths.embeddings_dir),
        }



    def _chunk_text(self, content: str) -> list[str]:
        if not content:
            return []
        step = EMBED_CHUNK_SIZE - EMBED_CHUNK_OVERLAP
        return [content[i:i + EMBED_CHUNK_SIZE] for i in range(0, len(content), step)] or [content]

    def _read_metadata(self, paths: WikiPaths) -> dict[str, Any]:
        if not paths.metadata_file.exists():
            metadata = {
                "wiki_id": paths.wiki_id,
                "name": paths.wiki_id.replace("_", " ").title(),
                "created_at": _timestamp(),
                "last_updated": _timestamp(),
                "models": {},
            }
            self._write_metadata(paths, metadata)
            return metadata
        with paths.metadata_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_metadata(self, paths: WikiPaths, metadata: dict[str, Any]) -> None:
        ensure_directory(paths.root_dir)
        metadata.setdefault("wiki_id", paths.wiki_id)
        metadata.setdefault("models", {})
        with paths.metadata_file.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2)

    def _ensure_seed_file(self, source_path: Path, target_path: Path) -> None:
        if not source_path.exists():
            return
        ensure_directory(target_path.parent)
        source_text = source_path.read_text(encoding="utf-8")
        if target_path.exists() and target_path.read_text(encoding="utf-8") == source_text:
            return
        target_path.write_text(source_text, encoding="utf-8")

    def _ensure_blank_seed(self, target_path: Path, default_content: str, legacy_template_path: Path | None = None) -> None:
        ensure_directory(target_path.parent)
        if not target_path.exists():
            target_path.write_text(default_content, encoding="utf-8")
            return

        current_content = target_path.read_text(encoding="utf-8")
        if current_content == default_content:
            return

        if legacy_template_path and legacy_template_path.exists():
            legacy_content = legacy_template_path.read_text(encoding="utf-8")
            if current_content == legacy_content:
                target_path.write_text(default_content, encoding="utf-8")

    def _ensure_wiki_scaffold(self, paths: WikiPaths) -> None:
        ensure_directory(paths.wiki_dir)
        self._ensure_seed_file(self.canonical_schema_path, paths.wiki_dir / "SCHEMA.md")
        self._ensure_seed_file(self.canonical_purpose_path, paths.wiki_dir / "purpose.md")
        self._ensure_blank_seed(paths.wiki_dir / "purpose.md", DEFAULT_PURPOSE_CONTENT)
        self._ensure_blank_seed(paths.wiki_dir / "index.md", DEFAULT_INDEX_CONTENT, self.legacy_index_template_path)
        self._ensure_blank_seed(paths.wiki_dir / "log.md", DEFAULT_LOG_CONTENT, self.legacy_log_template_path)

    def _serialize_wiki(self, paths: WikiPaths, metadata: dict[str, Any]) -> dict[str, Any]:
        page_count = len([path for path in paths.wiki_dir.glob("*.md")]) if paths.wiki_dir.exists() else 0
        source_count = len([path for path in paths.sources_dir.iterdir() if path.is_file() and path.suffix in {".md", ".txt", ".html"}]) if paths.sources_dir.exists() else 0
        return {
            "wiki_id": paths.wiki_id,
            "name": metadata.get("name", paths.wiki_id),
            "created_at": metadata.get("created_at"),
            "last_updated": metadata.get("last_updated"),
            "models": metadata.get("models", {}),
            "root_dir": str(paths.root_dir),
            "sources_dir": str(paths.sources_dir),
            "wiki_dir": str(paths.wiki_dir),
            "embeddings_dir": str(paths.embeddings_dir),
            "metadata_file": str(paths.metadata_file),
            "log_file": str(paths.log_file),
            "page_count": page_count,
            "source_count": source_count,
        }

    def _migrate_legacy_data(self) -> None:
        has_existing_wikis = any(self.wikis_root.iterdir())
        if has_existing_wikis:
            return

        legacy_exists = self.legacy_wiki_dir.exists() or self.legacy_raw_dir.exists()
        if not legacy_exists:
            return

        migrated = self.create_wiki("Main Wiki", wiki_id="main")
        paths = self.get_paths(migrated["wiki_id"])

        if self.legacy_raw_dir.exists():
            for item in self.legacy_raw_dir.iterdir():
                target = paths.sources_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)

        if self.legacy_wiki_dir.exists():
            for item in self.legacy_wiki_dir.iterdir():
                if item.name == ".git":
                    continue
                if item.name == ".chroma":
                    shutil.copytree(item, paths.embeddings_dir, dirs_exist_ok=True)
                    continue
                target = paths.wiki_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)

        self._ensure_wiki_scaffold(paths)
        metadata = self._read_metadata(paths)
        metadata["last_updated"] = _timestamp()
        metadata["migrated_from_legacy"] = True
        self._write_metadata(paths, metadata)
