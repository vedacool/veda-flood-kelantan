"""Stable IDs for the World Model - a Python port of the Meterless reference (engines/world-model/reference,
stableIds.ts, Apache-2.0). Agents that see the same thing must arrive at the same id without coordinating.

    normalize_name("José  García") == normalize_name("Jose Garcia")      # NFKD, accents/NBSP/zero-width gone
    entity_id_from_name("person", "Jose Garcia") -> "ent_<16 hex>"       # type is part of the key
    external_id("station", "jps", "_DKBR0007") -> "station:jps:_DKBR0007"
"""
import hashlib
import json
import re
import unicodedata

_COMBINING = re.compile(r"[̀-ͯ]")
_ZERO_WIDTH = re.compile(r"[​-‍﻿]")


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(value):
    """Deterministic JSON: sorted keys, None-valued keys dropped, no spaces (same rules as the reference)."""
    if isinstance(value, dict):
        keys = sorted(k for k, v in value.items() if v is not None)
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + canonical_json(value[k]) for k in keys) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def normalize_name(name):
    """NFKD -> strip combining marks -> strip zero-width -> lowercase -> collapse whitespace -> trim.
    Never abbreviates or drops word characters ("Acme Corp" != "Acme Corporation")."""
    text = unicodedata.normalize("NFKD", name)
    text = _COMBINING.sub("", text)
    text = _ZERO_WIDTH.sub("", text)
    return re.sub(r"\s+", " ", text.lower()).strip()


def external_id(entity_type, system, ext_id):
    """Externally keyed entity: the literal grammar type:system:id."""
    return f"{entity_type}:{system}:{ext_id}"


def entity_id_from_name(entity_type, name):
    """Name-keyed entity: ent_ + first 16 hex of sha256('type:normalized name')."""
    return "ent_" + sha256_hex(f"{entity_type}:{normalize_name(name)}")[:16]


def context_id_from_attrs(context_type, attrs, parent=None):
    return "ctx_" + sha256_hex(f"{context_type}:{canonical_json(attrs)}:{parent or ''}")[:16]


def relationship_id(from_id, rel_type, to_id, context=None, valid_from=None):
    """Re-adding the identical edge is a no-op (same id)."""
    return "rel_" + sha256_hex(f"{from_id}|{rel_type}|{to_id}|{context or ''}|{valid_from or ''}")[:16]


def fact_id(about, predicate, value, asserted_at, source_kind, source_url=None):
    """Content-addressed: asserting the identical fact twice is a no-op."""
    return "fact_" + sha256_hex(
        f"{about}|{predicate}|{canonical_json(value)}|{asserted_at}|{source_kind}|{source_url or ''}")[:16]
