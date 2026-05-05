from __future__ import annotations

import unittest

from test_support import BACKEND_PATH

from wiki_builder.models import FetchedSource, SearchResult
from wiki_builder.obsidian import build_source_note_markdown
from wiki_builder.search import deduplicate_results, generate_search_queries


class QueryGenerationTests(unittest.TestCase):
    def test_generate_search_queries_returns_unique_queries(self) -> None:
        queries = generate_search_queries(
            "Distributed Systems",
            (
                "{topic}",
                "{topic} overview",
                "{topic}",
                "{topic} applications",
            ),
            max_queries=4,
        )
        self.assertEqual(
            queries,
            [
                "Distributed Systems",
                "Distributed Systems overview",
                "Distributed Systems applications",
            ],
        )


class LinkExtractionTests(unittest.TestCase):
    def test_deduplicate_results_normalizes_urls(self) -> None:
        results = [
            SearchResult(title="One", url="https://example.com/page", snippet="a", query="q"),
            SearchResult(title="Two", url="https://example.com/page/", snippet="b", query="q"),
            SearchResult(title="Three", url="https://example.com/page#section", snippet="c", query="q"),
        ]
        deduplicated = deduplicate_results(results, limit=10)
        self.assertEqual(len(deduplicated), 1)
        self.assertEqual(deduplicated[0].url, "https://example.com/page")


class MarkdownConversionTests(unittest.TestCase):
    def test_build_source_note_markdown_includes_frontmatter_and_content(self) -> None:
        source = FetchedSource(
            title="Consensus Protocols",
            url="https://example.com/consensus",
            snippet="Consensus overview",
            query="consensus protocols",
            raw_content="<html></html>",
            cleaned_content="Consensus protocols coordinate replicated state machines.",
            content_type="text/html",
            retrieval_timestamp="2026-05-04T00:00:00+00:00",
            last_updated="Mon, 04 May 2026 00:00:00 GMT",
            source_id="consensus-protocols-123",
        )
        markdown = build_source_note_markdown("Distributed Systems", source)
        self.assertIn('title: "Consensus Protocols"', markdown)
        self.assertIn('  - "source"', markdown)
        self.assertIn("Consensus protocols coordinate replicated state machines.", markdown)


if __name__ == "__main__":
    unittest.main()
