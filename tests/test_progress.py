"""B-76: the live view (CLI + web) says which model ACTUALLY answered each Nightshift call - taken from the response."""
from app import progress


def rec(status, **details):
    return {"action": "nightshift.chat", "agent_name": "Critic", "status": status, "output_summary": "empty response",
            "duration_ms": 10714, "details": details}


def test_answered_call_names_the_served_model_and_receipt():
    line = progress.describe(rec("success", requested_model="meterless/fast",
                                 served_model="nvidia/nemotron-3.5-lightning-30b-a3b", receipt_id="req_m9vp8735"))
    assert line == ("  Critic: answered by nvidia/nemotron-3.5-lightning-30b-a3b via Nightshift, receipt req_m9vp8735, "
                    "10.7 s")
    assert "meterless/fast" not in line                      # the route asked for is not the model that answered


def test_failed_call_says_no_model_answered():
    assert progress.describe(rec("failed")) == "  ! Critic: no model answered (empty response)"


def test_step_lines_are_plain_words():
    """A5 (24 Oct evening): no "full path, answer in BM: full:" and no "(F1)" in the step lines people see."""
    line = progress.describe({"action": "route", "output_summary": "full path, answer in BM",
                              "decision": "full: Sg. Golok di Kg. Jenob (F1) is rising (0.47 m in 1 h, 1.08 m in 3 h)"})
    assert line == "  full path, answer in BM: Sg. Golok di Kg. Jenob is rising (0.47 m in 1 h, 1.08 m in 3 h)"
    assert progress.describe({"action": "route", "output_summary": "quick path, answer in English",
                              "decision": "quick: linked gauges below Alert"}) == \
        "  quick path, answer in English: linked gauges below Alert"
    assert progress.plain("Sg. Kelantan di Jambatan Tendong (F2) at warning") == "Sg. Kelantan di Jambatan Tendong at warning"
