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
        models = models or settings.COMPARISON_MODELS
        results = []

        for model in models:
            start_time = time.perf_counter()
            try:
                engine = IngestEngine(self.raw_dir, self.wiki_dir, model_name=model)
                wiki_file = await engine.process_file(filename)
                end_time = time.perf_counter()
                
                latency = end_time - start_time
                
                results.append({
                    "model": model,
                    "status": "success",
                    "latency": round(latency, 2),
                    "wiki_page": wiki_file,
                    "provider": "Groq" if "llama" in model.lower() else "OpenAI/Anthropic"
                })
            except Exception as e:
                results.append({
                    "model": model,
                    "status": "error",
                    "error": str(e)
                })
        
        return results
