from __future__ import annotations

from pathlib import Path

from .models import FetchedSource
from .utils import ensure_directory, slugify


def _yaml_escape(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'


def build_source_note_markdown(topic: str, source: FetchedSource) -> str:
    topic_slug = slugify(topic)
    title = source.title.strip() or "Untitled Source"
    lines = [
        "---",
        f"title: {_yaml_escape(title)}",
        f"source_url: {_yaml_escape(source.url)}",
        f"retrieved_at: {_yaml_escape(source.retrieval_timestamp)}",
        f"last_updated: {_yaml_escape(source.last_updated or '')}",
        "tags:",
        '  - "source"',
        f'  - "topic/{topic_slug}"',
        "---",
        "",
        f"# {title}",
        "",
        f"Source: [{source.url}]({source.url})",
        "",
        source.cleaned_content.strip(),
        "",
    ]
    return "\n".join(lines)


class ObsidianWriter:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path

    def write_source_notes(self, topic: str, sources: list[FetchedSource], workspace_id: str | None = None) -> list[Path]:
        topic_root = ensure_directory(self.vault_path / (workspace_id or slugify(topic)))
        sources_dir = ensure_directory(topic_root / "sources")
        written: list[Path] = []
        for source in sources:
            note_path = sources_dir / f"{source.source_id}.md"
            note_path.write_text(build_source_note_markdown(topic, source), encoding="utf-8")
            written.append(note_path)
        return written
