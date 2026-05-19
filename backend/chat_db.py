"""
Chat persistence layer — multi-conversation support.

Tables:
  conversations — independent chat sessions per wiki
  messages      — per-conversation message history with citation metadata
"""

import sqlite3
import os
import uuid
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

DB_PATH = "data/chat_history.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _connect() as conn:
        cursor = conn.cursor()

        # ── Conversations table ──
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                wiki_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT 'New Conversation',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_conv_wiki ON conversations (wiki_id)')

        # ── Messages table ──
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                wiki_id TEXT NOT NULL,
                conversation_id TEXT,
                text TEXT NOT NULL,
                sender TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                model TEXT,
                context TEXT,
                citations TEXT,
                retrieval_stats TEXT
            )
        ''')

        # ── Migration: add new columns if missing (existing DB) ──
        columns = [row[1] for row in cursor.execute("PRAGMA table_info(messages)").fetchall()]
        if "conversation_id" not in columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN conversation_id TEXT")
        if "citations" not in columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN citations TEXT")
        if "retrieval_stats" not in columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN retrieval_stats TEXT")

        # ── Indexes (safe now that columns exist) ──
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_wiki_id ON messages (wiki_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_conv_id ON messages (conversation_id)')

        conn.commit()

    # Migrate orphaned messages into legacy conversations
    _migrate_legacy_messages()


def _migrate_legacy_messages():
    """Move messages without a conversation_id into a 'Legacy' conversation per wiki."""
    with _connect() as conn:
        cursor = conn.cursor()
        orphans = cursor.execute(
            "SELECT DISTINCT wiki_id FROM messages WHERE conversation_id IS NULL"
        ).fetchall()

        for row in orphans:
            wiki_id = row["wiki_id"]
            conv_id = uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()

            # Find the earliest message timestamp for created_at
            first_ts = cursor.execute(
                "SELECT MIN(timestamp) as ts FROM messages WHERE wiki_id = ? AND conversation_id IS NULL",
                (wiki_id,)
            ).fetchone()
            created = first_ts["ts"] if first_ts and first_ts["ts"] else now

            cursor.execute(
                "INSERT INTO conversations (id, wiki_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (conv_id, wiki_id, "Previous Chat", created, now)
            )
            cursor.execute(
                "UPDATE messages SET conversation_id = ? WHERE wiki_id = ? AND conversation_id IS NULL",
                (conv_id, wiki_id)
            )

        conn.commit()


# ─── Conversation CRUD ─────────────────────────────────────────────────

def create_conversation(wiki_id: str, title: str = "New Conversation") -> Dict[str, Any]:
    conv_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO conversations (id, wiki_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (conv_id, wiki_id, title, now, now)
        )
        conn.commit()
    return {"id": conv_id, "wiki_id": wiki_id, "title": title, "created_at": now, "updated_at": now, "message_count": 0}


def list_conversations(wiki_id: str) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT c.id, c.wiki_id, c.title, c.created_at, c.updated_at,
                      (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) as message_count
               FROM conversations c
               WHERE c.wiki_id = ?
               ORDER BY c.updated_at DESC""",
            (wiki_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """SELECT c.id, c.wiki_id, c.title, c.created_at, c.updated_at,
                      (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) as message_count
               FROM conversations c WHERE c.id = ?""",
            (conversation_id,)
        ).fetchone()
        return dict(row) if row else None


def rename_conversation(conversation_id: str, title: str):
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, conversation_id)
        )
        conn.commit()


def delete_conversation(conversation_id: str):
    with _connect() as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()


# ─── Message Operations ───────────────────────────────────────────────

def save_message(
    msg_id: str,
    wiki_id: str,
    text: str,
    sender: str,
    timestamp: str,
    model: Optional[str] = None,
    context: Optional[str] = None,
    conversation_id: Optional[str] = None,
    citations: Optional[dict] = None,
    retrieval_stats: Optional[dict] = None,
):
    citations_json = json.dumps(citations) if citations else None
    stats_json = json.dumps(retrieval_stats) if retrieval_stats else None
    with _connect() as conn:
        conn.execute(
            """INSERT INTO messages (id, wiki_id, conversation_id, text, sender, timestamp, model, context, citations, retrieval_stats)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, wiki_id, conversation_id, text, sender, timestamp, model, context, citations_json, stats_json)
        )
        # Touch conversation updated_at
        if conversation_id:
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (timestamp, conversation_id)
            )
        conn.commit()


def get_conversation_messages(conversation_id: str) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, wiki_id, conversation_id, text, sender, timestamp, model, context, citations, retrieval_stats
               FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC""",
            (conversation_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["citations"] = json.loads(d["citations"]) if d.get("citations") else None
            d["retrieval_stats"] = json.loads(d["retrieval_stats"]) if d.get("retrieval_stats") else None
            result.append(d)
        return result


def get_chat_history(wiki_id: str) -> List[Dict[str, Any]]:
    """Legacy endpoint — returns ALL messages for a wiki (all conversations merged)."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, wiki_id, text, sender, timestamp, model, context
               FROM messages WHERE wiki_id = ? ORDER BY timestamp ASC""",
            (wiki_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_last_exchange(conversation_id: str) -> Optional[Dict[str, str]]:
    """Remove the last assistant + user message pair. Returns the user query text for regeneration."""
    with _connect() as conn:
        # Find the last assistant message
        last_bot = conn.execute(
            """SELECT id, timestamp FROM messages
               WHERE conversation_id = ? AND sender = 'bot'
               ORDER BY timestamp DESC LIMIT 1""",
            (conversation_id,)
        ).fetchone()
        if not last_bot:
            return None

        # Find the user message immediately before it
        last_user = conn.execute(
            """SELECT id, text FROM messages
               WHERE conversation_id = ? AND sender = 'user' AND timestamp <= ?
               ORDER BY timestamp DESC LIMIT 1""",
            (conversation_id, last_bot["timestamp"])
        ).fetchone()

        # Delete both
        conn.execute("DELETE FROM messages WHERE id = ?", (last_bot["id"],))
        user_query = None
        if last_user:
            user_query = last_user["text"]
            conn.execute("DELETE FROM messages WHERE id = ?", (last_user["id"],))

        conn.commit()
        return {"query": user_query} if user_query else None


def get_conversation_for_export(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Get full conversation data for wiki export."""
    conv = get_conversation(conversation_id)
    if not conv:
        return None
    conv["messages"] = get_conversation_messages(conversation_id)
    return conv
