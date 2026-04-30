import asyncio
import json
from typing import AsyncGenerator

class ProgressManager:
    def __init__(self):
        self.queues = []

    async def subscribe(self) -> AsyncGenerator[str, None]:
        queue = asyncio.Queue()
        self.queues.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self.queues.remove(queue)

    def broadcast(self, message: str, progress: int = 0, status: str = "processing"):
        payload = json.dumps({"message": message, "progress": progress, "status": status})
        for queue in self.queues:
            queue.put_nowait(f"data: {payload}\n\n")

progress_manager = ProgressManager()
