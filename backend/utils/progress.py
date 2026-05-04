import asyncio
import json
from typing import AsyncGenerator

class ProgressManager:
    def __init__(self):
        self.queues = []
        self.last_payload = None

    async def subscribe(self) -> AsyncGenerator[str, None]:
        queue = asyncio.Queue()
        self.queues.append(queue)
        
        # If there's a last known progress, send it immediately to the new subscriber
        if self.last_payload:
            yield self.last_payload

        try:
            while True:
                yield await queue.get()
        finally:
            self.queues.remove(queue)

    def broadcast(self, message: str, progress: int = 0, status: str = "processing"):
        payload = json.dumps({"message": message, "progress": progress, "status": status})
        self.last_payload = payload
        
        for queue in self.queues:
            queue.put_nowait(payload)

progress_manager = ProgressManager()
