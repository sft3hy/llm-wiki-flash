import os
import re

class LintEngine:
    def __init__(self, wiki_dir: str):
        self.wiki_dir = wiki_dir

    async def meditate(self):
        broken_links = []
        all_pages = [f for f in os.listdir(self.wiki_dir) if f.endswith(".md")]
        
        for page in all_pages:
            with open(os.path.join(self.wiki_dir, page), "r") as f:
                content = f.read()
                links = re.findall(r"\[\[(.*?)\]\]", content)
                for link in links:
                    link_file = f"{link}.md"
                    if link_file not in all_pages:
                        broken_links.append({"source": page, "target": link_file})
        
        return {
            "status": "success", 
            "broken_links": broken_links,
            "suggestions": [f"Create page for {link['target']}" for link in broken_links]
        }
