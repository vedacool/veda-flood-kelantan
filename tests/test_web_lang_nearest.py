"""B3: the page shows Main's result fields explanation_lang and nearest_covered (app/main.py result_json)."""
from app import trace

PAGE = (trace.ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")


def test_wording_en_and_bm():
    for text in ('expl_lang_note: "Written in Bahasa Melayu when you asked"', 'expl_recheck: "Check again in English"',
                 'expl_lang_note: "Ditulis dalam English semasa anda bertanya"', 'expl_recheck: "Semak semula dalam BM"',
                 'check_nearest: "Check {place} ({km} km from {from})"',
                 'check_nearest: "Semak {place} ({km} km dari {from})"'):
        assert text in PAGE, text
    assert "dari sini" not in PAGE and "km away" not in PAGE    # the distance is from the place asked about


def test_language_note_only_when_the_paragraph_is_in_the_other_language():
    assert "const el = result.explanation_lang;" in PAGE
    assert '$("a-expl-lang").hidden = !v.explanation || !el || el === lang;' in PAGE
    # the re-ask uses the page language's own standard question for this place
    recheck = PAGE.split('$("a-expl-recheck").addEventListener("click"', 1)[1].split("});", 1)[0]
    assert 'ask(UI[lang].q_default.replace("{town}", place), place)' in recheck


def test_not_covered_reply_offers_the_nearest_covered_place_as_a_big_button():
    assert "const near = result && result.nearest_covered;" in PAGE
    assert ('near && near.from_place\n        ? t("check_nearest").replace("{place}", town).replace("{km}", near.km)'
            '.replace("{from}", near.from_place)\n        : t("check_town")') in PAGE     # no asked place: no distance
    assert '"primary wide big-choice"' in PAGE
    assert ".big-choice { grid-column: 1 / -1; width: 100%; min-height: 64px;" in PAGE


def test_the_fields_exist_in_the_result():
    main = (trace.ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert 'out["explanation_lang"]' in main and 'out["nearest_covered"]' in main
