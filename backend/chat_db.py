import sqlite3
import os
from typing import List, Dict, Any, Optional

DB_PATH = "data/chat_history.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                wiki_id TEXT NOT NULL,
                text TEXT NOT NULL,
                sender TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                model TEXT,
                context TEXT
            )
        ''')
        # Create an index for faster lookups by wiki_id
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_wiki_id ON messages (wiki_id)')
        conn.commit()

def save_message(msg_id: str, wiki_id: str, text: str, sender: str, timestamp: str, model: Optional[str] = None, context: Optional[str] = None):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (id, wiki_id, text, sender, timestamp, model, context)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (msg_id, wiki_id, text, sender, timestamp, model, context))
        conn.commit()

def get_chat_history(wiki_id: str) -> List[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        # Return dicts instead of tuples
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, wiki_id, text, sender, timestamp, model, context
            FROM messages
            WHERE wiki_id = ?
            ORDER BY timestamp ASC
        ''', (wiki_id,))
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
