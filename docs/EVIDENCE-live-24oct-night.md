# Live runs, 24 Oct 2026 night (21:38-22:36 MYT) - Nemotron's judgement in the loop (Part 7)

Every live run since Part 7 Phase 1, on this machine (live JPS data through Zetaris, Nemotron 3.5 Super VL through
Meterless Nightshift, app `veda-deep`). Nightshift was restarted before each run (its memory is held in the running
process, so each run starts empty). **Redacted:** no river readings - levels are VEDA's words only. Receipts are
Nightshift's own ids (`receipts.jsonl` on this machine); a call that never answered has no receipt (Nightshift logs it
as failed at the same second). Questions: Rantau Panjang (EN), Pasir Mas (BM), Kota Bharu (EN), "at risk in the next
two days" (full path).

| Run | Code | Place | Rules | Nemotron (confidence) | Final | AI calls (agent: outcome, time, model, receipt) | Total |
|---|---|---|---|---|---|---|---|
| 20261024-213824-3194 | Phase 1 (943441f) | Rantau Panjang (EN) | NORMAL | did not run: no AI-written text to check | NORMAL | Coordinator: failed (NVIDIA 500), 2.4 s, no receipt<br>Coordinator: failed (NVIDIA 500), 2.2 s, no receipt | 14.5 s |
| 20261024-213852-e3eb | Phase 1 (943441f) | Pasir Mas (BM) | WATCH | WATCH (medium) | WATCH | Coordinator: ok, 32.5 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_neh2jtu9`<br>Critic: ok, 21.8 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_ddyiwqan` | 65.5 s |
| 20261024-214010-fcc9 | Phase 1 (943441f) | Kota Bharu (EN) | WATCH | WATCH (medium) | WATCH | Coordinator: ok, 26.8 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_mnraap82`<br>Coordinator: ok, 17.6 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_pv088s72`<br>Critic: ok, 21.6 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_qzw4ao42` | 79.3 s |
| 20261024-220155-c759 | Follow-ups (4f2ff21) | Rantau Panjang (EN) | WATCH | did not run: Nightshift unavailable | WATCH | Coordinator: ok, 18.3 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_oo09kpuu`<br>Critic: timeout, 45.0 s, no receipt | 71.5 s |
| 20261024-220320-d8fc | Follow-ups (4f2ff21) | Pasir Mas (BM) | WATCH | WATCH (medium) | WATCH | Coordinator: ok, 37.4 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_7terxsp1`<br>Critic: ok, 15.6 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_bpx4kfn5` | 63.4 s |
| 20261024-220437-0377 | Follow-ups (4f2ff21) | Kota Bharu (EN) | WATCH | did not run: Nightshift unavailable | WATCH | Coordinator: ok, 34.1 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_fh1kpbfp`<br>Coordinator: empty reply, 34.8 s, no receipt<br>Coordinator: ok, 36.8 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_sw21rfyu`<br>Critic: timeout, 21.7 s, no receipt | 140.0 s |
| 20261024-223209-939c | Task 1 (e2b82bc) | Rantau Panjang (EN) | WATCH | WATCH (medium) - **explanation timed out → facts-only judgement took over** | WATCH | Coordinator: timeout, 45.0 s, no receipt<br>Critic: ok, 23.4 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_15f6mn9c` | 81.7 s |
| 20261024-223343-7c96 | Task 1 (e2b82bc) | Pasir Mas (BM) | WATCH | WATCH (medium) | WATCH | Coordinator: ok, 29.3 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_plwtb5ha`<br>Critic: ok, 14.8 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_tt264vzl` | 54.6 s |
| 20261024-223451-3932 | Task 1 (e2b82bc) | Kota Bharu (EN) | WATCH | WATCH (high) | WATCH | Coordinator: ok, 20.4 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_9qo2it81`<br>Coordinator: ok, 13.1 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_5zsqgkao`<br>Critic: ok, 39.4 s, nvidia/nemotron-3.5-super-vl-120b-a12b, `rcpt_req_67nlanqh` | 85.5 s |

**Totals (9 runs):** Nemotron's judgement ran in 6 of 9; it agreed 6, raised 0, judged lower
0. Where it did not run, the Critic's review call failed (timeout / budget) or - before the facts-only call
existed (run 213824) - the explanation call failed. No run changed level. Longest run: see the Total column (all
within the 150 s budget).

**What this shows:** the AI's level is recorded on every full run and is used only when it is higher, cited and
checked; on these nine live runs it never had a reason to raise. Do not read this as "the AI catches surges": in a
separate re-judgement of the 24 Oct 18:30 facts for Rantau Panjang (a fast rise at Kg. Jenob upstream, still below
its Alert level), Nemotron kept NORMAL 3 of 3.

How to reproduce: the run ids are this machine's traces (`logs/trace-<run_id>.jsonl`, not committed - they contain live
readings); `scripts/` + the README's live setup.
