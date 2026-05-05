from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_support import BACKEND_PATH

from wiki_builder.config import PipelineConfig
from wiki_builder.models import SearchResult
from wiki_builder.pipeline import PipelineRunner


class EndToEndPipelineTests(unittest.TestCase):
    def test_run_pipeline_creates_expected_structure_and_logs_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs_dir = root / "fixtures"
            docs_dir.mkdir(parents=True, exist_ok=True)
            edge_ai_path = docs_dir / "edge-ai.html"
            on_device_path = docs_dir / "on-device.html"
            missing_path = docs_dir / "missing.html"
            edge_ai_path.write_text(
                """
                <html><head><title>Edge AI Overview</title></head>
                <body><article>
                  <p>Edge AI runs machine learning workloads near sensors and devices.</p>
                  <p>On-device inference reduces latency and protects sensitive data.</p>
                </article></body></html>
                """,
                encoding="utf-8",
            )
            on_device_path.write_text(
                """
                <html><head><title>On Device Inference</title></head>
                <body><main>
                  <p>Model compression and quantization make on-device inference feasible.</p>
                  <p>Edge AI deployments balance power limits, bandwidth, and privacy.</p>
                </main></body></html>
                """,
                encoding="utf-8",
            )
            config = PipelineConfig(
                vault_path=(root / "vault").resolve(),
                data_root=root / "data",
                logs_dir=root / "logs",
                fallback_search=None,
                searxng=None,
                minimum_sources_warning=5,
            )
            results = [
                SearchResult(title="Edge AI Overview", url=edge_ai_path.as_uri(), snippet="Overview of edge AI systems", query="Edge AI"),
                SearchResult(title="On Device Inference", url=on_device_path.as_uri(), snippet="Efficient inference techniques", query="Edge AI"),
                SearchResult(title="Broken Source", url=missing_path.as_uri(), snippet="This one fails", query="Edge AI"),
            ]
            with patch.object(PipelineConfig, "validate", return_value=None):
                runner = PipelineRunner(config)

            def fake_discover(topic: str, logger):
                logger.log("search", True, "Completed source discovery", topic=topic, count=len(results))
                return results

            with patch.object(PipelineRunner, "discover_sources", side_effect=fake_discover):
                result = runner.run_pipeline("Edge AI")

            self.assertEqual(result.discovered_sources, 3)
            self.assertEqual(result.fetched_sources, 2)
            self.assertEqual(result.failed_sources, 1)
            self.assertTrue(result.warnings)
            self.assertTrue((Path(result.raw_sources_dir) / "sources.json").exists())
            self.assertTrue((Path(result.obsidian_wiki_dir) / "index.md").exists())
            self.assertTrue(Path(result.log_path).exists())

            log_lines = [json.loads(line) for line in Path(result.log_path).read_text(encoding="utf-8").splitlines() if line.strip()]
            stages = {line["stage"] for line in log_lines}
            self.assertTrue({"search", "fetch", "parse", "ingest", "generate"}.issubset(stages))
            self.assertTrue(any(not line["success"] for line in log_lines if line["stage"] == "fetch"))


if __name__ == "__main__":
    unittest.main()
