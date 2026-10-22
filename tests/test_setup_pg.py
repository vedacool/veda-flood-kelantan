"""Tests for B-05: db/schema.sql, scripts/setup_pg.py and run_ddl(setup=True).

Live tests run only with VEDA_LIVE=1 (needs veda-pg running and registered).
"""
import importlib.util
import os
import re

import pytest

from app import trace
from app.adapters import zetaris

ROOT = trace.ROOT
spec = importlib.util.spec_from_file_location("setup_pg", ROOT / "scripts" / "setup_pg.py")
setup_pg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup_pg)


def test_schema_creates_every_table_idempotently():
    stmts = setup_pg.schema_statements()
    created = {m.group(1) for s in stmts for m in [re.match(r"CREATE TABLE IF NOT EXISTS (\w+)", s)] if m}
    assert created == set(setup_pg.TABLES)
    assert not [s for s in stmts if re.match(r"\s*(DROP|TRUNCATE|DELETE)\b", s, re.IGNORECASE)]
    assert not [s for s in stmts if re.match(r"CREATE TABLE (?!IF NOT EXISTS)", s)]


def test_create_datasource_needs_setup_flag(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "false")
    trace.start_run("t", log_dir=tmp_path, quiet=True)
    try:
        with pytest.raises(zetaris.ZetarisError) as e:
            zetaris.run_ddl('CREATE DATASOURCE x OPTIONS (jdbcdriver "d")', agent="Healer")
        assert e.value.kind == "not_allowed"
    finally:
        trace.end_run()
    assert zetaris.ddl_problem('CREATE DATASOURCE veda_pg OPTIONS ()', setup=True) is None
    assert zetaris.ddl_problem('CREATE DATASOURCES x', setup=True) is not None


def test_schema_split_respects_quotes(tmp_path, monkeypatch):
    f = tmp_path / "s.sql"
    f.write_text("CREATE TABLE a (x text DEFAULT 'a;b -- not a comment'); -- real comment\nSELECT 1;", encoding="utf-8")
    monkeypatch.setattr(setup_pg, "SCHEMA", f)
    assert setup_pg.schema_statements() == ["CREATE TABLE a (x text DEFAULT 'a;b -- not a comment')", "SELECT 1"]


@pytest.mark.parametrize("value, ok", [("A" * 16, True), ("abc_DEF-123456789", True), ("short", False),
                                       ('quote"inside1234567', False), ("space inside 123456", False)])
def test_role_password_rule(value, ok):
    assert bool(setup_pg.PASSWORD_OK.match(value)) is ok


def test_bind_is_localhost_only():
    assert setup_pg.BIND.startswith("127.0.0.1:")


def test_constraints_have_unique_names():
    names = [n for n, _, _ in setup_pg.CONSTRAINTS]
    assert len(names) == len(set(names)) and {"river_levels_station_fk", "river_levels_level_range"} <= set(names)


live = pytest.mark.skipif(os.getenv("VEDA_LIVE") != "1", reason="live veda-pg/Zetaris test: set VEDA_LIVE=1")


@live
def test_every_table_answers_through_zetaris(tmp_path):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    trace.start_run("live B-05 test", log_dir=tmp_path, quiet=True)
    try:
        counts = setup_pg.smoke_check()
    finally:
        trace.end_run()
    assert set(counts) == set(setup_pg.TABLES)
    assert all(isinstance(n, int) for n in counts.values())


@live
def test_readonly_role_cannot_write():
    import psycopg
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    with psycopg.connect(host=setup_pg.config.PG_HOST, port=setup_pg.HOST_PORT, dbname="veda", user=setup_pg.RO_ROLE,
                         password=os.environ["VEDA_PG_RO_PASSWORD"], autocommit=True) as conn:
        conn.execute("SELECT COUNT(*) FROM source_registry")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO source_registry (source_id, name, kind) VALUES ('x', 'x', 'x')")
