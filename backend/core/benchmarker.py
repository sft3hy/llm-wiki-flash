import time
import asyncio
from typing import List, Dict
from core.ingest import IngestEngine
from config import settings


class Benchmarker:
    def __init__(self, raw_dir: str, wiki_dir: str):
        self.raw_dir = raw_dir
        self.wiki_dir = wiki_dir

    async def compare_models(self, filename: str, models: List[str] = None) -> List[Dict]:
        """Run ingestion across multiple models and compare performance."""
        from config import AVAILABLE_MODELS, MODEL_LOOKUP
        models = models or [m.model_id for m in AVAILABLE_MODELS]
        results = []

        for model_id in models:
            model_config = MODEL_LOOKUP.get(model_id)
            start_time = time.perf_counter()
            try:
                engine = IngestEngine(self.raw_dir, self.wiki_dir, model_id=model_id)
                result = await engine.process_file(filename)
                end_time = time.perf_counter()

                latency = end_time - start_time

                results.append({
                    "model": model_id,
                    "display_name": model_config.display_name if model_config else model_id,
                    "status": "success",
                    "latency": round(latency, 2),
                    "pages_created": result.get("pages_created", []),
                    "pages_updated": result.get("pages_updated", []),
                    "total_pages_touched": result.get("total_pages_touched", 0),
                    "provider": model_config.provider if model_config else "unknown",
                })
            except Exception as e:
                results.append({
                    "model": model_id,
                    "display_name": model_config.display_name if model_config else model_id,
                    "status": "error",
                    "error": str(e),
                    "provider": model_config.provider if model_config else "unknown",
                })

        return results
