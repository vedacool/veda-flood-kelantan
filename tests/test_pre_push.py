"""B-99: the pre-push gate (scripts/precommit.py push) - which pushes it skips, and that a dirty tree is refused."""
import importlib.util

from app import config

spec = importlib.util.spec_from_file_location("precommit", config.ROOT / "scripts" / "precommit.py")
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


def test_only_docs_and_media_skip_the_gate():
    assert pc._doc_only({"README.md", "docs/EVIDENCE.md", "docs/media/v2/b96/home-375-en.png", "x/clip.mp4"})
    assert not pc._doc_only({"README.md", "app/web/live.html"})
    assert not pc._doc_only({"tests/test_card.py"}) and not pc._doc_only(set())


def test_pushed_files_come_from_the_pushed_range(monkeypatch):
    calls = []
    monkeypatch.setattr(pc, "_git", lambda *a: calls.append(a) or "README.md\ndocs/x.md\n")
    files = pc._pushed_files("refs/heads/main " + "a" * 40 + " refs/heads/main " + "b" * 40 + "\n")
    assert files == {"README.md", "docs/x.md"} and calls[-1] == ("diff", "--name-only", "b" * 40 + ".." + "a" * 40)
    assert pc._pushed_files("refs/heads/x " + "0" * 40 + " refs/heads/x " + "b" * 40 + "\n") == set()   # delete


def test_a_dirty_tree_blocks_the_push(monkeypatch, capsys):
    monkeypatch.setattr(pc, "_pushed_files", lambda _: {"app/main.py"})
    monkeypatch.setattr(pc, "_git", lambda *a: " M app/main.py\n" if a[0] == "status" else "")
    assert pc.pre_push("") == 1 and "PUSH BLOCKED" in capsys.readouterr().out
    monkeypatch.setattr(pc, "_git", lambda *a: "?? docs/notes.md\n" if a[0] == "status" else "")
    monkeypatch.setattr(pc, "_pushed_files", lambda _: {"README.md"})
    assert pc.pre_push("") == 0                                   # docs-only push: skipped before the tree check
