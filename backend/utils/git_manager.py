import os
from git import Repo

class GitManager:
    def __init__(self, wiki_dir: str):
        self.wiki_dir = wiki_dir
        if not os.path.exists(os.path.join(wiki_dir, ".git")):
            self.repo = Repo.init(wiki_dir)
        else:
            self.repo = Repo(wiki_dir)

    def commit_changes(self, message: str):
        self.repo.git.add(A=True)
        try:
            self.repo.index.commit(message)
            return True
        except Exception as e:
            print(f"Git commit failed (likely no changes): {e}")
            return False
