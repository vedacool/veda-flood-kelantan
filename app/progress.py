"""Live progress (B-17 / B-19): one short, plain line per important trace step - shared by the CLI and the web page.

    line = progress.describe(record)      # None for steps the user does not need to see
"""

STEP_LABELS = {"plan": "Understanding the question", "gather": "Checking river gauges, rain and warnings",
               "forecast": "Working out the risk", "draft": "Writing the answer", "critique": "Checking the answer",
               "revise": "Fixing the answer"}


def describe(rec):
    """A short line for one trace record, or None."""
    a, out = rec.get("action"), rec.get("output_summary") or ""
    if a == "state":
        return f"> {STEP_LABELS.get(rec.get('input_summary'), rec.get('input_summary'))}"
    if a == "route":
        return f"  {out}: {rec.get('decision') or ''}"
    if a == "forecast.verdict":
        return f"  verdict {out}"
    if a == "critic.review":
        return f"  review: {out}"
    if a == "budget":
        return f"  ! {out}"
    if a == "replay":
        return f"  {out} ({rec.get('decision')})"
    if a == "nightshift.chat":       # B-76: which model ACTUALLY answered, from the response (not the request)
        d = rec.get("details") or {}
        who = rec.get("agent_name")
        if rec.get("status") == "success" and d.get("served_model"):
            receipt = f", receipt {d['receipt_id']}" if d.get("receipt_id") else ""
            took = f", {rec['duration_ms'] / 1000:.1f} s" if rec.get("duration_ms") else ""
            return f"  {who}: answered by {d['served_model']} via Nightshift{receipt}{took}"
        return f"  ! {who}: no model answered ({out})"
    if a == "data.sources":            # B-71(a): which sources were chosen / skipped for this place
        d = rec.get("details") or {}
        chosen, skipped = d.get("chosen") or [], d.get("skipped") or []
        return (f"  sources: {len(chosen)} used ({', '.join(c.split(' (')[0] for c in chosen[:4])}"
                f"{', ...' if len(chosen) > 4 else ''}); {len(skipped)} skipped"
                + (f" ({'; '.join(skipped[:2])}{'; ...' if len(skipped) > 2 else ''})" if skipped else ""))
    if a == "critic.request":          # B-71(b): the Critic asks the Data & Reconciler for a missing source
        return f"  Critic -> Data & Reconciler: {out}"
    if a == "rain.upstream":           # B-88: rain upstream (and when it may arrive) + rain here
        return f"  rain: {out}"
    if a == "forecast.met_warning":    # rule A not applied yet: said plainly
        return f"  ! {out} - {rec.get('decision')}"
    if a == "card.advice":
        return f"  advice: {out}"
    if a == "data.request":
        return f"  Data & Reconciler -> Critic: {out}"
    if a == "verdict.recomputed":
        return f"  {out}"
    if a == "ai.fallback":             # B-86: AI fallback marked plainly, next to the served-model lines
        return f"  ! {rec.get('agent_name')}: {out}"
    if a == "safety" and rec.get("status") != "success":
        return f"  safety: {out}"
    if rec.get("status") == "failed" and a != "run_end":
        return f"  ! {rec.get('agent_name')}: {out}"
    return None
