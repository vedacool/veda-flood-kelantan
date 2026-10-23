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
