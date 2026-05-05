from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import GenericJSONSearchConfig, PipelineConfig, SearxngConfig
from .pipeline import PipelineRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local AI Wiki Builder pipeline.")
    parser.add_argument("--topic", required=True, help="Topic to research and convert into a wiki.")
    parser.add_argument("--vault", required=True, help="Absolute path to the Obsidian vault root.")
    parser.add_argument("--searxng-url", help="Base URL for a SearXNG instance, for example http://localhost:8080.")
    parser.add_argument("--search-api-url", help="Fallback JSON search API endpoint.")
    parser.add_argument("--results-per-query", type=int, default=5)
    parser.add_argument("--source-limit", type=int, default=15)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    searxng = SearxngConfig(base_url=args.searxng_url) if args.searxng_url else None
    fallback = GenericJSONSearchConfig(endpoint=args.search_api_url) if args.search_api_url else None
    config = PipelineConfig(
        vault_path=Path(args.vault).expanduser().resolve(),
        searxng=searxng,
        fallback_search=fallback,
        results_per_query=args.results_per_query,
        source_limit=args.source_limit,
    )
    result = PipelineRunner(config).run_pipeline(args.topic)
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
