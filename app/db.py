"""AENIMUS SQLite store v0.1.0."""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.conn.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, title TEXT NOT NULL, orchestration TEXT NOT NULL, agent_ids TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, agent_id TEXT, role TEXT NOT NULL, content TEXT NOT NULL, channel TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit (id TEXT PRIMARY KEY, event TEXT NOT NULL, actor TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, action TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS swarms (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL);
        """)

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def rows(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def put_agent(self, data):
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO agents VALUES (?,?,?)",
                (data["id"], json.dumps(data), self.now()),
            )
            self.conn.commit()

    def agents(self):
        return [
            json.loads(x["data"])
            for x in self.rows("SELECT data FROM agents ORDER BY updated_at")
        ]

    def session(self, title, agent_ids, orchestration):
        id, now = uuid4().hex, self.now()
        with self.lock:
            self.conn.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?)",
                (id, title, orchestration, json.dumps(agent_ids), now),
            )
            self.conn.commit()
        return {
            "id": id,
            "title": title,
            "agent_ids": agent_ids,
            "orchestration": orchestration,
            "created_at": now,
        }

    def sessions(self):
        out = self.rows("SELECT * FROM sessions ORDER BY created_at DESC")
        for x in out:
            x["agent_ids"] = json.loads(x["agent_ids"])
        return out

    def message(self, session_id, role, content, agent_id=None, channel="main"):
        item = {
            "id": uuid4().hex,
            "session_id": session_id,
            "agent_id": agent_id,
            "role": role,
            "content": content,
            "channel": channel,
            "created_at": self.now(),
        }
        with self.lock:
            self.conn.execute(
                "INSERT INTO messages VALUES (:id,:session_id,:agent_id,:role,:content,:channel,:created_at)",
                item,
            )
            self.conn.commit()
        return item

    def messages(self, session_id):
        return self.rows(
            "SELECT * FROM messages WHERE session_id=? ORDER BY created_at",
            (session_id,),
        )

    def audit(self, event, actor, detail):
        row = (uuid4().hex, event, actor, json.dumps(detail), self.now())
        with self.lock:
            self.conn.execute("INSERT INTO audit VALUES (?,?,?,?,?)", row)
            self.conn.commit()

    def audits(self):
        out = self.rows("SELECT * FROM audit ORDER BY created_at DESC LIMIT 250")
        for x in out:
            x["detail"] = json.loads(x["detail"])
        return out

    def approval(self, action, payload):
        item = {
            "id": uuid4().hex,
            "action": action,
            "payload": payload,
            "status": "pending",
            "created_at": self.now(),
        }
        with self.lock:
            self.conn.execute(
                "INSERT INTO approvals VALUES (?,?,?,?,?)",
                (
                    item["id"],
                    action,
                    json.dumps(payload),
                    "pending",
                    item["created_at"],
                ),
            )
            self.conn.commit()
        return item

    def decide(self, id, status):
        with self.lock:
            self.conn.execute("UPDATE approvals SET status=? WHERE id=?", (status, id))
            self.conn.commit()

    def get_approval(self, id):
        r = self.conn.execute("SELECT * FROM approvals WHERE id=?", (id,)).fetchone()
        return dict(r) if r else None

    def consume_approval(self, id, action, payload):
        """Atomically consume an approval only when action and prepared payload match."""
        expected = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM approvals WHERE id=?", (id,)
            ).fetchone()
            if not row or row["status"] != "approved" or row["action"] != action:
                return False
            actual = json.dumps(
                json.loads(row["payload"]), sort_keys=True, separators=(",", ":")
            )
            if actual != expected:
                return False
            changed = self.conn.execute(
                "UPDATE approvals SET status='used' WHERE id=? AND status='approved'",
                (id,),
            ).rowcount
            self.conn.commit()
            return changed == 1

    def approvals(self):
        return self.rows("SELECT * FROM approvals ORDER BY created_at DESC LIMIT 100")

    def put_swarm(self, data):
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO swarms VALUES (?,?,?)",
                (data["id"], json.dumps(data), self.now()),
            )
            self.conn.commit()

    def swarms(self):
        return [
            json.loads(x["data"])
            for x in self.rows("SELECT data FROM swarms ORDER BY updated_at DESC")
        ]

    def backup(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(path)
        with self.lock:
            self.conn.backup(target)
        target.close()

    def restore(self, path: Path):
        source = sqlite3.connect(path)
        with self.lock:
            source.backup(self.conn)
            self.conn.commit()
        source.close()

    def purge_history(self):
        with self.lock:
            self.conn.executescript(
                "DELETE FROM messages; DELETE FROM sessions; DELETE FROM approvals;"
            )
            self.conn.commit()
