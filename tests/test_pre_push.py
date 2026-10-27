"""B-99: the pre-push gate (scripts/precommit.py push) - which pushes it skips, and that a dirty tree is refused."""
import importlib.util

from app import config

spec = importlib.util.spec_from_file_location("precommit", config.ROOT / "scripts" / "precommit.py")
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


def test_only_docs_and_media_skip_the_gate():
    assert pc._doc_only({"docs/EVIDENCE.md", "docs/media/v2/b96/home-375-en.png", "x/clip.mp4"})
    assert not pc._doc_only({"docs/EVIDENCE.md", "app/web/live.html"})
    assert not pc._doc_only({"README.md"}) and not pc._doc_only({"README.md", "docs/x.md"})   # A-P3-18: tests read it
    assert not pc._doc_only({"tests/test_card.py"}) and not pc._doc_only(set())


def test_pushed_files_come_from_the_pushed_range(monkeypatch):
    calls = []
    monkeypatch.setattr(pc, "_git", lambda *a: calls.append(a) or "README.md\ndocs/x.md\n")
    files = pc._pushed_files("refs/heads/main " + "a" * 40 + " refs/heads/main " + "b" * 40 + "\n")
    assert files == {"README.md", "docs/x.md"} and calls[-1] == ("diff", "--name-only", "--no-renames", "b" * 40 + ".." + "a" * 40)
    assert pc._pushed_files("refs/heads/x " + "0" * 40 + " refs/heads/x " + "b" * 40 + "\n") == set()   # delete


def test_a_dirty_tree_blocks_the_push(monkeypatch, capsys):
    monkeypatch.setattr(pc, "_pushed_files", lambda _: {"app/main.py"})
    monkeypatch.setattr(pc, "_git", lambda *a: " M app/main.py\n" if a[0] == "status" else "")
    assert pc.pre_push("") == 1 and "PUSH BLOCKED" in capsys.readouterr().out
    monkeypatch.setattr(pc, "_git", lambda *a: "?? docs/notes.md\n" if a[0] == "status" else "")
    monkeypatch.setattr(pc, "_pushed_files", lambda _: {"docs/notes.md"})
    assert pc.pre_push("") == 0                                   # docs-only push: skipped before the tree check


def test_pushing_a_commit_that_is_not_checked_out_is_blocked(monkeypatch, capsys):
    """Audit 27 Oct A-P3-19: the tests run on the checked-out tree, so only HEAD may be pushed."""
    head, other, tag = "a" * 40, "c" * 40, "d" * 40
    commits = {"HEAD": head, head + "^{commit}": head, other + "^{commit}": other, tag + "^{commit}": head}
    monkeypatch.setattr(pc, "_pushed_files", lambda _: {"app/main.py"})
    monkeypatch.setattr(pc, "_git", lambda *a: commits.get(a[1], "") + "\n" if a[0] == "rev-parse" else "")
    line = "refs/heads/feature " + other + " refs/heads/feature " + "b" * 40 + "\n"
    assert pc.pre_push(line) == 1 and "not the checked-out commit" in capsys.readouterr().out
    assert pc._not_checked_out("refs/heads/main " + head + " refs/heads/main " + "b" * 40 + "\n") == []
    assert pc._not_checked_out("refs/heads/x " + "0" * 40 + " refs/heads/x " + "b" * 40 + "\n") == []   # a delete
    # A-P3-38: an annotated tag on HEAD is pushed as the tag object - it points at HEAD, so it is fine
    assert pc._not_checked_out("refs/tags/v1 " + tag + " refs/tags/v1 " + "0" * 40 + "\n") == []


def test_a_rename_of_code_into_a_doc_name_runs_the_gate(tmp_path):
    """Audit 26 Oct (Cowork): `git mv app/loop.py app/loop.md` must not pass as docs-only."""
    import os
    import subprocess
    # Inside a git hook (the pre-push gate runs this suite) git sets GIT_DIR / GIT_INDEX_FILE etc.; inherited, they
    # point `git -C tmp_path` at the REAL repository - this test then overwrote its user.name / user.email and
    # committed there (26 Oct). The throwaway repo must see no GIT_* variable.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    git = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True, text=True,  # noqa: E731
                                    env=env).stdout
    git("init", "-q")
    git("config", "user.email", "t@example.invalid")
    git("config", "user.name", "t")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "loop.py").write_text("x = 1", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "a")
    base = git("rev-parse", "HEAD").strip()
    git("mv", "app/loop.py", "app/loop.md")
    git("commit", "-qm", "b")
    files = set(git("diff", "--name-only", "--no-renames", f"{base}..HEAD").split())
    assert files == {"app/loop.py", "app/loop.md"} and not pc._doc_only(files)
