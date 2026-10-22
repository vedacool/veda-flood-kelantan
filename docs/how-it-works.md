# How VEDA works
_Module contracts (inputs → outputs → failure behaviour). Filled in as modules are built._

## Guard rails (B-65) — `scripts/codemap.py`, `scripts/precommit.py`, `tests/test_architecture.py`, `.githooks/`
- **Inputs:** the repo's Python files (`app/`, `scripts/`, `run.py`), all git-tracked files (secret scan), the local `.env` (only to know which secret values must never appear), the commit message.
- **Outputs:** `docs/CODEMAP.md` (module → purpose, public functions, callers), regenerated and staged on every commit; pass/fail for 6 guard rules; pass/fail for the backlog-ID check.
- **Failure behaviour:** any failed rule exits non-zero → git refuses the commit and prints the file:line and the rule broken. Secret values are never printed, only where they were found. Rules 1–2 skip `spikes/`; the secret scan covers every tracked file.
