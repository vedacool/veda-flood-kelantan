"""World Model idempotency check - Python port of the Meterless reference script
(engines/world-model/reference/scripts/idempotency-check.ts, Apache-2.0).

Re-running ingest on the same input must produce the same world state (empty diff).
    python scripts/wm_idempotency_check.py            # exit 0 on empty diff
    python scripts/wm_idempotency_check.py --mutate   # proves the check can fail: edits one title, exit 0 only if
                                                      # the diff is NON-empty (exit 1 otherwise)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engines.world_model import WorldModel  # noqa: E402

FIXTURE = [
    {"external_id": "art-101", "title": "Fed holds rates steady amid mixed signals", "at": "2026-05-17T14:00:00.000Z",
     "source": {"kind": "rss", "url": "https://example.com/a", "at": "2026-05-17T14:00:00.000Z"},
     "entities": [{"type": "person", "name": "Jerome Powell"}, {"type": "org", "name": "Federal Reserve"}]},
    {"external_id": "art-102", "title": "Powell signals patience on cuts", "at": "2026-05-17T16:30:00.000Z",
     "source": {"kind": "rss", "url": "https://example.com/b", "at": "2026-05-17T16:30:00.000Z"},
     "entities": [{"type": "person", "name": "Jerome Powell"}, {"type": "org", "name": "Federal Reserve"}]},
    {"external_id": "art-103", "title": "Markets unmoved by the announcement", "at": "2026-05-17T18:00:00.000Z",
     "source": {"kind": "api", "at": "2026-05-17T18:00:00.000Z"},
     "entities": [{"type": "org", "name": "Federal Reserve"}]},
]


def main(argv):
    mutate = "--mutate" in argv
    world = WorldModel(storage="memory", namespace="idem")
    r1 = world.ingest(FIXTURE)
    shape1 = world.state_shape_canonical()
    print(f"run 1: processed={r1['processed']} changed={r1['changed']}")
    second = ([{**FIXTURE[0], "title": FIXTURE[0]["title"] + " (edited)"}] + FIXTURE[1:]) if mutate else FIXTURE
    r2 = world.ingest(second)
    shape2 = world.state_shape_canonical()
    print(f"run 2: processed={r2['processed']} skipped={r2['skipped_unchanged']} changed={r2['changed']}")
    if shape1 == shape2:
        print("diff: empty")
        if mutate:
            print("expected the mutation to change state; it did not", file=sys.stderr)
            return 1
        return 0
    print("diff: NON-EMPTY")
    return 0 if mutate else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
