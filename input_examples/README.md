# Input examples (B-20)

Questions judges can send as they are. Each file: `question`, optional `replay` + `at` (Malaysia time), optional `stale_hours` (simulates the controlling gauge having had no reading for that long - test only).

```bash
curl -X POST localhost:8000/run -H "Content-Type: application/json" -d @input_examples/03_normal_day_en.json
python run.py --replay nov2024 --at "2024-11-26 18:00" "Rantau Panjang selamat ke malam ni?"
```

| File | Question | Data | What it shows |
|---|---|---|---|
| `01_rising_river_prepare.json` | Rantau Panjang selamat ke malam ni? | replay nov2024 at 2024-11-26 18:00 | Rising river - Rantau Panjang (Pasir Mas district) on 26 Nov 2024 18:00, replay of the real flood: Golok at Warning, upstream Kg Jenob at Danger |
| `02_rising_river_act.json` | Is Rantau Panjang safe now? | replay nov2024 at 2024-11-27 19:30 | Rising river at its worst - Rantau Panjang on 27 Nov 2024 19:30, 10.94 m, above the Dec 2014 peak |
| `03_normal_day_en.json` | Tumpat ok? | live data (recorded) | Normal day - a simple question in English, calm river (quick path) |
| `04_normal_day_bm.json` | Tumpat selamat ke? | live data (recorded) | Normal day - the same in Bahasa Melayu |
| `05_broken_source.json` | Is Tumpat safe? | gauge 5 h old | Broken source - the controlling gauge has had no reading for 5 hours; the frozen data.gov.my /flood-warning is excluded as always |
| `06_out_of_area.json` | Machang banjir tak? | live data (recorded) | Out of area - a Kelantan district VEDA does not cover yet (reply in BM) |
