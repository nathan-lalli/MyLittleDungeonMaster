"""Persistent campaign memory (SQLite, one file per campaign).  Characters are stored
as JSON blobs in the `characters` table alongside the narrative state tables.

Three layers, because a 1-3B model with a 4k context cannot "remember" a whole campaign by itself:
  1. Structured state  - NPCs, locations, quests, party members, hard facts (always injected, compact)
  2. Rolling summary   - older story folded into a paragraph by the LLM
  3. Recent messages   - last few turns verbatim
"""
import datetime
import json
import os
import re
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS entities(
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
    description TEXT DEFAULT '', status TEXT DEFAULT '', updated_turn INTEGER DEFAULT 0,
    UNIQUE(kind, name));
CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY, turn INTEGER, role TEXT NOT NULL, content TEXT NOT NULL,
    summarized INTEGER DEFAULT 0, ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, turn INTEGER, text TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS summaries(id INTEGER PRIMARY KEY, upto_message_id INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS characters(
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
    data TEXT NOT NULL, updated_turn INTEGER DEFAULT 0);
"""

KINDS = ("pc", "npc", "location", "quest", "premise")


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "campaign"


class Memory:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self._lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    # ---- meta / turn counter -------------------------------------------------
    def get_meta(self, key, default=None):
        with self._lock:
            row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key, value):
        with self._lock:
            self.db.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                            (key, str(value)))
            self.db.commit()

    @property
    def turn(self):
        return int(self.get_meta("turn", 0))

    def next_turn(self):
        t = self.turn + 1
        self.set_meta("turn", t)
        self.set_meta("last_played", datetime.date.today().isoformat())
        return t

    # ---- messages ---------------------------------------------------------------
    def add_message(self, role, content):
        with self._lock:
            cur = self.db.execute("INSERT INTO messages(turn,role,content) VALUES(?,?,?)", (self.turn, role, content))
            self.db.commit()
            return cur.lastrowid

    def unsummarized(self):
        with self._lock:
            rows = self.db.execute("SELECT id, role, content FROM messages WHERE summarized=0 ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def mark_summarized(self, upto_id):
        with self._lock:
            self.db.execute("UPDATE messages SET summarized=1 WHERE id<=?", (upto_id,))
            self.db.commit()

    # ---- summary ----------------------------------------------------------------
    def latest_summary(self):
        with self._lock:
            row = self.db.execute("SELECT text FROM summaries ORDER BY id DESC LIMIT 1").fetchone()
        return row["text"] if row else ""

    def add_summary(self, upto_message_id, text):
        with self._lock:
            self.db.execute("INSERT INTO summaries(upto_message_id,text) VALUES(?,?)", (upto_message_id, text))
            self.db.commit()

    # ---- entities & facts -----------------------------------------------------------
    def upsert_entity(self, kind, name, description="", status=""):
        name = name.strip()
        if not name or kind not in KINDS:
            return
        with self._lock:
            self.db.execute(
                """INSERT INTO entities(kind,name,description,status,updated_turn) VALUES(?,?,?,?,?)
                   ON CONFLICT(kind,name) DO UPDATE SET
                     description=CASE WHEN excluded.description!='' THEN excluded.description ELSE description END,
                     status=CASE WHEN excluded.status!='' THEN excluded.status ELSE status END,
                     updated_turn=excluded.updated_turn""",
                (kind, name, description.strip(), status.strip(), self.turn))
            self.db.commit()

    def entities(self, kind=None):
        q, args = "SELECT kind,name,description,status FROM entities", ()
        if kind:
            q, args = q + " WHERE kind=?", (kind,)
        with self._lock:
            rows = self.db.execute(q + " ORDER BY updated_turn DESC, id DESC", args).fetchall()
        return [dict(r) for r in rows]

    def add_fact(self, text):
        text = text.strip()
        if text:
            with self._lock:
                self.db.execute("INSERT OR IGNORE INTO facts(turn,text) VALUES(?,?)", (self.turn, text))
                self.db.commit()

    def facts(self, limit=12):
        with self._lock:
            rows = self.db.execute("SELECT text FROM facts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [r["text"] for r in reversed(rows)]

    # ---- prompt injection -----------------------------------------------------------
    def state_block(self, max_chars=1200):
        """Compact world state. Most-recently-touched entities come first so truncation drops the stalest."""
        lines = []
        prem = self.entities("premise")
        if prem:
            lines.append(f"Premise: {prem[0]['description']}")
        for label, kind in (("Party", "pc"), ("Quests", "quest"), ("NPCs", "npc"), ("Places", "location")):
            for e in self.entities(kind):
                s = f" [{e['status']}]" if e["status"] else ""
                lines.append(f"{label[:-1] if label.endswith('s') else label}: {e['name']}{s} - {e['description']}")
        for f in self.facts():
            lines.append(f"Fact: {f}")
        out, used = [], 0
        for ln in lines:
            if used + len(ln) + 1 > max_chars:
                break
            out.append(ln)
            used += len(ln) + 1
        return "\n".join(out)

    @staticmethod
    def list_campaigns(campaigns_dir):
        """Return campaign info dicts for every .db file in campaigns_dir, newest first."""
        import glob
        campaigns = []
        for db_path in glob.glob(os.path.join(campaigns_dir, "*.db")):
            name = os.path.splitext(os.path.basename(db_path))[0]
            try:
                db = sqlite3.connect(db_path)
                rows = {r[0]: r[1] for r in db.execute("SELECT key, value FROM meta").fetchall()}
                db.close()
            except sqlite3.Error:
                rows = {}
            campaigns.append({
                "name": name,
                "path": db_path,
                "turn": int(rows.get("turn", 0)),
                "theme": rows.get("theme", "unknown"),
                "last_played": rows.get("last_played", "never"),
            })
        campaigns.sort(key=lambda c: c["last_played"], reverse=True)
        return campaigns

    # ---- characters ----------------------------------------------------------------
    def save_character(self, char_data: dict):
        name = char_data["name"]
        with self._lock:
            self.db.execute(
                "INSERT INTO characters(name,data,updated_turn) VALUES(?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET data=excluded.data, updated_turn=excluded.updated_turn",
                (name, json.dumps(char_data), self.turn))
            self.db.commit()

    def get_character(self, name: str) -> dict | None:
        with self._lock:
            row = self.db.execute("SELECT data FROM characters WHERE name=?", (name,)).fetchone()
        return json.loads(row["data"]) if row else None

    def all_characters(self) -> list[dict]:
        with self._lock:
            rows = self.db.execute(
                "SELECT data FROM characters ORDER BY updated_turn DESC").fetchall()
        return [json.loads(r["data"]) for r in rows]

    def reset(self):
        with self._lock:
            for t in ("entities", "messages", "facts", "summaries", "meta", "characters"):
                self.db.execute(f"DELETE FROM {t}")
            self.db.commit()
