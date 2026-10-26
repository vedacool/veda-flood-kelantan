"""B-77 step 5: scripts/public_links.py switches links to the public repo and nothing else."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("public_links", Path(__file__).resolve().parents[1] / "scripts" /
                                              "public_links.py")
pl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pl)


def test_link_matches_the_private_repo_only():
    assert pl.LINK.sub(pl.PUBLIC, "git clone https://github.com/vedacool/veda.git") == \
        "git clone https://github.com/vedacool/veda-flood-kelantan.git"
    assert pl.LINK.sub(pl.PUBLIC, "(+https://github.com/vedacool/veda; research)") == \
        "(+https://github.com/vedacool/veda-flood-kelantan; research)"
    assert not pl.LINK.search("https://github.com/vedacool/veda-flood-kelantan")  # never a second time
    assert not pl.LINK.search("https://github.com/vedacool/veda-kelantan")
    assert not pl.LINK.search("https://github.com/vedacool/vedanta")


def test_a_rename_moves_the_old_public_links_only():
    """26 Oct: the public repo is vedacool/veda-flood-kelantan (was veda-kelantan): --from the old public name; the
    new name is never matched by the old one (veda-kelantan is not a prefix of veda-flood-kelantan)."""
    assert pl.PUBLIC == "https://github.com/vedacool/veda-flood-kelantan"
    changes, _ = pl.plan(pl.PUBLIC, "https://github.com/vedacool/veda-kelantan")
    assert [c for c in changes if c[1] is not None] == []                   # applied: nothing left on the old name


def test_the_sweep_is_applied_and_keeps_the_private_mentions():
    """Cowork 26 Oct: --apply ran (the public repo is vedacool/veda-flood-kelantan). A dry run now changes nothing; the
    user-facing links point at the public repo; the lines that name the private repo on purpose are kept."""
    changes, kept = pl.plan(pl.PUBLIC)
    assert [c for c in changes if c[1] is not None] == []                   # nothing left to switch
    kept_text = " ".join(k[2] for k in kept)
    assert "stays **PRIVATE and untouched**" in kept_text                   # build evidence, never switched
    for path in ("docs/JUDGES.md", "metadata.json", "app/ingest/jps.py", "app/web/judges.html"):
        text = (pl.ROOT / path).read_text(encoding="utf-8")
        assert pl.PUBLIC in text and not pl.LINK.search(text), path


def test_the_script_and_its_test_are_never_swept():
    """B-98: both hold private links on purpose (the constant, the test inputs) - an --apply must not rewrite them."""
    changes, kept = pl.plan(pl.PUBLIC)
    touched = {str(c[0].relative_to(pl.ROOT)).replace("\\", "/") for c in changes + kept}
    assert pl.SKIP == {"scripts/public_links.py", "tests/test_public_links.py"} and not pl.SKIP & touched
    for p in pl.SKIP:                                     # without the exclusion they would be rewritten
        assert pl.LINK.search((pl.ROOT / p).read_text(encoding="utf-8")), p
    assert pl.PRIVATE == "https://github.com/vedacool/veda" and pl.PUBLIC != pl.PRIVATE


def test_the_judge_path_still_works_after_the_sweep():
    """Cowork audit P1-3: after --apply the clone URL changes to the public repo; each clone names its folder, so the
    next line's `cd veda` stays right (a bare `git clone .../veda-flood-kelantan.git` would make a veda-flood-kelantan folder)."""
    import re
    judges = pl.LINK.sub(pl.PUBLIC, (pl.ROOT / "docs" / "JUDGES.md").read_text(encoding="utf-8")).splitlines()
    clones = [i for i, line in enumerate(judges) if line.startswith("git clone ")]
    assert len(clones) == 2
    for i in clones:
        url, folder = re.fullmatch(r"git clone (\S+) (\S+)", judges[i]).groups()
        assert url == pl.PUBLIC + ".git" and judges[i + 1] == f"cd {folder}" and folder == "veda", judges[i:i + 2]
