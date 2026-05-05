from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm_provider import call_sync_with_fallback
from .models import FetchedSource
from .utils import ensure_directory, normalize_whitespace, sentence_split, slugify


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "into", "is", "it",
    "of", "on", "or", "that", "the", "their", "this", "to", "was", "were", "what", "when", "where",
    "which", "who", "with", "within", "without", "your",
    "has", "have", "had", "been", "being", "still", "over", "under", "past", "today", "years", "year", "ago",
}
LOW_VALUE_TOKENS = {
    "important",
    "could",
    "would",
    "should",
    "there",
    "their",
    "them",
    "they",
    "these",
    "those",
    "city",
    "most",
    "main",
    "public",
    "its",
    "hlist",
    "parser",
    "output",
    "website",
    "remarkable",
    "first",
    "last",
    "built",
    "move",
    "moved",
    "private",
    "news",
    "introduction",
    "technical",
    "questions",
    "answers",
}
BAD_EDGE_TOKENS = {"website", "remarkable", "first", "last", "built", "today", "past", "years", "year", "ago"}
SYSTEM_PAGES = {"index.md", "log.md", "SCHEMA.md"}
SENTENCE_NOISE_MARKERS = (
    "under construction",
    "to the sister website",
    "private website",
    "aqueduct news",
    "in dutch",
)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text)]


def build_ngram_candidates(text: str, min_n: int = 1, max_n: int = 3) -> Counter[str]:
    words = tokenize(text)
    counts: Counter[str] = Counter()
    for size in range(min_n, max_n + 1):
        for index in range(0, len(words) - size + 1):
            chunk = words[index:index + size]
            if any(token in STOPWORDS for token in chunk):
                continue
            candidate = " ".join(chunk)
            counts[candidate] += 1
    return counts


def concept_title(slug: str) -> str:
    return slug.replace("-", " ").title()


def normalize_source_title(title: str) -> str:
    cleaned = re.split(r"\s+\|\s+", title, maxsplit=1)[0]
    cleaned = re.split(r"\s+-\s+(Wikipedia|PMC|Reddit)\b", cleaned, maxsplit=1)[0]
    return normalize_whitespace(cleaned)


def is_low_value_phrase(phrase: str, topic_tokens: set[str]) -> bool:
    tokens = phrase.split()
    if len(tokens) < 2:
        return True
    if any(token in LOW_VALUE_TOKENS for token in tokens):
        return True
    if tokens[0] in BAD_EDGE_TOKENS or tokens[-1] in BAD_EDGE_TOKENS:
        return True
    if all(token in topic_tokens for token in tokens):
        return True
    return False


def is_useful_sentence(sentence: str) -> bool:
    lowered = sentence.lower()
    if any(marker in lowered for marker in SENTENCE_NOISE_MARKERS):
        return False
    if len(sentence) < 60 or len(sentence) > 420:
        return False
    if len(re.findall(r"[{};=]", sentence)) > max(10, len(sentence) // 25):
        return False
    return True


def _score_sentence(sentence: str, concept: str, related: set[str]) -> float:
    lowered = sentence.lower()
    score = len(sentence) / 100.0
    if concept in lowered:
        score += 3
    for item in related:
        if item.replace("-", " ") in lowered:
            score += 0.75
    return score


def _apply_wikilinks(text: str, concept_map: dict[str, str], current_slug: str) -> str:
    linked = text
    replacements = sorted(concept_map.items(), key=lambda item: len(item[0]), reverse=True)
    for phrase, slug in replacements:
        if slug == current_slug:
            continue
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        linked = pattern.sub(f"[[{slug}|{concept_title(slug)}]]", linked, count=1)
    return linked


class WikiGenerator:
    def __init__(self, vault_path: Path, model_id: str | None = None):
        self.vault_path = vault_path
        self.model_id = model_id

    def _llm_select_concepts(self, topic: str, sources: list[FetchedSource], fallback: list[str]) -> list[str]:
        source_briefs = []
        for source in sources[:8]:
            snippet = normalize_whitespace(source.snippet)[:220]
            source_briefs.append(f"- {source.title}: {snippet}")
        prompt = "\n".join(source_briefs) or "- No source briefs available."
        candidate_slugs = ", ".join(fallback)
        messages = [
            SystemMessage(
                content=(
                    "You are selecting concept pages for a local research wiki.\n"
                    "Return only a JSON array of 4 to 8 kebab-case slugs.\n"
                    "Prefer enduring topics, places, systems, engineering concepts, and named aqueducts.\n"
                    "Exclude website names, source brands, citation fragments, adjectives, time phrases, and navigation text.\n"
                    "The first slug must be the main topic slug if it is appropriate."
                )
            ),
            HumanMessage(
                content=(
                    f"Topic: {topic}\n"
                    f"Fallback candidate slugs: {candidate_slugs}\n"
                    f"Source briefs:\n{prompt}"
                )
            ),
        ]
        try:
            response = call_sync_with_fallback(messages, "wiki-builder-concepts", model_id=self.model_id) or ""
            parsed = json.loads(response)
            if not isinstance(parsed, list):
                return fallback
            concepts: list[str] = []
            for item in parsed:
                slug = slugify(str(item))
                if not slug or slug in concepts or slug in SYSTEM_PAGES:
                    continue
                concepts.append(slug)
            return concepts or fallback
        except Exception:
            return fallback

    def _llm_build_concept_page(
        self,
        topic: str,
        concept_slug: str,
        related: list[str],
        source_links: list[str],
        supporting_sentences: list[str],
    ) -> str | None:
        if not self.model_id or not supporting_sentences:
            return None
        related_lines = "\n".join(f"- {concept_title(slug)} ({slug})" for slug in related) or "- None"
        source_lines = "\n".join(f"- {link}" for link in source_links) or "- None"
        evidence = "\n".join(f"- {sentence}" for sentence in supporting_sentences[:8])
        messages = [
            SystemMessage(
                content=(
                    "You are writing a concise markdown wiki page from research excerpts.\n"
                    "Use only the supplied evidence.\n"
                    "Ignore source-brand names, bibliographies, menu text, and navigation clutter unless historically important.\n"
                    "Return markdown with these sections exactly: "
                    "# Title, ## Overview, ## Key Points, ## Related Concepts, ## Source Notes.\n"
                    "In Related Concepts and Source Notes, preserve the provided wikilinks exactly when used.\n"
                    "Do not invent facts."
                )
            ),
            HumanMessage(
                content=(
                    f"Topic: {topic}\n"
                    f"Concept slug: {concept_slug}\n"
                    f"Concept title: {concept_title(concept_slug)}\n"
                    f"Available related concepts:\n{related_lines}\n"
                    f"Available source note links:\n{source_lines}\n"
                    f"Evidence excerpts:\n{evidence}"
                )
            ),
        ]
        try:
            response = call_sync_with_fallback(messages, "wiki-builder-page", model_id=self.model_id)
            cleaned = normalize_whitespace(response or "")
            return cleaned if cleaned.startswith("# ") else None
        except Exception:
            return None

    def extract_concepts(self, topic: str, sources: list[FetchedSource]) -> list[str]:
        topic_tokens = set(tokenize(topic))
        document_frequency: Counter[str] = Counter()
        term_frequency: Counter[str] = Counter()
        for source in sources:
            title_seed = normalize_source_title(source.title)
            leading_text = " ".join(sentence_split(source.cleaned_content)[:10])
            counts = build_ngram_candidates(f"{title_seed}\n{title_seed}\n{source.snippet}\n{leading_text}", min_n=2, max_n=4)
            term_frequency.update(counts)
            document_frequency.update(counts.keys())

        scored: list[tuple[str, float]] = []
        for candidate, total_count in term_frequency.items():
            tokens = candidate.split()
            if is_low_value_phrase(candidate, topic_tokens):
                continue
            title_bonus = 3 if any(candidate in normalize_source_title(source.title).lower() for source in sources) else 0
            if total_count < 2 and document_frequency[candidate] < 2 and title_bonus == 0:
                continue
            df = document_frequency[candidate]
            score = total_count + (df * 2.5) + title_bonus + math.log(len(candidate) + 1)
            scored.append((candidate, score))

        ranked = sorted(scored, key=lambda item: (-item[1], item[0]))
        selected: list[str] = [slugify(topic)]
        seen_tokens: set[str] = set()
        for phrase, _score in ranked:
            slug = slugify(phrase)
            if not slug or slug in selected:
                continue
            tokens = set(phrase.split())
            if tokens and tokens.issubset(seen_tokens):
                continue
            selected.append(slug)
            seen_tokens.update(tokens)
            if len(selected) >= 10:
                break
        if not selected:
            selected.append(slugify(topic))
        llm_selected = self._llm_select_concepts(topic, sources, selected[:8])
        topic_slug = slugify(topic)
        if topic_slug in llm_selected:
            llm_selected = [topic_slug] + [slug for slug in llm_selected if slug != topic_slug]
        elif topic_slug:
            llm_selected = [topic_slug, *llm_selected]
        return llm_selected[:8]

    def _collect_sentences(self, concept_slug: str, sources: list[FetchedSource]) -> list[str]:
        concept_phrase = concept_slug.replace("-", " ")
        matches: list[str] = []
        for source in sources:
            for sentence in sentence_split(source.cleaned_content):
                normalized = normalize_whitespace(sentence)
                if concept_phrase in normalized.lower() and is_useful_sentence(normalized):
                    matches.append(normalized)
        return matches

    def _related_concepts(self, concept_slug: str, concept_slugs: list[str], sources: list[FetchedSource]) -> list[str]:
        concept_phrase = concept_slug.replace("-", " ")
        related_scores: Counter[str] = Counter()
        for source in sources:
            lowered = source.cleaned_content.lower()
            if concept_phrase not in lowered:
                continue
            for other_slug in concept_slugs:
                if other_slug == concept_slug:
                    continue
                if other_slug.replace("-", " ") in lowered:
                    related_scores[other_slug] += 1
        return [slug for slug, _count in related_scores.most_common(5)]

    def _build_concept_page(self, topic: str, concept_slug: str, concept_slugs: list[str], sources: list[FetchedSource]) -> str:
        supporting_sentences = self._collect_sentences(concept_slug, sources)
        related = self._related_concepts(concept_slug, concept_slugs, sources)
        related_phrases = {slug.replace("-", " "): slug for slug in related}
        if not supporting_sentences:
            supporting_sentences = []
            for source in sources:
                supporting_sentences.extend(
                    sentence
                    for sentence in (normalize_whitespace(item) for item in sentence_split(source.cleaned_content))
                    if is_useful_sentence(sentence)
                )
        ranked_sentences = sorted(
            supporting_sentences,
            key=lambda sentence: _score_sentence(sentence, concept_slug.replace("-", " "), set(related)),
            reverse=True,
        )
        unique_sentences: list[str] = []
        seen: set[str] = set()
        for sentence in ranked_sentences:
            normalized = sentence.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique_sentences.append(sentence)
            if len(unique_sentences) >= 5:
                break
        overview = " ".join(unique_sentences[:3]).strip()
        overview = _apply_wikilinks(overview, related_phrases, concept_slug)
        bullets = [_apply_wikilinks(sentence, related_phrases, concept_slug) for sentence in unique_sentences[:5]]
        source_links = []
        for source in sources:
            if concept_slug.replace("-", " ") in source.cleaned_content.lower():
                source_links.append(f"[[sources/{source.source_id}|{source.title}]]")
        source_links = source_links[:5]
        llm_page = self._llm_build_concept_page(topic=topic, concept_slug=concept_slug, related=related, source_links=source_links, supporting_sentences=unique_sentences)
        if llm_page:
            return llm_page
        lines = [
            f"# {concept_title(concept_slug)}",
            "",
            "## Overview",
            overview or "No overview was extracted for this concept.",
            "",
            "## Key Points",
        ]
        if bullets:
            lines.extend(f"- {bullet}" for bullet in bullets)
        else:
            lines.append("- No supporting sentences were available.")
        lines.extend(["", "## Related Concepts"])
        if related:
            lines.extend(f"- [[{slug}|{concept_title(slug)}]]" for slug in related)
        else:
            lines.append("- None identified from the current sources.")
        lines.extend(["", "## Source Notes"])
        if source_links:
            lines.extend(f"- {link}" for link in source_links)
        else:
            lines.append("- No source notes referenced this concept directly.")
        lines.append("")
        return "\n".join(lines)

    def write_wiki(self, topic: str, sources: list[FetchedSource], workspace_id: str | None = None) -> list[Path]:
        topic_root = ensure_directory(self.vault_path / (workspace_id or slugify(topic)))
        wiki_dir = ensure_directory(topic_root / "wiki")
        concept_slugs = self.extract_concepts(topic, sources)
        for existing_page in wiki_dir.glob("*.md"):
            if existing_page.name in SYSTEM_PAGES:
                continue
            existing_page.unlink()
        written: list[Path] = []
        for concept_slug in concept_slugs:
            page_path = wiki_dir / f"{concept_slug}.md"
            page_path.write_text(self._build_concept_page(topic, concept_slug, concept_slugs, sources), encoding="utf-8")
            written.append(page_path)
        index_path = wiki_dir / "index.md"
        index_lines = [
            f"# {topic}",
            "",
            "## Concepts",
        ]
        index_lines.extend(f"- [[{slug}|{concept_title(slug)}]]" for slug in concept_slugs)
        index_lines.append("")
        index_path.write_text("\n".join(index_lines), encoding="utf-8")
        written.append(index_path)
        return written
