"""Append-only event store for the World Model (WorldStoreService).

Every change is an event (seq, kind, payload, at, actor, run). The current state is REBUILT from the events
(canonical reconstruction), so any belief can be traced back to the event - and the source - that created it.
Storage: in memory (tests) or a SQLite file (one events table, write-through, single writer per process).
Each mutation also gets an audit entry with a strictly increasing seq, optionally mirrored to a JSONL file.
"""
import copy
import json
import sqlite3
import threading
from pathlib import Path


class EventStore:
    """Events + rebuilt state (entities, contexts, relationships, facts, aliases) + audit log."""

    def __init__(self, path=None, audit_jsonl=None):
        self.path = Path(path) if path else None
        self.audit_jsonl = Path(audit_jsonl) if audit_jsonl else None
        self.lock = threading.Lock()
        self.events, self.audit_log = [], []
        self.state = {"entities": {}, "contexts": {}, "relationships": {}, "facts": {}, "aliases": {},
                      "observations": {}}
        self.merge_queue = []
        self._db = None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(self.path, check_same_thread=False)
            self._db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, kind TEXT NOT NULL, "
                             "payload TEXT NOT NULL, at TEXT NOT NULL, actor TEXT, run_id TEXT)")
            self._db.commit()
            for seq, kind, payload, at, actor, run_id in self._db.execute(
                    "SELECT seq, kind, payload, at, actor, run_id FROM events ORDER BY seq"):
                self._apply({"seq": seq, "kind": kind, "payload": json.loads(payload), "at": at, "actor": actor,
                             "run_id": run_id})

    # -- write path -------------------------------------------------------------------------------------------
    def append(self, kind, payload, at, actor=None, run_id=None):
        """Persist one event (write-through) and apply it to the state. Returns the event."""
        event = {"seq": len(self.events) + 1, "kind": kind, "payload": copy.deepcopy(payload), "at": at,
                 "actor": actor, "run_id": run_id}
        if self._db:
            self._db.execute("INSERT INTO events (seq, kind, payload, at, actor, run_id) VALUES (?, ?, ?, ?, ?, ?)",
                             (event["seq"], kind, json.dumps(payload, ensure_ascii=False), at, actor, run_id))
            self._db.commit()
        self._apply(event)
        return event

    def log_audit(self, kind, actor, summary, event=None, run_id=None, at=None):
        """One audit entry per mutation, seq strictly increasing."""
        entry = {"seq": (self.audit_log[-1]["seq"] + 1) if self.audit_log else 1, "at": at, "kind": kind,
                 "actor": actor, "summary": summary, "event_seq": event["seq"] if event else None, "run_id": run_id}
        self.audit_log.append(entry)
        if self.audit_jsonl:
            self.audit_jsonl.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    # -- reducer (canonical reconstruction) -------------------------------------------------------------------
    def _apply(self, event):
        self.events.append(event)
        kind, p, st = event["kind"], copy.deepcopy(event["payload"]), self.state
        if kind == "upsert_entity":
            current = st["entities"].get(p["id"])
            if current:
                current["attrs"].update(p.get("attrs") or {})
                for k in ("name", "type", "state"):
                    if p.get(k) is not None:
                        current[k] = p[k]
                current["updated_at"] = p["updated_at"]
                current["sources"].append(p["source"])
            else:
                p["sources"] = [p.pop("source")]
                st["entities"][p["id"]] = p
        elif kind == "upsert_context":
            current = st["contexts"].get(p["id"])
            if current:
                current["attrs"].update(p.get("attrs") or {})
                current["updated_at"] = p["updated_at"]
            else:
                st["contexts"][p["id"]] = p
        elif kind == "alias":
            st["aliases"][p["alias_id"]] = p["primary_id"]
        elif kind == "relate":
            # Superseding: a new open edge with the same (from, type, context) but a different target closes the
            # previous open edge at the new edge's valid_from (same rule as the reference store).
            for other in st["relationships"].values():
                if (other["from"] == p["from"] and other["type"] == p["type"]
                        and (other.get("context") or "") == (p.get("context") or "")
                        and other["to"] != p["to"] and not other.get("valid_to") and not other.get("superseded_by")):
                    other["valid_to"] = p["valid_from"]
                    other["superseded_by"] = p["id"]
            st["relationships"].setdefault(p["id"], p)
        elif kind == "assert_fact":
            # payload carries the conflict decision: superseded_by (if this fact lost) and supersedes (rivals it beat)
            st["facts"].setdefault(p["id"], p)
            for fid in p.get("supersedes", []):
                if fid in st["facts"]:
                    st["facts"][fid]["superseded_by"] = p["id"]
        elif kind == "observation":
            st["observations"][p["external_id"]] = p
        elif kind == "mark_stale":
            for oid in p["observation_ids"]:
                if oid in st["observations"]:
                    st["observations"][oid]["stale"] = True

    def resolve_alias(self, entity_id):
        seen = set()
        while entity_id in self.state["aliases"] and entity_id not in seen:
            seen.add(entity_id)
            entity_id = self.state["aliases"][entity_id]
        return entity_id

    def close(self):
        if self._db:
            self._db.close()
            self._db = None
