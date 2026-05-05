from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_support import BACKEND_PATH

from wiki_builder.config import PipelineConfig
from wiki_builder.models import FetchedSource, SearchResult
from wiki_builder.pipeline import PipelineRunner
from wiki_builder.wiki import WikiGenerator


TOPIC = "Solar Microgrids"

DOC_ONE = """
<html>
  <head><title>Solar Microgrids Overview</title></head>
  <body>
    <nav>Navigation that should be ignored.</nav>
    <article>
      <p>Solar microgrids combine photovoltaic generation, battery storage, and intelligent controls.</p>
      <p>Battery storage stabilizes the system during cloud cover and evening demand peaks.</p>
      <p>Inverters translate direct current into grid-ready alternating current.</p>
    </article>
  </body>
</html>
"""

DOC_TWO = """
<html>
  <head><title>Battery Storage For Microgrids</title></head>
  <body>
    <main>
      <p>Battery storage supports resilience, frequency control, and black-start operations.</p>
      <p>Demand response reduces peak load and complements battery storage dispatch.</p>
    </main>
  </body>
</html>
"""

DOC_THREE = """
<html>
  <head><title>Inverter Controls In Practice</title></head>
  <body>
    <article>
      <p>Advanced inverters coordinate solar production with battery storage and demand response.</p>
      <p>Power electronics let microgrids island from the main grid during outages.</p>
    </article>
  </body>
</html>
"""
class IngestionIntegrationTests(unittest.TestCase):
    def test_small_topic_ingestion_stores_raw_cleaned_and_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs_dir = root / "fixtures"
            docs_dir.mkdir(parents=True, exist_ok=True)
            overview_path = docs_dir / "overview.html"
            battery_path = docs_dir / "battery.html"
            inverters_path = docs_dir / "inverters.html"
            overview_path.write_text(DOC_ONE, encoding="utf-8")
            battery_path.write_text(DOC_TWO, encoding="utf-8")
            inverters_path.write_text(DOC_THREE, encoding="utf-8")
            config = PipelineConfig(
                vault_path=(root / "vault").resolve(),
                data_root=root / "data",
                logs_dir=root / "logs",
                fallback_search=None,
                searxng=None,
            )
            with patch.object(PipelineConfig, "validate", return_value=None):
                runner = PipelineRunner(config)
            logger_path = config.logs_dir / "integration.log"
            from wiki_builder.logging_utils import PipelineLogger

            logger = PipelineLogger(logger_path)
            results = [
                SearchResult(title="Solar Microgrids Overview", url=overview_path.as_uri(), snippet="Solar microgrid introduction", query=TOPIC),
                SearchResult(title="Battery Storage For Microgrids", url=battery_path.as_uri(), snippet="Storage and resilience", query=TOPIC),
                SearchResult(title="Inverter Controls In Practice", url=inverters_path.as_uri(), snippet="Inverter coordination", query=TOPIC),
            ]
            topic_slug, raw_dir, _log_path, _sources_dir, _wiki_dir = runner._topic_paths(TOPIC)
            fetched, failures = runner.fetch_sources(TOPIC, results, raw_dir, logger)
            note_paths = runner.ingest_sources(TOPIC, fetched, logger)

            self.assertEqual(topic_slug, "solar-microgrids")
            self.assertEqual(len(results), 3)
            self.assertEqual(failures, 0)
            self.assertEqual(len(fetched), 3)
            self.assertEqual(len(note_paths), 3)
            self.assertTrue((raw_dir / "sources.json").exists())
            manifest = json.loads((raw_dir / "sources.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest), 3)
            self.assertTrue(all(Path(item["cleaned_file"]).exists() for item in manifest))


class WikiGenerationIntegrationTests(unittest.TestCase):
    def test_wiki_generation_from_sample_docs_creates_index_and_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            generator = WikiGenerator(vault)
            sources = [
                FetchedSource(
                    title="Solar Microgrids Overview",
                    url="https://example.com/overview",
                    snippet="",
                    query="solar microgrids",
                    raw_content="",
                    cleaned_content=(
                        "Solar microgrids combine photovoltaic generation, battery storage, and intelligent controls. "
                        "Battery storage stabilizes evening demand. Inverters manage conversion between direct current and alternating current."
                    ),
                    content_type="text/html",
                    retrieval_timestamp="2026-05-04T00:00:00+00:00",
                    source_id="overview-1",
                ),
                FetchedSource(
                    title="Demand Response Guide",
                    url="https://example.com/demand-response",
                    snippet="",
                    query="solar microgrids",
                    raw_content="",
                    cleaned_content=(
                        "Demand response lowers peak load and works with battery storage. "
                        "Advanced inverters help microgrids coordinate distributed loads."
                    ),
                    content_type="text/html",
                    retrieval_timestamp="2026-05-04T00:00:00+00:00",
                    source_id="demand-response-1",
                ),
            ]
            paths = generator.write_wiki(TOPIC, sources)
            index_path = next(path for path in paths if path.name == "index.md")
            content = index_path.read_text(encoding="utf-8")
            self.assertIn("[[battery-storage|Battery Storage]]", content)
            concept_file = next(path for path in paths if path.name == "battery-storage.md")
            concept_content = concept_file.read_text(encoding="utf-8")
            self.assertIn("## Related Concepts", concept_content)
            self.assertIn("[[sources/overview-1|Solar Microgrids Overview]]", concept_content)


if __name__ == "__main__":
    unittest.main()
