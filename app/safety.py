"""Safety gate (B-58): the LAST check on every answer before it leaves VEDA - plain code, after the Critic, on every
path (quick, full, fallback, replay, place not covered). BUILD_BRIEF section 7, in one place.

    answer = safety.gate(answer, card, evidence, forecast)

Rules (each fix is one `System | safety` trace line; a clean answer gets one "all passed" line):
  1. never NORMAL when the controlling data is missing or stale -> the INSUFFICIENT DATA card
  2. never advice to walk, wade, drive or swim through water (EN + BM; a sentence that warns against it is fine)
     -> the card alone, without the AI explanation
  3. the disclaimer + 999 / 991 in the answer's language
  4. ranges, never one precise number: a projected range whose low and high are equal is dropped (Husaini 22 Oct)
  5. a replay answer starts with its "REPLAY · ..." title
  6. (B-73) never says a PPS is open, never predicts a road / bridge being cut off -> the card alone
"""
from app import card as card_mod
from app import trace
from app.agents import critic
from app.agents.coordinator import SAFETY

AGENT = "System"


def _unsafe(text):
    return critic.unsafe_sentences(text)


def _render(answer, card, lang):
    return card_mod.render(card, lang, answer.get("explanation"), low_confidence=bool(answer.get("low_confidence")))


def gate(answer, card=None, evidence=None, forecast=None):
    """Check (and if needed fix) one answer. Returns the answer, with answer['safety'] = the list of fixes."""
    answer = dict(answer)
    lang = answer.get("language") if answer.get("language") in SAFETY else "en"
    fixes = []
    if card is not None:
        card = dict(card)
        if card["verdict"] == "NORMAL" and not (evidence or {}).get("usable"):                         # rule 1
            card.update(verdict="INSUFFICIENT_DATA", action=card_mod.ADVICE["INSUFFICIENT_DATA"], level_name=None,
                        gauge=None, range_24h=None, confidence="low")
            answer.update(explanation=None, drafted_by="code")
            fixes.append("NORMAL without fresh controlling data -> INSUFFICIENT DATA card")
        r = card.get("range_24h")
        if r and r.get("min") == r.get("max"):                                                          # rule 4
            card["range_24h"] = None
            fixes.append(f"projected range {r['min']}-{r['max']} m has no width -> range line dropped")
        if fixes:
            answer.update(text=_render(answer, card, lang), card=card)
        bad = _unsafe(answer["text"])
        if bad:                                                                                         # rule 2
            answer.update(explanation=None, drafted_by="code", card=card)
            answer["text"] = _render(answer, card, lang)
            fixes.append(f"unsafe advice removed: {bad[0][:80]!r} -> card without the explanation")
            if _unsafe(answer["text"]):
                fixes.append("the card itself contains unsafe wording - BUG, check card.ADVICE")
        claim = card_mod.osm_claim(answer["text"])
        if claim:                                                                                       # rule 6
            answer.update(explanation=None, drafted_by="code", card=card)
            answer["text"] = _render(answer, card, lang)
            fixes.append(f"{claim} -> card without the explanation")
            if card_mod.osm_claim(answer["text"]):
                fixes.append("the card itself claims an open PPS or a cut-off road - BUG, check card.T")
        title = card.get("replay")
        if title and not answer["text"].startswith(title):                                              # rule 5
            answer["text"] = f"{title}\n{answer['text']}"
            fixes.append(f"replay answer did not start with '{title}' -> added")
    if answer.get("safety_line") != SAFETY[lang]:                                                        # rule 3
        answer["safety_line"] = SAFETY[lang]
        fixes.append(f"disclaimer + 999 / 991 set in {lang}")
    answer["safety"] = fixes
    trace.step(AGENT, "safety", input_summary=f"answer ({answer.get('drafted_by')}, {lang})",
               output_summary="; ".join(fixes) if fixes else "all safety checks passed",
               status="fallback" if fixes else "success",
               decision="BUILD_BRIEF section 7: never NORMAL on missing data, never into water, disclaimer, ranges, "
                        "replay label, no open-PPS / cut-off claims", details={"fixes": fixes})
    return answer
