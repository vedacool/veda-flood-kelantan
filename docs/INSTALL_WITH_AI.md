# Install VEDA with your AI assistant

**What you'll get**
- **Offline demo in minutes:** the real agents on the Nov 2024 flood replay and the test scenes - no keys, no Docker.
- **Live mode (about 1 hour):** today's JPS river readings through Zetaris, Nemotron through Meterless Nightshift.
- **Your keys stay with you:** the assistant never sees, types or stores them - you put them in yourself.

Copy everything in the box below into Claude Code, Cursor or a similar coding assistant, opened in an empty folder.

```text
Please install VEDA (a flood-risk app for Kelantan) on this computer and get it running. Follow these rules exactly.

Steps
1. Clone the repository I give you (ask me for the address if I have not given it) and open the cloned folder.
2. Run the installer from that folder:
   - Windows (PowerShell): .\install.ps1
     (if Windows blocks it: powershell -ExecutionPolicy Bypass -File .\install.ps1)
   - macOS / Linux: ./install.sh
   It creates .venv, installs the pinned packages, creates .env from .env.example only if .env does not exist,
   runs the doctor and starts VEDA on http://127.0.0.1:8000. Without keys VEDA runs the offline demo - that is fine.
3. Run the doctor and show me its output: .\.venv\Scripts\python -m veda doctor (Windows) or
   .venv/bin/python -m veda doctor (macOS / Linux). It is read-only.
4. Only if I want live mode: fix each line marked ✗ (or X) in the order shown, using the README section
   "Live setup". Run the doctor again after each fix. A JPS line marked ✗ is a report only - do not try to fix it.

Rules
- NEVER print, store, type, paste or commit a key, token or password - not in the chat, a file, a command or a log.
  Never show the contents of .env.
- When a key is needed, stop and ask ME to do it myself:
  - the NVIDIA key goes into Nightshift's Providers tab (Nightshift's own window), never into .env;
  - the Zetaris URL and API token, and the Nightshift runtime token, go into .env - I open .env and type them in.
- Never use sudo or admin rights, and never delete, overwrite or move a file without asking me first.
- Do not change VEDA's code, and do not disable any security or certificate check.
- Keep VEDA on 127.0.0.1 (this computer only). Do not make it public.
- If any step fails twice, stop, and explain in plain words what failed and what you think the cause is.

When you finish, tell me the link to open and whether VEDA is running in the offline demo or live, and why
(the doctor's last line says it).
```

**Stuck without an assistant?** Run `python -m veda doctor` in the VEDA folder (inside `.venv`): every ✗ line comes with
a one-line fix. VEDA is decision support only - not an official warning. Emergency 999 · APM 991.
