"""WorldModel - VEDA's shared, provenance-stamped world state (Meterless World Model engine, Python).

One object all four agents read and write. Rules from the Meterless spec, enforced here:
    * every write carries provenance {kind, at}  -> no provenance, no write (prov-001)
    * stable ids: same thing -> same id without coordination (sid-001/002)
    * name-keyed duplicates: >= 0.85 similarity auto-merge, 0.82-0.85 review queue, else new (band-001)
    * ingest is idempotent: the same batch twice changes nothing (idem-001/002)
    * relationships are bitemporal: a superseding edge closes the old one; point-in-time queries (bitemp-001)
    * every mutation writes an audit entry with a strictly increasing seq (audit-001)
Timestamps come from the observations / provenance, never the wall clock, so re-runs are reproducible.
"""
from app.engines.world_model.resolve import decide, name_similarity
from app.engines.world_model.stable_ids import (canonical_json, entity_id_from_name, external_id, fact_id,
                                                relationship_id, sha256_hex)
from app.engines.world_model.store import EventStore

SERVICES = {  # the spec's service boundaries (§12.5) and whether VEDA uses them - the wired-vs-helper map (§10.3)
    "WorldStoreService": "live - append-only event log (memory or SQLite), canonical reconstruction, audit",
    "IngestPipelineService": "live - idempotent observation ingest (reconcile, persist, edges, aggregates, mark "
                             "stale); story clustering not used by VEDA",
    "ContextBuilderService": "live - structured place context with provenance and selection reasons",
    "RelationshipService": "live - typed bitemporal edges, neighbors_of(at=...)",
    "EnrichmentService": "dormant - no enrichment jobs yet",
    "ControlPlaneService": "dormant - no query/mutation endpoints yet (agents call the Python API)",
    "SupervisorAgent": "dormant - stale/conflict facts are written by the Critic instead",
}


class ProvenanceError(ValueError):
    """A write arrived without provenance {kind, at}."""


def _provenance(source):
    if not isinstance(source, dict) or not source.get("kind") or source.get("at") in (None, ""):
        raise ProvenanceError("World Model: every write carries provenance (kind + at). No provenance, no write.")
    return dict(source)


class WorldModel:
    """Shared world state. storage='memory' or a SQLite file path."""

    def __init__(self, storage="memory", namespace="veda", audit_jsonl=None, conflict_policy="most-recent-wins"):
        if not namespace:
            raise ValueError("WorldModel: namespace is required")
        self.namespace = namespace
        self.conflict_policy = conflict_policy
        self.store = EventStore(None if storage == "memory" else storage, audit_jsonl=audit_jsonl)

    # -- entities and contexts --------------------------------------------------------------------------------
    def upsert_entity(self, type, name=None, external_key=None, attrs=None, source=None, state="active"):
        """Create or update an entity. external_key={'system','id'} -> id 'type:system:id'; else name-keyed."""
        src = _provenance(source)
        with self.store.lock:
            if external_key:
                eid = external_id(type, external_key["system"], external_key["id"])
            else:
                if not name:
                    raise ValueError("World Model: name-keyed entities need a name (or an external_key)")
                eid = entity_id_from_name(type, name)
                for other in list(self.store.state["entities"].values()):
                    if other["type"] != type or other["id"] == eid or not other.get("name"):
                        continue
                    sim = name_similarity(name, other["name"])
                    verdict = decide(sim)
                    if verdict == "auto-merge":
                        ev = self.store.append("alias", {"alias_id": eid, "primary_id": other["id"],
                                                         "reason": f"similarity {sim:.3f}"}, src["at"], "resolver",
                                               src.get("run_id"))
                        self.store.log_audit("auto-merge", "resolver", f"{name} -> {other['name']} ({sim:.3f})", ev,
                                             src.get("run_id"), src["at"])
                        eid = other["id"]
                        break
                    if verdict == "review" and not any({p["left_id"], p["right_id"]} == {eid, other["id"]}
                                                       for p in self.store.merge_queue):
                        self.store.merge_queue.append({"left_id": eid, "right_id": other["id"], "left_name": name,
                                                       "right_name": other["name"], "similarity": sim,
                                                       "status": "pending"})
                        self.store.log_audit("merge-proposed", "resolver", f"{name} ~ {other['name']} ({sim:.3f})",
                                             None, src.get("run_id"), src["at"])
            payload = {"id": eid, "type": type, "name": name, "attrs": dict(attrs or {}), "state": state,
                       "source": src, "created_at": src["at"], "updated_at": src["at"]}
            ev = self.store.append("upsert_entity", payload, src["at"], src.get("agent"), src.get("run_id"))
            self.store.log_audit("upsert_entity", src.get("agent") or "system", f"{eid} ({type})", ev,
                                 src.get("run_id"), src["at"])
            return self.store.state["entities"][eid]

    def upsert_context(self, type, external_key, attrs=None, source=None):
        """Contexts are where entities live or are observed from (here: data sources and runs)."""
        src = _provenance(source)
        with self.store.lock:
            cid = external_id(type, external_key["system"], external_key["id"])
            payload = {"id": cid, "type": type, "attrs": dict(attrs or {}), "source": src, "created_at": src["at"],
                       "updated_at": src["at"]}
            ev = self.store.append("upsert_context", payload, src["at"], src.get("agent"), src.get("run_id"))
            self.store.log_audit("upsert_context", src.get("agent") or "system", f"{cid} ({type})", ev,
                                 src.get("run_id"), src["at"])
            return self.store.state["contexts"][cid]

    # -- relationships ----------------------------------------------------------------------------------------
    def relate(self, from_id, type, to_id, valid_from=None, valid_to=None, context=None, attrs=None, source=None):
        """Typed, bitemporal edge. Same (from, type, context) with a new target closes the old edge."""
        src = _provenance(source)
        with self.store.lock:
            frm, to = self.store.resolve_alias(from_id), self.store.resolve_alias(to_id)
            rid = relationship_id(frm, type, to, context, valid_from)
            if rid in self.store.state["relationships"]:
                return self.store.state["relationships"][rid]          # content-addressed no-op
            payload = {"id": rid, "from": frm, "type": type, "to": to, "context": context, "attrs": attrs or {},
                       "valid_from": valid_from or src["at"], "valid_to": valid_to, "source": src}
            ev = self.store.append("relate", payload, src["at"], src.get("agent"), src.get("run_id"))
            self.store.log_audit("relate", src.get("agent") or "system", f"{frm} -[{type}]-> {to}", ev,
                                 src.get("run_id"), src["at"])
            return self.store.state["relationships"][rid]

    # -- facts ------------------------------------------------------------------------------------------------
    def assert_fact(self, about, predicate, value, confidence=0.5, context=None, source=None):
        """A timestamped claim about an entity. Identical fact twice = no-op. Conflicts: most recent wins."""
        src = _provenance(source)
        with self.store.lock:
            about = self.store.resolve_alias(about)
            fid = fact_id(about, predicate, value, src["at"], src["kind"], src.get("url"))
            if fid in self.store.state["facts"]:
                return self.store.state["facts"][fid]
            rivals = [f for f in self.store.state["facts"].values()
                      if f["about"] == about and f["predicate"] == predicate and not f.get("superseded_by")]
            winner = max(rivals, key=lambda f: f["asserted_at"], default=None)
            new_wins = winner is None or src["at"] >= winner["asserted_at"]
            payload = {"id": fid, "about": about, "predicate": predicate, "value": value, "confidence": confidence,
                       "context": context, "source": src, "asserted_at": src["at"],
                       "superseded_by": None if new_wins else winner["id"],
                       "supersedes": [f["id"] for f in rivals] if new_wins else []}
            ev = self.store.append("assert_fact", payload, src["at"], src.get("agent"), src.get("run_id"))
            self.store.log_audit("assert_fact", src.get("agent") or "system", f"{about} {predicate}={value!r}", ev,
                                 src.get("run_id"), src["at"])
            return self.store.state["facts"][fid]

    def facts_about(self, about, predicate=None, include_superseded=False):
        about = self.store.resolve_alias(about)
        return sorted((f for f in self.store.state["facts"].values() if f["about"] == about
                       and (predicate is None or f["predicate"] == predicate)
                       and (include_superseded or not f.get("superseded_by"))),
                      key=lambda f: (f["predicate"], f["asserted_at"]))

    # -- ingest (IngestPipelineService) -----------------------------------------------------------------------
    def ingest(self, observations):
        """Idempotent ingest of observations {external_id, title, at, source, entities:[{type, name}]}.
        Steps follow the spec's canonical order; an unchanged observation (same content hash) is skipped.
        Returns {run_id, processed, skipped_unchanged, changed}."""
        before = self.state_shape_canonical()
        run_id = "run_" + sha256_hex(canonical_json([o["external_id"] for o in observations]))[:12]
        processed, skipped = 0, 0
        for obs in observations:                                   # step 3: persist primary records
            src = _provenance(obs.get("source"))
            content_hash = sha256_hex(canonical_json({k: v for k, v in obs.items() if k != "source"}))
            known = self.store.state["observations"].get(obs["external_id"])
            if known and known["content_hash"] == content_hash:
                skipped += 1
                continue
            processed += 1
            entity_ids = [self.upsert_entity(e["type"], name=e.get("name"), external_key=e.get("external_key"),
                                             source=src)["id"] for e in obs.get("entities", [])]
            with self.store.lock:
                ev = self.store.append("observation", {"external_id": obs["external_id"], "title": obs.get("title"),
                                                       "at": obs["at"], "content_hash": content_hash,
                                                       "entity_ids": entity_ids, "stale": False, "source": src},
                                       obs["at"], src.get("agent"), run_id)
                self.store.log_audit("ingest", "pipeline", f"observation {obs['external_id']}", ev, run_id, obs["at"])
            for eid in entity_ids:                                 # step 6: persist edges
                self.relate(f"observation:{self.namespace}:{obs['external_id']}", "mentions", eid,
                            context=obs["external_id"], source=src)
        return {"run_id": run_id, "processed": processed, "skipped_unchanged": skipped,
                "changed": before != self.state_shape_canonical()}

    # -- read surface -----------------------------------------------------------------------------------------
    def neighbors_of(self, entity_id, via=None, at=None, in_context=None):
        """Entities linked to entity_id. Without `at`: only open edges (now). With `at`: edges valid at that time."""
        rid, out = self.store.resolve_alias(entity_id), []
        for rel in self.store.state["relationships"].values():
            if via and rel["type"] != via:
                continue
            if in_context is not None and rel.get("context") != in_context:
                continue
            if at is not None:
                if (rel.get("valid_from") and at < rel["valid_from"]) or (rel.get("valid_to") and at >= rel["valid_to"]):
                    continue
            elif rel.get("valid_to"):
                continue
            other = rel["to"] if rel["from"] == rid else rel["from"] if rel["to"] == rid else None
            if other and other in self.store.state["entities"]:
                out.append(self.store.state["entities"][other])
        return sorted(out, key=lambda e: e["id"])

    def edges(self, entity_id, via=None, direction="out", at=None):
        """Open (or valid-at) edges leaving (direction='out') or entering ('in') entity_id."""
        rid, key = self.store.resolve_alias(entity_id), ("from" if direction == "out" else "to")
        out = []
        for rel in self.store.state["relationships"].values():
            if rel[key] != rid or (via and rel["type"] != via):
                continue
            if at is None and rel.get("valid_to"):
                continue
            if at is not None and ((rel.get("valid_from") and at < rel["valid_from"])
                                   or (rel.get("valid_to") and at >= rel["valid_to"])):
                continue
            out.append(rel)
        return sorted(out, key=lambda r: (r.get("context") or "", r["to"], r["from"]))

    def entity(self, entity_id):
        return self.store.state["entities"].get(self.store.resolve_alias(entity_id))

    def audit(self):
        return list(self.store.audit_log)

    def merge_queue(self):
        return list(self.store.merge_queue)

    def state_shape_canonical(self):
        """Canonical JSON of the world (no wall-clock values) - equal strings mean equal worlds."""
        st = self.store.state
        shape = {
            "entities": {k: {"type": v["type"], "name": v.get("name"), "attrs": v["attrs"], "state": v.get("state")}
                         for k, v in st["entities"].items()},
            "contexts": {k: {"type": v["type"], "attrs": v["attrs"]} for k, v in st["contexts"].items()},
            "relationships": {k: {"from": v["from"], "type": v["type"], "to": v["to"], "context": v.get("context"),
                                  "valid_from": v.get("valid_from"), "valid_to": v.get("valid_to")}
                              for k, v in st["relationships"].items()},
            "facts": {k: {"about": v["about"], "predicate": v["predicate"], "value": v["value"],
                          "superseded_by": v.get("superseded_by")} for k, v in st["facts"].items()},
            "observations": {k: {"title": v.get("title"), "at": v["at"], "content_hash": v["content_hash"],
                                 "stale": v.get("stale")} for k, v in st["observations"].items()},
            "aliases": st["aliases"],
        }
        return canonical_json(shape)

    def manifest(self):
        """Which engine services are live vs dormant (the spec's wired-vs-helper map)."""
        st = self.store.state
        return {"engine": "Meterless World Model (Python implementation, VEDA)", "namespace": self.namespace,
                "services": SERVICES, "counts": {k: len(v) for k, v in st.items()},
                "events": len(self.store.events), "audit_entries": len(self.store.audit_log),
                "merge_queue": len(self.store.merge_queue)}

    def close(self):
        self.store.close()
