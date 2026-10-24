"""scripts/seed_places.py must be safe to re-run (24 Oct fresh-clone check): osm_place_features points at places, so
the seed upserts places and only removes places that left the CSV - their OSM rows first."""
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seed_places  # noqa: E402


class FakeConn:
    def __init__(self):
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append((" ".join(sql.split()), params))
        return self

    def fetchall(self):
        return [(0, 6.02, 101.97)]


def test_seed_upserts_places_and_keeps_osm_rows_of_kept_places(monkeypatch):
    conn = FakeConn()

    @contextmanager
    def transaction():
        yield conn
    monkeypatch.setattr(seed_places.pg, "transaction", transaction)
    rows = [r for r in seed_places.load_rows() if r["place_id"] in ("rantau_panjang", "tumpat")]
    seed_places.seed(rows)
    statements = [s for s, _ in conn.sql]
    assert "DELETE FROM places" not in statements                         # never every place
    osm = next(i for i, s in enumerate(statements) if s.startswith("DELETE FROM osm_place_features WHERE NOT"))
    gone = next(i for i, s in enumerate(statements) if s.startswith("DELETE FROM places WHERE NOT"))
    assert osm < gone and conn.sql[gone][1] == (["rantau_panjang", "tumpat"],)
    assert all("ON CONFLICT (place_id) DO UPDATE" in s for s in statements if s.startswith("INSERT INTO places"))
