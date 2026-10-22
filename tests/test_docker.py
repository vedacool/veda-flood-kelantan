"""B-19 guard tests for the container: Python 3.13 base pinned by digest, no secrets or local state copied in,
not running as root, the API as the entry point."""
from app import trace

DOCKERFILE = (trace.ROOT / "Dockerfile").read_text(encoding="utf-8")
IGNORE = (trace.ROOT / ".dockerignore").read_text(encoding="utf-8").split()


def test_base_image_is_python_313_slim_pinned_by_digest():
    base = next(line for line in DOCKERFILE.splitlines() if line.startswith("FROM "))
    assert base.startswith("FROM python:3.13-slim@sha256:") and len(base.split("@sha256:")[1]) == 64


def test_secrets_and_local_state_never_enter_the_image():
    for entry in (".env", ".env.*", ".venv/", ".git/", "logs/", "data/world/", "CLAUDE.local.md"):
        assert entry in IGNORE, entry
    assert "COPY . " not in DOCKERFILE and ".env" not in DOCKERFILE.split("# Never")[0].split("COPY")[-1]


def test_runs_as_a_normal_user_and_starts_the_api():
    assert "\nUSER veda\n" in DOCKERFILE and 'CMD ["python", "-m", "app.main"]' in DOCKERFILE
    assert "VEDA_HOST=0.0.0.0" in DOCKERFILE and "HEALTHCHECK" in DOCKERFILE
