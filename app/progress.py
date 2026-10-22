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
    if a == "safety" and rec.get("status") != "success":
        return f"  safety: {out}"
    if rec.get("status") == "failed" and a != "run_end":
        return f"  ! {rec.get('agent_name')}: {out}"
    return None
