"""B-77 step 5: scripts/public_links.py switches links to the public repo and nothing else."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("public_links", Path(__file__).resolve().parents[1] / "scripts" /
                                              "public_links.py")
pl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pl)


def test_link_matches_the_private_repo_only():
    assert pl.LINK.sub(pl.PUBLIC, "git clone https://github.com/vedacool/veda.git") == \
        "git clone https://github.com/vedacool/veda-kelantan.git"
    assert pl.LINK.sub(pl.PUBLIC, "(+https://github.com/vedacool/veda; research)") == \
        "(+https://github.com/vedacool/veda-kelantan; research)"
    assert not pl.LINK.search("https://github.com/vedacool/veda-kelantan")       # never a second time
    assert not pl.LINK.search("https://github.com/vedacool/vedanta")


def test_dry_run_changes_the_user_facing_links_and_keeps_the_private_mentions():
    changes, kept = pl.plan(pl.PUBLIC)
    changed = {str(c[0].relative_to(pl.ROOT)).replace("\\", "/") for c in changes if c[1] is not None}
    assert {"docs/JUDGES.md", "metadata.json", "app/ingest/jps.py"} <= changed
    kept_text = " ".join(k[2] for k in kept)
    assert "stays **PRIVATE and untouched**" in kept_text                   # build evidence, never switched
    assert all("vedacool/veda-kelantan" not in c[2] for c in changes if c[1] is not None)


def test_the_script_and_its_test_are_never_swept():
    """B-98: both hold private links on purpose (the constant, the test inputs) - an --apply must not rewrite them."""
    changes, kept = pl.plan(pl.PUBLIC)
    touched = {str(c[0].relative_to(pl.ROOT)).replace("\\", "/") for c in changes + kept}
    assert pl.SKIP == {"scripts/public_links.py", "tests/test_public_links.py"} and not pl.SKIP & touched
    for p in pl.SKIP:                                     # without the exclusion they would be rewritten
        assert pl.LINK.search((pl.ROOT / p).read_text(encoding="utf-8")), p
    assert pl.PRIVATE == "https://github.com/vedacool/veda" and pl.PUBLIC != pl.PRIVATE
