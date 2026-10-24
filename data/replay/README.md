# Replay and scene data

- `nov2024_anchors.csv` - the Nov 2024 past-flood replay: JPS river readings as **reported in the news**, each row with
  its source, URL and quote (B-70). Only Sg. Golok (Rantau Panjang, Kg. Jenob) has cited readings; VEDA holds no Nov
  2024 readings for the Sg. Kelantan towns.
- `synthetic_anchors.csv` - SYNTHETIC scenes (made-up river levels, `scripts/make_synthetic_scenes.py`, seeded).

## Notes: news reports about Kota Bharu, Nov 2024 (context for the B-88 rain rule - not readings, not crossing times)

The B-88 rain rule (rain upstream + here), run hour by hour on the Open-Meteo archive with no hindsight, raised Kota
Bharu at 10:00 on 27 Nov 2024. That night the news reported the river at Kota Bharu overflowing. These are **report
times**, not the times the river crossed Waspada / Bahaya, so **no lead time is claimed**:

| Published (MYT) | Source | What it reports |
|---|---|---|
| 28 Nov 2024 01:10 (dateline Kota Bharu, 27 Nov) | Bernama - https://web11.bernama.com/en/news.php?id=2368507 | Sungai Kelantan at Tambatan D'Raja overflowing (not re-checked: the site did not answer on 24 Oct 2026) |
| 28 Nov 2024 11:08 | RTM - https://berita.rtm.gov.my/?p=128138 | APM Kelantan: "air Sungai Kelantan telah melebihi paras bahaya" |
| 28 Nov 2024 12:51 | Bernama - https://bernama.com/en/news.php?id=2368592 | APM Kelantan: the level "has exceeded the danger point" |

Allowed wording: "In the Nov 2024 replay the rule raised Kota Bharu at 10:00 on 27 Nov; that night the news reported
the river at Kota Bharu overflowing."
