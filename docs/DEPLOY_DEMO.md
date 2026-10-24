# Public offline demo on the Dell Wyse 5070 (Tailscale Funnel)

For Husaini, on the Wyse (`wyse5070` on the tailnet; x86 Linux; also runs Pi-hole). The demo is VEDA **offline**:
the Nov 2024 past-flood replay and made-up test scenes only - no live JPS data, no Nemotron, no keys. Visitors reach
it at one public HTTPS address through Tailscale Funnel; nothing else on the Wyse is exposed.

```
visitor --HTTPS--> Tailscale Funnel --> 127.0.0.1:8765 --> proxy (nginx) --+--> veda      (SAMPLE_MODE, no internet)
                                                                            +--> feedback  (answers on a volume)
```
- **proxy** (`demo/nginx.conf`): per-visitor rate limits - 20 answers (and feedback requests) a minute, burst 10,
  and 120 page requests a minute, burst 60; then HTTP 429 - at most 3 open streams (answer steps, live log) per
  visitor and 10 in all - security headers (CSP, HSTS, nosniff, no framing). The demo strip, top bar and footer
  (with *Feedback*) come from the app's shared frame (B-96, `app/frame.py`), and the answer has its own feedback line;
  the proxy adds nothing to the pages; the feedback form wears the same frame - the public API (`/api/v1/`) and its docs page (`/api/docs`)
  with the same limits as an answer stream - `/admin`, run logs and FastAPI's own `/docs`, `/redoc`, `/openapi.json`
  closed (404), no access log (it would store IP addresses), visitors' addresses not passed on.
- **veda** (the normal VEDA image): `SAMPLE_MODE=true`, read-only filesystem, 1 GB memory limit, on an internal
  network with **no route out** (it cannot fetch anything, whatever the code does). Questions visitors type stay in
  memory (tmpfs) and vanish on restart.
- **feedback** (`demo/feedback/feedback.py`, Python standard library only): the form at `/feedback`, answers appended
  to `answers.jsonl` on the `veda-demo_feedback` volume. No IP, phone, email or address stored.
- All three restart unless stopped, so the demo comes back after a reboot. Docker keeps at most 3 × 10 MB of logs
  per service.

Commands below are for a Debian / Ubuntu-style system with `sudo`; run them in a terminal on the Wyse (SSH over the
tailnet is fine).

## Tonight (before the public repo exists): four commands
No git on the Wyse: the PC makes a bundle from `main` and Tailscale sends it over.

**On the PC** (PowerShell, in `E:\Project\veda`):
```
.venv\Scripts\python scripts\make_demo_bundle.py
tailscale file cp dist\veda-demo-<commit>.tar.gz wyse5070:
```
The first command builds `dist\veda-demo-<commit>.tar.gz` from `origin/main` (it refuses a commit older than
`a6a2280`, any secret-looking file or `.env` value, and anything that fails the JPS guard) and prints the exact file
name, its size and SHA256. Use that file name in the second command.

**On the Wyse:**
```
sudo tailscale file get ~/ && sudo chown "$USER": ~/veda-demo-*.tar.gz && tar -xzf ~/veda-demo-*.tar.gz -C ~
cd ~/veda-demo && bash demo/setup_wyse.sh
```
`setup_wyse.sh` does steps 1, 4 and 5 below in one go: it checks the machine (x86_64, 1.5 GB memory, 3 GB disk,
Docker - it never installs anything; without Docker it prints step 2 and stops), finds a free port (8765, or the
next free one), builds and starts the demo, runs the checks (`PASS` / `FAIL` each; nothing is published if one
fails), shows what Tailscale already serves, then asks **"Publish on Funnel port 443 or 8443?"** (only 8443 is
offered if 443 is already in use; `skip` publishes nothing). It then sets `VEDA_PUBLIC_URL` to the public address
(`https://<this machine's Tailscale name>`, plus `:8443` if used - read from Tailscale at run time, never stored in the
repo) and restarts VEDA, so the links in shared answers open the public demo. It prints the public link, the feedback
link and:
```
bash demo/setup_wyse.sh --export      # all feedback answers -> feedback-<date>.csv in the current folder
bash demo/setup_wyse.sh --stop        # Funnel off for the demo's port + containers down (answers kept); also
                                      # asks before turning off 443, in case Funnel was turned on there by hand
```
Then do step 6 (test from outside) by hand. Steps 1-9 below are the same thing done by hand, for reference.

## 1. Check the machine (2 min)
```
uname -m                       # x86_64
free -h                        # want >= 1.5 GB available (the demo uses at most ~1.2 GB)
df -h ~                        # want >= 3 GB free (images ~1 GB)
docker --version && docker compose version     # if either fails: step 2
sudo ss -ltnp | grep -E ':8765\b' || echo "port 8765 free"
tailscale version && tailscale status | head -3
```
If 8765 is taken, pick another free port and put `DEMO_PORT=<port>` in front of every `docker compose` command below
(and use it in step 5).

## 2. Install Docker (only if missing, 5 min)
```
curl -fsSL https://get.docker.com -o get-docker.sh     # Docker's official install script
less get-docker.sh                                     # read it first
sudo sh get-docker.sh
sudo usermod -aG docker "$USER"                        # then log out and back in
docker run --rm hello-world
```
Pi-hole: if it runs in Docker it keeps running; if it is installed natively it is not touched. The demo uses its own
networks and only port 8765 on 127.0.0.1.

## 3. Get the code (1 min)
```
git clone https://github.com/vedacool/veda-kelantan.git ~/veda-demo     # the public repo (after Monday)
cd ~/veda-demo
```
(Before the public repo exists: clone the private repo with your GitHub login.)

**Build from `main` at or after the app's demo mode** (private repo commit `a6a2280`, 24 Oct 2026: `VEDA_DEMO=1`
forces SAMPLE_MODE on, reads no `.env`, blocks live Zetaris / Nightshift calls and answers 404 for `/admin` and run
logs in the app itself). Check before building - the public repo has new commit IDs, so check the code:
```
git checkout main && git pull
grep -n "def demo_mode" app/config.py          # must print a line; if not, the code is too old - do not deploy
git merge-base --is-ancestor a6a2280 HEAD && echo "has a6a2280"     # private repo only
```

## 4. Build and start (5-10 min the first time)
```
cd ~/veda-demo
docker compose -f demo/compose.yaml --profile demo up -d --build
docker compose -f demo/compose.yaml --profile demo ps          # veda "healthy", proxy and feedback "running"
curl -s http://127.0.0.1:8765/health                           # {"status":"ok","sample_mode":true,...}
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/admin    # 404 (the proxy)
curl -s http://127.0.0.1:8765/ | grep -c 'class="vf-strip"'    # 1 (the demo strip)
docker compose -f demo/compose.yaml --profile demo exec -T proxy \
  wget -S -O /dev/null http://veda:8000/admin 2>&1 | grep HTTP/   # 404 from the app itself (behind the proxy)
```

## 5. Publish with Tailscale Funnel (5 min)
Funnel must be allowed for this machine: Tailscale admin console -> *Access controls* -> the policy has a `funnel`
node attribute for `wyse5070` (the console offers to add it the first time), and *DNS* -> *HTTPS certificates* is on.

First look at what is already served, so nothing of yours is replaced:
```
tailscale serve status
tailscale funnel status
```
If nothing uses port 443 on this machine:
```
sudo tailscale funnel --bg 8765
```
If 443 is already used by another `tailscale serve` (for example a Pi-hole page on the tailnet), use 8443 instead:
```
sudo tailscale funnel --bg --https=8443 8765
```
`tailscale funnel status` must now show **only** `http://127.0.0.1:8765` as public (Funnel on). The public address is
`https://wyse5070.<your-tailnet>.ts.net/` (with `:8443` if you used it). Pi-hole and the other services stay
tailnet-only: Funnel exposes only what is listed there. **Never run `tailscale serve reset` or `tailscale funnel reset`**
- they remove every serve setting on the Wyse, not just the demo.

## 6. Test it from outside (5 min)
On a phone **on mobile data, not on the tailnet** (or any computer logged out of Tailscale):
1. Open the public address: the dark one-line strip "Demo · past flood replay · not an official warning"
   is at the top (in BM after tapping BM). Link to share with judges and testers (opens the flood replay):
   `https://wyse5070.<your-tailnet>.ts.net/?replay=nov2024&at=2024-11-27%2019:30` -> tap **Rantau Panjang** -> Act now.
2. `…/admin` -> 404. `…/feedback` -> the form, in BM if the phone is in Malay; send one test answer -> *Thank you*.
3. The rate limit cannot be dodged with a fake header (from any computer outside the tailnet):
   ```
   for i in $(seq 30); do curl -s -o /dev/null -w '%{http_code}\n' -H "X-Forwarded-For: 10.9.$i.1" \
     https://wyse5070.<your-tailnet>.ts.net/feedback; done | sort | uniq -c
   ```
   Expect about 11 × `200` and the rest `429` (wait a minute before using the demo from that computer). If
   **all 30 are 200**, Funnel is not adding the visitor's address the
   way the proxy expects: in `demo/nginx.conf` change the line `"~(?<last>[^,\s]+)\s*$" $last;` to
   `"~." $remote_addr;` (one shared limit for all visitors together - safe, just stricter), then
   `docker compose -f demo/compose.yaml --profile demo up -d --build proxy` (the config is built into the proxy image)
   and test again.
4. The limit is **per visitor**, checked from two networks (audit 24 Oct). You need two devices on different
   networks, neither on the tailnet - for example phone A on mobile data and phone B (or a laptop) on another
   Wi-Fi. On **A**, open `…/feedback` and pull down to reload about 20 times quickly, until it shows
   `429 Too Many Requests`. Straight away on **B**, open `…/feedback`:
   - **B shows the form:** each visitor has their own limit - good.
   - **B also gets 429:** everyone shares one limit (Funnel is not passing the visitor's address). The demo is still
     safe, but one busy visitor slows everyone; tell Session B, and keep the step-3 fallback in mind.
   Wait a minute before using the demo from A again.
5. Nothing leaves VEDA's container (on the Wyse):
   ```
   docker compose -f demo/compose.yaml --profile demo exec -T veda python -c "import urllib.request; urllib.request.urlopen('https://api.open-meteo.com', timeout=5)"
   ```
   must fail with `URLError`.

## 7. While it runs
```
docker stats --no-stream veda-demo-veda-1 veda-demo-proxy-1 veda-demo-feedback-1   # memory under the limits
docker compose -f demo/compose.yaml --profile demo logs --tail 50 veda
```
Updating after a new commit: `git pull` then the `up -d --build` line from step 4.

**What visitors can see of each other:** the live log (`/live`) follows every run as it happens - the place and the
steps, never the question. The feedback form's answers are only on the Wyse.

## 8. Export the feedback
```
cd ~/veda-demo
docker compose -f demo/compose.yaml --profile demo exec -T feedback python feedback.py export > feedback-$(date +%F).csv
docker compose -f demo/compose.yaml --profile demo cp feedback:/data/answers.jsonl ./answers-$(date +%F).jsonl
```
The CSV has one row per answer: time (to the minute), language, the eight answers, first name and whether it may be
quoted (`quote_ok` - only quote people where it is `True`). Phone numbers and emails typed into answers already read
`[removed]`. Copy the files off the Wyse privately (they are not for the repo).

## 9. Stop it after judging (6 Nov 2026, results at 16:00 UTC)
```
sudo tailscale funnel --https=443 off          # or --https=8443 if you used it
tailscale funnel status                        # the demo is no longer listed
cd ~/veda-demo
# export the feedback first (step 8), then:
docker compose -f demo/compose.yaml --profile demo down          # containers gone; the answers volume is kept
docker compose -f demo/compose.yaml --profile demo down -v       # only when the answers are exported and no longer needed
```

## Three layers keep the demo offline and closed
1. **The app** (`VEDA_DEMO=1`, set in `demo/compose.yaml`; on main since `a6a2280`): SAMPLE_MODE is on even if
   `SAMPLE_MODE=false` is set, no `.env` is read, live Zetaris and Nightshift calls raise an error, and `/admin`,
   the approve route and run logs answer 404 "not in the public demo".
2. **The network:** VEDA's container has no route out (internal network).
3. **The proxy:** `/admin` and run logs answer 404 before they reach the app.

Checked together on 24 Oct 2026 (local Docker, main at `a6a2280`, demo profile, `SAMPLE_MODE=false` forced in on
purpose): `/health` reports `sample_mode: true`; 404 at both the proxy and the app; JPS, Open-Meteo and the host's
Zetaris / Nightshift ports unreachable; 11 answers then 429; banner, the BM feedback form and the five scenes as
expected.
