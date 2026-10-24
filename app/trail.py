""""How VEDA got there": four plain lines from a run - Data, Forecast, Critic, Safety gate (B-96, Cowork wireframes v3).

    lines = trail.how_lines(out, "en")      # out = scenes.compact(main.result_json(run)) - the parts of a run result

Shared by the Scenes test page and (Main) the answer page. Plain words only: never SAMPLE_MODE, internal ids, rule
names or confidence decimals - those stay in the technical log. Built from the run's own output: the answer view's
plain "why" and source notes, and the agents' trace steps (did the Critic ask the Data agent for more data, did it
approve, what did the safety gate do).
"""
import re

from app.view import HEADLINE

AGENTS = {"gather": {"en": "Data agent", "ms": "Ejen Data"}, "forecast": {"en": "Forecast agent", "ms": "Ejen Ramalan"},
          "critique": {"en": "Critic", "ms": "Penyemak"}, "safety": {"en": "Safety gate", "ms": "Semakan keselamatan"}}
W = {
    "used": {"en": "Used {n} of {m} sources.", "ms": "Menggunakan {n} daripada {m} sumber."},
    "left_out": {"en": "Left out: {items}.", "ms": "Diketepikan: {items}."},
    "more": {"en": "and {n} more", "ms": "dan {n} lagi"},
    "level": {"en": "{level}. {why}", "ms": "{level}. {why}"},
    "asked": {"en": "Asked the Data agent for a fresh upstream reading.",
              "ms": "Meminta Ejen Data mencari bacaan hulu yang baharu."},
    "found": {"en": "It found {name}.", "ms": "Ia menemui {name}."},
    "nothing": {"en": "Nothing fresh was found.", "ms": "Tiada bacaan baharu ditemui."},
    "recomputed": {"en": "The level was worked out again.", "ms": "Tahap dikira semula."},
    "approved": {"en": "Checked the facts again and approved the answer.",
                 "ms": "Menyemak semula fakta dan meluluskan jawapan."},
    "sent_back": {"en": "Sent the answer back to be fixed.", "ms": "Memulangkan jawapan untuk dibetulkan."},
    "safe": {"en": "All safety checks passed.", "ms": "Semua semakan keselamatan lulus."},
    "fixed": {"en": "Made {n} safety fix(es) before the answer went out.",
              "ms": "Membuat {n} pembetulan keselamatan sebelum jawapan dihantar."},
}
SHOWN_LEFT_OUT = 3


def _lines_of(out, key):
    return [ln for s in out.get("steps", []) if s.get("key") == key for ln in s.get("lines", [])]


def _short(name):
    return re.sub(r"^(River level|River upstream|Paras sungai|Sungai di hulu)\s*:\s*", "", name or "")


def how_lines(out, lang):
    """[{"key", "who", "text"}] for gather, forecast, critique, safety - in the page language."""
    lang = lang if lang in ("en", "ms") else "en"
    rows = []
    sources = (out.get("sources_by_lang") or {}).get(lang) or out.get("sources") or []
    if sources:
        used = [s for s in sources if s.get("used")]
        out_ = [s for s in sources if not s.get("used")]
        text = W["used"][lang].format(n=len(used), m=len(sources))
        if out_:
            items = [f"{_short(s['name'])}, {s['note'].split(':', 1)[-1].strip()}" if s.get("note") else _short(s["name"])
                     for s in out_[:SHOWN_LEFT_OUT]]
            if len(out_) > SHOWN_LEFT_OUT:
                items.append(W["more"][lang].format(n=len(out_) - SHOWN_LEFT_OUT))
            text += " " + W["left_out"][lang].format(items="; ".join(items))
        rows.append({"key": "gather", "who": AGENTS["gather"][lang], "text": text})
    verdict = out.get("verdict")
    if verdict:
        why = ((out.get("why") or {}).get(lang) or "").strip()
        level = (HEADLINE.get(verdict) or {}).get(lang, verdict)
        rows.append({"key": "forecast", "who": AGENTS["forecast"][lang],
                     "text": W["level"][lang].format(level=level, why=why).strip()})
    critic = _lines_of(out, "critique")
    if critic:
        parts = []
        if any(ln.get("action") == "critic.request" for ln in critic):
            parts.append(W["asked"][lang])
            answer = next((ln["text"] for ln in critic if ln.get("action") == "data.request"), "")
            found = re.match(r"found (.+?) \(", answer)
            parts.append(W["found"][lang].format(name=_short(re.sub(r"\s*\(F\d\)", "", found.group(1))))
                         if found else W["nothing"][lang])
            if any(ln.get("action") == "verdict.recomputed" for ln in _lines_of(out, "forecast") + critic):
                parts.append(W["recomputed"][lang])
        reviews = [ln["text"] for ln in critic if ln.get("action") == "critic.review"]
        approved = bool(reviews) and reviews[-1].startswith("approve")
        parts.append(W["approved"][lang] if approved else W["sent_back"][lang])
        rows.append({"key": "critique", "who": AGENTS["critique"][lang], "text": " ".join(parts)})
    safety = _lines_of(out, "safety")
    if safety:
        texts = [ln.get("text") or "" for ln in safety]
        if any(t.startswith("all safety checks passed") for t in texts):
            text = W["safe"][lang]
        else:
            fixes = re.search(r"(\d+) fix", " ".join(texts))
            text = W["fixed"][lang].format(n=fixes.group(1) if fixes else 1)
        rows.append({"key": "safety", "who": AGENTS["safety"][lang], "text": text})
    return rows
