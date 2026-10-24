# Wording review - every string a public user can see (EN + BM)

Prepared 24 Oct 2026 for Cowork. **Nothing is changed yet.** Rules applied: BM polite and warm ("Sila", "Mohon", "Elakkan" rather than a bare "Jangan" where the meaning stays just as clear), everyday words, English words kept where Malaysians use them (marked *italic*, e.g. *power bank*, *group*; PPS stays), standard Malaysian Malay (no Indonesian word found), one term per thing; EN plain, calm, no blame. **Safety rule:** an urgent instruction stays just as direct - rows where that decides the wording are marked UNSURE / FLAG.

Columns: id / location · current EN · current BM · issue · proposed EN · proposed BM (empty = keep) · note.
**43 rows have an issue** (8 marked FLAG / UNSURE for Cowork). Only rows with an issue have proposals; every other row is listed so nothing is missed.

## Home (23 strings)

| id / location | current EN | current BM | issue | proposed EN | proposed BM | note |
|---|---|---|---|---|---|---|
| `index.UI.home_title` | Is my area at risk of flooding? | Adakah kawasan saya berisiko banjir? | - |  |  |  |
| `index.UI.or_type` | Or type a question | Atau taip soalan | - |  |  |  |
| `index.UI.ask` | Ask | Tanya | - |  |  |  |
| `index.UI.privacy` | Please don't type names, IC, phone numbers or addresses. Your question is not sent to any AI model; it stays on this computer in VEDA's log files, with phone and IC numbers masked. | Jangan taip nama, IC, nombor telefon atau alamat. Soalan anda tidak dihantar kepada mana-mana model AI; ia kekal di komputer ini dalam fail log VEDA, dengan nombor telefon dan IC disembunyikan. | BM bare 'Jangan' (not urgent) |  | Mohon jangan taip nama, IC, nombor telefon atau alamat. Soalan anda tidak dihantar kepada mana-mana model AI; ia kekal di komputer ini dalam fail log VEDA, dengan nombor telefon dan IC disembunyikan. |  |
| `index.UI.sos` | I'm stranded / in danger | Saya terkandas / dalam bahaya | - |  |  |  |
| `index.UI.data_label` | Data | Data | - |  |  |  |
| `index.UI.privacy_short` | Your question stays private · | Soalan anda kekal peribadi · | - |  |  |  |
| `index.UI.more` | more › | lagi › | - |  |  |  |
| `index.UI.less` | less ‹ | kurang ‹ | - |  |  |  |
| `index.UI.demo_data` | Demo data | Data demo | - |  |  |  |
| `index.UI.footer` | Not an official warning. Follow JPS / APM / police instructions. Emergency 999 · APM 991. | Bukan amaran rasmi. Ikut arahan JPS / APM / polis. Kecemasan 999 · APM 991. | - |  |  |  |
| `index.UI.credits_lead` | River levels: Jabatan Pengairan dan Saliran (JPS) Malaysia, read live on this machine and used for non-commercial public-safety research. Also: | Paras sungai: Jabatan Pengairan dan Saliran (JPS) Malaysia, dibaca secara langsung di komputer ini dan digunakan untuk penyelidikan keselamatan awam bukan komersial. Juga: | - |  |  |  |
| `index.UI.credits_replay` | Past flood replay (Nov 2024): readings as reported by Bernama and Kosmo, citing JPS. Made-up test scenes use invented readings. | Ulang tayang banjir lalu (Nov 2024): bacaan seperti yang dilaporkan oleh Bernama dan Kosmo, memetik JPS. Senario ujian rekaan menggunakan bacaan rekaan. | - |  |  |  |
| `index.UI.bigger` | Bigger text | Teks lebih besar | - |  |  |  |
| `index.UI.live` | Live now | Langsung sekarang | BM literal ('Langsung sekarang') |  | Data semasa |  |
| `index.UI.past` | Past flood | Banjir lalu | - |  |  |  |
| `index.UI.madeup` | Made-up test | Ujian rekaan | - |  |  |  |
| `index.UI.q_default` | Is {town} at risk of flooding right now? | Adakah {town} berisiko banjir sekarang? | - |  |  |  |
| `index.UI.town_hint` | Check now | Semak sekarang | - |  |  |  |
| `index.DATA.synthetic_rising` | rising river | sungai naik | - |  |  |  |
| `index.DATA.synthetic_calm` | calm day | hari tenang | - |  |  |  |
| `index.DATA.synthetic_silent_upstream` | no reading upstream | tiada bacaan di hulu | - |  |  |  |
| `index.DATA.synthetic_upstream_rain` | rain upstream + here | hujan di hulu + di sini | - |  |  |  |

## Waiting (13 strings)

| id / location | current EN | current BM | issue | proposed EN | proposed BM | note |
|---|---|---|---|---|---|---|
| `index.UI.see_doing` | See what VEDA is doing › | Lihat apa yang VEDA sedang buat › | - |  |  |  |
| `index.UI.hide_doing` | Hide what VEDA is doing | Sembunyikan apa yang VEDA sedang buat | - |  |  |  |
| `index.UI.tip_label` | Tip | Petua | - |  |  |  |
| `index.UI.warn_label` | MetMalaysia warning | Amaran MetMalaysia | - |  |  |  |
| `index.UI.s_start` | Starting… | Bermula… | - |  |  |  |
| `index.UI.s_plan` | Understanding your question… | Memahami soalan anda… | - |  |  |  |
| `index.UI.s_gather` | Reading river levels, rain and warnings… | Membaca paras sungai, hujan dan amaran… | - |  |  |  |
| `index.UI.s_forecast` | Working out the risk… | Menilai risiko… | - |  |  |  |
| `index.UI.s_draft` | Writing the answer… | Menulis jawapan… | - |  |  |  |
| `index.UI.s_critique` | Double-checking the answer… | Menyemak semula jawapan… | - |  |  |  |
| `index.UI.s_revise` | Fixing the answer… | Membetulkan jawapan… | - |  |  |  |
| `index.UI.s_done` | Done. | Selesai. | - |  |  |  |
| `index.UI.tips` | ["Keep a charged phone and a power bank ready during the monsoon.", "Never walk or drive through floodwater - 15 cm of fast water can knock you down.", "Put important documents in a plastic bag, ready to take.", "Know where your nearest relief centre (PPS) is - ask the village head."] | ["Sediakan telefon yang dicas dan power bank sepanjang musim tengkujuh.", "Jangan meredah air banjir - air deras setinggi 15 cm boleh menjatuhkan anda.", "Masukkan dokumen penting dalam beg plastik, sedia untuk dibawa.", "Ketahui PPS (pusat pemindahan) terdekat - tanya ketua kampung."] | safety tip keeps 'Jangan' |  |  | UNSURE: tip 2 'Jangan meredah air banjir...' stays direct (danger); tips 1, 3, 4 are fine. |

## Answer screen (incl. Details) (151 strings)

| id / location | current EN | current BM | issue | proposed EN | proposed BM | note |
|---|---|---|---|---|---|---|
| `view.HEADLINE.NORMAL` | Normal for now | Normal buat masa ini | - |  |  |  |
| `view.HEADLINE.WATCH` | Keep watching | Terus berjaga-jaga | - |  |  |  |
| `view.HEADLINE.PREPARE` | Get ready | Bersedia | - |  |  |  |
| `view.HEADLINE.ACT` | Act now | Bertindak sekarang | - |  |  |  |
| `view.HEADLINE.INSUFFICIENT_DATA` | Can't confirm right now | Tidak dapat disahkan sekarang | - |  |  |  |
| `view.W.river_vs` | The river is {d} m {side} the {name} level | Paras sungai {d} m {side} paras {name} | - |  |  |  |
| `view.W.above` | above | di atas | - |  |  |  |
| `view.W.below` | below | di bawah | - |  |  |  |
| `view.W.and` | and {t}. | dan {t}. | - |  |  |  |
| `view.W.trend.rising` | still rising | masih naik | - |  |  |  |
| `view.W.trend.falling` | falling | sedang turun | - |  |  |  |
| `view.W.trend.steady` | steady | stabil | - |  |  |  |
| `view.W.no_reading` | VEDA has no fresh river reading for this place right now. | VEDA tiada bacaan sungai terkini untuk tempat ini sekarang. | - |  |  |  |
| `view.W.no_reading_past` | There is no checked river reading near this time. | Tiada bacaan sungai yang disahkan berhampiran masa ini. | - |  |  |  |
| `view.W.water` | {m} m at {t} | {m} m pada {t} | - |  |  |  |
| `view.W.rate_up` | rising {r} cm an hour | naik {r} cm sejam | - |  |  |  |
| `view.W.rate_down` | falling {r} cm an hour | turun {r} cm sejam | - |  |  |  |
| `view.W.rate_flat` | about the same | lebih kurang sama | - |  |  |  |
| `view.W.change_3h_up` | up {c} cm in 3 hours | naik {c} cm dalam 3 jam | - |  |  |  |
| `view.W.change_3h_down` | down {c} cm in 3 hours | turun {c} cm dalam 3 jam | - |  |  |  |
| `view.W.change_3h_flat` | no change in 3 hours | tiada perubahan dalam 3 jam | - |  |  |  |
| `view.W.tidal` | the sea tide moves this river, so no trend | pasang surut laut menggerakkan sungai ini, jadi tiada trend | inconsistent with the Water row (WP.tidal) | the sea tide moves this river, so no trend is shown | pasang surut laut menggerakkan sungai ini, jadi trend tidak ditunjukkan |  |
| `view.W.vs_level` | {d} m {side} the {name} level ({t} m) | {d} m {side} paras {name} ({t} m) | - |  |  |  |
| `view.W.up_none` | No fresh reading upstream ({where}) - VEDA can't see what may be coming. | Tiada bacaan terkini di hulu ({where}) - VEDA tidak dapat melihat apa yang mungkin sampai. | - |  |  |  |
| `view.W.up_ok` | {where}: normal | {where}: normal | - |  |  |  |
| `view.W.up_high` | {where}: at the {name} level | {where}: pada paras {name} | - |  |  |  |
| `view.W.up_rising` | , rising | , sedang naik | - |  |  |  |
| `view.W.up_window` | ; may reach here in {a}-{b} hours | ; mungkin sampai ke sini dalam {a}-{b} jam | - |  |  |  |
| `view.W.rain_next` | {mm} mm expected in the next 24 hours | {mm} mm dijangka dalam 24 jam akan datang | - |  |  |  |
| `view.W.rain_past` | {mm} mm fell in the 24 hours before this time | {mm} mm turun dalam 24 jam sebelum masa ini | - |  |  |  |
| `view.W.checked2` | Double-checked | Disemak dua kali | - |  |  |  |
| `view.W.checked1` | Checked | Disemak | - |  |  |  |
| `view.W.combined` | combined from {n} sources: {kinds} | digabung daripada {n} sumber: {kinds} | - |  |  |  |
| `view.W.n_left_out` | {n} left out | {n} diketepikan | - |  |  |  |
| `view.W.from_live` | official river gauge | stesen sungai rasmi | - |  |  |  |
| `view.W.from_reported` | reading reported in the news | bacaan yang dilaporkan dalam berita | - |  |  |  |
| `view.W.from_estimated` | estimate between reported readings | anggaran antara bacaan yang dilaporkan | - |  |  |  |
| `view.W.from_made_up` | made-up test reading | bacaan ujian rekaan | - |  |  |  |
| `view.W.calm_note` | Nothing to do now. VEDA checks again whenever you ask. | Tiada apa perlu dibuat sekarang. VEDA menyemak semula setiap kali anda bertanya. | - |  |  |  |
| `view.W.no_river_row` | No fresh river reading right now. | Tiada bacaan sungai terkini sekarang. | - |  |  |  |
| `view.W.cant_confirm` | We could not get a fresh river reading, so we will not guess. Check JPS Infobanjir; call 999 if you are in danger. | Kami tidak dapat bacaan sungai terkini, jadi kami tidak akan meneka. Semak JPS Infobanjir; hubungi 999 jika anda dalam bahaya. | - |  |  |  |
| `view.W.covers` | VEDA covers Rantau Panjang, Pasir Mas, Kota Bharu and Tumpat for now. | Buat masa ini VEDA meliputi Rantau Panjang, Pasir Mas, Kota Bharu dan Tumpat. | - |  |  |  |
| `view.W.nearest` | The nearest is {place}. | Yang paling dekat ialah {place}. | - |  |  |  |
| `view.W.did_you_mean` | Did you mean one of these? | Adakah maksud anda salah satu daripada ini? | - |  |  |  |
| `view.W.down` | VEDA can't answer right now. If you are in danger call 999. | VEDA tidak dapat menjawab sekarang. Jika anda dalam bahaya, hubungi 999. | - |  |  |  |
| `view.W.combined_why` | The river here alone would say “{alone}”; it is {who} that {verb} this to “{now}”. | Sungai di sini sahaja akan menunjukkan “{alone}”; {who} yang menaikkannya kepada “{now}”. | - |  |  |  |
| `view.W.who_upstream` | the river upstream | sungai di hulu | - |  |  |  |
| `view.W.who_rain` | the rain forecast | ramalan hujan | - |  |  |  |
| `view.W.who_rain_up` | the heavy rain upstream | hujan lebat di hulu | - |  |  |  |
| `view.W.who_met` | the official MetMalaysia rain warning | amaran hujan rasmi MetMalaysia | - |  |  |  |
| `view.W.who_rain_both` | the heavy rain upstream arriving while it rains heavily here | hujan lebat di hulu yang sampai ketika hujan lebat di sini | - |  |  |  |
| `view.W.and_word` | and | dan | - |  |  |  |
| `view.W.from_none` | no fresh river reading | tiada bacaan sungai terkini | - |  |  |  |
| `view.W.label_replay` | Past flood replay · {when} | Ulang tayang banjir lalu · {when} | - |  |  |  |
| `view.W.label_synthetic` | Made-up test scene · {when} | Senario ujian rekaan · {when} | - |  |  |  |
| `view.W.used` | used | digunakan | - |  |  |  |
| `view.W.left_out` | left out: {why} | diketepikan: {why} | - |  |  |  |
| `view.W.not_used` | not used: {why} | tidak digunakan: {why} | - |  |  |  |
| `view.WHY.level>=danger` | The river is at or above the danger level. | Paras sungai pada atau melebihi paras Bahaya. | - |  |  |  |
| `view.WHY.level>=warning` | The river is at or above the warning level. | Paras sungai pada atau melebihi paras Amaran. | - |  |  |  |
| `view.WHY.level>=alert` | The river is at or above the alert level. | Paras sungai pada atau melebihi paras Waspada. | - |  |  |  |
| `view.WHY.danger<=12h` | At its current rate the river could reach the danger level in about {h} hours. | Pada kadar sekarang, sungai boleh sampai ke paras Bahaya dalam kira-kira {h} jam. | - |  |  |  |
| `view.WHY.danger<=24h` | At its current rate the river could reach the danger level in about {h} hours. | Pada kadar sekarang, sungai boleh sampai ke paras Bahaya dalam kira-kira {h} jam. | - |  |  |  |
| `view.WHY.alert<=24h` | At its current rate the river could reach the alert level in about {h} hours. | Pada kadar sekarang, sungai boleh sampai ke paras Waspada dalam kira-kira {h} jam. | - |  |  |  |
| `view.WHY.sentinel>=danger` | The river upstream at {where} is at the danger level{window}. | Sungai di hulu ({where}) pada paras Bahaya{window}. | - |  |  |  |
| `view.WHY.sentinel>=alert` | The river upstream at {where} is high{window}. | Sungai di hulu ({where}) tinggi{window}. | - |  |  |  |
| `view.WHY.window` | ; the water may reach here in {a}-{b} hours | ; air mungkin sampai ke sini dalam {a}-{b} jam | - |  |  |  |
| `view.WHY.upstream-rain` | Heavy rain has fallen upstream ({where}, {mm} mm in 3 days); {when}. | Hujan lebat telah turun di hulu ({where}, {mm} mm dalam 3 hari); {when}. | - |  |  |  |
| `view.WHY.upstream-rain-fc` | Heavy rain is forecast upstream ({where}, {mm} mm in 24 hours). | Hujan lebat dijangka di hulu ({where}, {mm} mm dalam 24 jam). | - |  |  |  |
| `view.WHY.when_known` | the water may reach here in {a}-{b} hours | air mungkin sampai ke sini dalam {a}-{b} jam | - |  |  |  |
| `view.WHY.when_unknown` | when it reaches here is not known | bila ia sampai ke sini tidak diketahui | - |  |  |  |
| `view.WHY.upstream+local-rain` | Heavy rain upstream ({where}) may reach here in {a}-{b} hours while it is also raining heavily here ({mm} mm in 12 hours), so VEDA moved up one step. | Hujan lebat di hulu ({where}) mungkin sampai ke sini dalam {a}-{b} jam ketika hujan lebat juga di sini ({mm} mm dalam 12 jam), jadi VEDA naikkan satu tahap. | - |  |  |  |
| `view.WHY.met-warning-no-river` | There is no fresh river reading here, but MetMalaysia has an official {level} rain warning for this district - an official warning is enough to get ready. | Tiada bacaan sungai terkini di sini, tetapi MetMalaysia mengeluarkan amaran hujan rasmi tahap {level} untuk daerah ini - amaran rasmi sudah cukup untuk bersedia. | - |  |  |  |
| `view.WHY.met-warning` | MetMalaysia has an official {level} rain warning for this district; that sets at least “{min}”. | MetMalaysia mengeluarkan amaran hujan rasmi tahap {level} untuk daerah ini; ini menetapkan sekurang-kurangnya “{min}”. | - |  |  |  |
| `view.WHY.rain-heavy` | Heavy rain is forecast: {amounts}. | Hujan lebat dijangka: {amounts}. | - |  |  |  |
| `view.WHY.mm_24` | {mm} mm in 24 hours | {mm} mm dalam 24 jam | - |  |  |  |
| `view.WHY.mm_72` | {mm} mm in 3 days | {mm} mm dalam 3 hari | - |  |  |  |
| `view.WHY.rain-wet-ground` | {n72} mm of rain is forecast in 3 days, on ground already wet from the past week. | {n72} mm hujan dijangka dalam 3 hari, di atas tanah yang sudah basah sejak minggu lepas. | - |  |  |  |
| `view.WHY.rising-fast` | The river is rising fast, so VEDA moved up one step. | Paras sungai naik dengan cepat, jadi VEDA naikkan satu tahap. | - |  |  |  |
| `view.WHY.no-trigger` | The river is below the alert level and nothing else points to a flood. | Paras sungai di bawah paras Waspada dan tiada tanda lain banjir. | BM word order |  | Paras sungai di bawah paras Waspada dan tiada tanda lain akan berlaku banjir. |  |
| `view.WHY.fail-safe` | VEDA has no fresh, checked river reading for this place, so it will not guess. | VEDA tiada bacaan sungai terkini yang disahkan untuk tempat ini, jadi ia tidak meneka. | inconsistent ('will not guess' elsewhere) |  | VEDA tiada bacaan sungai terkini yang disahkan untuk tempat ini, jadi ia tidak akan meneka. |  |
| `view.SOURCE_NAME.open_meteo` | Rain forecast (Open-Meteo) | Ramalan hujan (Open-Meteo) | - |  |  |  |
| `view.SOURCE_NAME.open_meteo_past` | Rain record (Open-Meteo archive) | Rekod hujan (arkib Open-Meteo) | - |  |  |  |
| `view.SOURCE_NAME.mygov_forecast` | MetMalaysia forecast | Ramalan MetMalaysia | - |  |  |  |
| `view.SOURCE_NAME.mygov_warning` | MetMalaysia warnings | Amaran MetMalaysia | - |  |  |  |
| `view.SOURCE_NAME.cross` | Flood warnings (data.gov.my) | Amaran banjir (data.gov.my) | - |  |  |  |
| `view.SOURCE_NAME.osm` | Map data (OpenStreetMap) | Data peta (OpenStreetMap) | - |  |  |  |
| `view.SOURCE_NAME.rain_up` | Rain upstream ({n} rain points, Open-Meteo) | Hujan di hulu ({n} titik hujan, Open-Meteo) | - |  |  |  |
| `view.SOURCE_NAME.river` | River level: {name} | Paras sungai: {name} | - |  |  |  |
| `view.SOURCE_NAME.upstream` | River upstream: {name} | Sungai di hulu: {name} | - |  |  |  |
| `view.LEFT_OUT.no_reading` | no reading | tiada bacaan | - |  |  |  |
| `view.LEFT_OUT.looked_wrong` | the reading looked wrong | bacaan kelihatan salah | - |  |  |  |
| `view.LEFT_OUT.too_old` | reading too old ({age}) | bacaan terlalu lama ({age}) | - |  |  |  |
| `view.LEFT_OUT.past` | not available for this date | tiada untuk tarikh ini | - |  |  |  |
| `view.LEFT_OUT.unreadable` | could not be read | tidak dapat dibaca | - |  |  |  |
| `view.LEFT_OUT.stale` | out of date | sudah lapuk | 'lapuk' sounds like 'rotten/obsolete' |  | sudah lama tidak dikemas kini |  |
| `view.LEFT_OUT.quick` | not needed for a quick check | tidak perlu untuk semakan pantas | - |  |  |  |
| `view.LEFT_OUT.not_needed` | not needed for this question | tidak perlu untuk soalan ini | - |  |  |  |
| `view.KIND.river` | river here | sungai di sini | - |  |  |  |
| `view.KIND.upstream` | river upstream | sungai di hulu | - |  |  |  |
| `view.KIND.rain` | rain | hujan | - |  |  |  |
| `view.KIND.forecast` | forecast | ramalan | - |  |  |  |
| `view.KIND.warnings` | warnings | amaran | - |  |  |  |
| `view.KIND.flood_warnings` | flood warnings | amaran banjir | - |  |  |  |
| `view.KIND.map` | map | peta | - |  |  |  |
| `view.KIND.rain_upstream` | rain upstream | hujan di hulu | - |  |  |  |
| `view.SET_BY.rain_both` | Heavy rain upstream is on its way, and it is raining hard here. | Hujan lebat dari hulu sedang menuju ke sini, dan hujan turun dengan lebat di sini. | - |  |  |  |
| `view.SET_BY.rain_up` | Heavy rain has fallen upstream, and the water may come this way. | Hujan lebat telah turun di hulu, dan airnya mungkin mengalir ke sini. | - |  |  |  |
| `view.SET_BY.upstream_gauge` | The river upstream is high, and the water may be on its way. | Sungai di hulu tinggi, dan airnya mungkin sedang menuju ke sini. | - |  |  |  |
| `view.SET_BY.rain_forecast` | Heavy rain is forecast. | Hujan lebat dijangka. | - |  |  |  |
| `view.SET_BY.met_warning` | MetMalaysia has an official {level} rain warning for this district. | MetMalaysia mengeluarkan amaran hujan rasmi tahap {level} untuk daerah ini. | - |  |  |  |
| `view.SET_BY.met_warning_no_river` | MetMalaysia has an official {level} rain warning for this district. We could not get a river reading, so get ready anyway. | MetMalaysia mengeluarkan amaran hujan rasmi tahap {level} untuk daerah ini. Kami tidak dapat bacaan sungai, jadi bersedialah juga. | BM '-lah' imperative |  | MetMalaysia mengeluarkan amaran hujan rasmi tahap {level} untuk daerah ini. Kami tidak dapat bacaan sungai, jadi sila bersedia juga. | UNSURE: 'sila bersedia' must stay an instruction, not a suggestion - please confirm it reads as clear as 'bersedialah'. |
| `view.WP.rising` | Rising about {r} cm an hour. | Naik kira-kira {r} cm sejam. | - |  |  |  |
| `view.WP.falling` | Falling about {r} cm an hour. | Turun kira-kira {r} cm sejam. | - |  |  |  |
| `view.WP.steady` | Steady. | Stabil. | - |  |  |  |
| `view.WP.tidal` | The sea tide moves this river, so we don't show a trend. | Pasang surut laut menggerakkan sungai ini, jadi kami tidak menunjukkan trend. | - |  |  |  |
| `view.WP.over_danger` | Already {d} m over the danger mark. | Sudah {d} m melebihi paras bahaya. | inconsistent capitals (level names are capitalised elsewhere) |  | Sudah {d} m melebihi paras Bahaya. |  |
| `view.WP.over_alert` | Over the alert mark, {d} m under the danger mark. | Melebihi paras waspada, {d} m di bawah paras bahaya. | inconsistent capitals |  | Melebihi paras Waspada, {d} m di bawah paras Bahaya. |  |
| `view.WP.under_alert` | {d} m under the alert mark. | {d} m di bawah paras waspada. | inconsistent capitals |  | {d} m di bawah paras Waspada. |  |
| `view.WP.calm` | Calm, below the alert mark. | Tenang, di bawah paras waspada. | inconsistent capitals |  | Tenang, di bawah paras Waspada. |  |
| `view.MET_LEVEL_WORD.waspada` | alert-level | Waspada | - |  |  |  |
| `view.MET_LEVEL_WORD.buruk` | severe-level | Buruk | - |  |  |  |
| `view.MET_LEVEL_WORD.bahaya` | danger-level | Bahaya | - |  |  |  |
| `index.UI.water_detail` | Water in detail | Air secara terperinci | BM stiff |  | Butiran paras air |  |
| `index.UI.todo` | What to do now | Apa perlu dibuat sekarang | - |  |  |  |
| `index.UI.water` | Water | Air | - |  |  |  |
| `index.UI.upstream` | Upstream | Hulu | - |  |  |  |
| `index.UI.rain` | Rain | Hujan | - |  |  |  |
| `index.UI.share` | Share with family | Kongsi dengan keluarga | - |  |  |  |
| `index.UI.listen` | Listen | Dengar | - |  |  |  |
| `index.UI.stop` | Stop | Berhenti | - |  |  |  |
| `index.UI.details` | Details › | Butiran › | - |  |  |  |
| `index.UI.hide_details` | Hide details | Sembunyikan butiran | - |  |  |  |
| `index.UI.why` | Why | Kenapa | - |  |  |  |
| `index.UI.explained` | In plain words | Dalam bahasa mudah | - |  |  |  |
| `index.UI.expl_note` | Written by AI (Nemotron) from the checked facts, then checked again. | Ditulis oleh AI (Nemotron) daripada fakta yang telah disemak, kemudian disemak semula. | - |  |  |  |
| `index.UI.sources` | Where this comes from | Dari mana maklumat ini | - |  |  |  |
| `index.UI.again` | Ask another question | Tanya soalan lain | - |  |  |  |
| `index.UI.disclaimer` | Not an official warning. Follow JPS / APM / police instructions. Emergency 999 · APM 991. | Bukan amaran rasmi. Ikut arahan JPS / APM / polis. Kecemasan 999 · APM 991. | - |  |  |  |
| `index.UI.share_title` | Share with family | Kongsi dengan keluarga | - |  |  |  |
| `index.UI.send_wa` | Send on WhatsApp | Hantar melalui WhatsApp | - |  |  |  |
| `index.UI.copy` | Copy text | Salin teks | - |  |  |  |
| `index.UI.copied` | Copied. | Disalin. | - |  |  |  |
| `index.UI.share_note` | Only the answer is shared - never your question. | Hanya jawapan dikongsi - soalan anda tidak dikongsi. | - |  |  |  |
| `index.UI.back` | Back | Kembali | - |  |  |  |
| `index.UI.no_rain` | No rain figure for this time. | Tiada angka hujan untuk masa ini. | - |  |  |  |
| `index.UI.level_now` | Now | Kini | - |  |  |  |
| `index.UI.alert` | Alert | Waspada | - |  |  |  |
| `index.UI.warning` | Warning | Amaran | - |  |  |  |
| `index.UI.danger` | Danger | Bahaya | - |  |  |  |
| `index.UI.m` | m | m | - |  |  |  |

## Card / WhatsApp share text (113 strings)

| id / location | current EN | current BM | issue | proposed EN | proposed BM | note |
|---|---|---|---|---|---|---|
| `card.ADVICE.NORMAL` | No action needed. Keep an eye on JPS updates. | Tiada tindakan diperlukan. Terus pantau maklumat terkini JPS. | - |  |  |  |
| `card.ADVICE.WATCH` | Check again in 3 hours. Get important documents, medicines and a charged phone / power bank ready. | Semak semula dalam 3 jam. Sediakan dokumen penting, ubat-ubatan dan telefon yang dicas / power bank. | English word not marked |  | Semak semula dalam 3 jam. Sediakan dokumen penting, ubat-ubatan dan telefon yang dicas / *power bank*. |  |
| `card.ADVICE.PREPARE` | Pack an emergency bag. Move valuables and your vehicle to higher ground. Find your nearest PPS (ask the village head / JKKK). Check on elderly or sick neighbours. | Sediakan beg kecemasan. Alihkan barang berharga dan kenderaan ke tempat tinggi. Kenal pasti PPS terdekat (tanya ketua kampung / JKKK). Bantu jiran warga emas atau yang sakit. | - |  |  |  |
| `card.ADVICE.ACT` | Follow APM / police instructions and go to the PPS if told. Switch off the main power. Never walk or drive through floodwater. If trapped: stay on high ground, save phone battery, call 999 / 991. | Ikut arahan APM / polis dan pergi ke PPS jika diarahkan. Matikan suis utama elektrik. Jangan meredah air banjir, sama ada berjalan kaki atau memandu. Jika terkandas: kekal di tempat tinggi, jimatkan bateri telefon, hubungi 999 / 991. | safety - keep direct |  |  | UNSURE: 'Jangan meredah air banjir' stays a bare 'Jangan' on purpose (danger instruction, safety rule). Please confirm. |
| `card.ADVICE.INSUFFICIENT_DATA` | VEDA cannot confirm the river level right now. Check JPS Infobanjir; call 999 if you are in danger. | VEDA tidak dapat mengesahkan paras sungai sekarang. Semak JPS Infobanjir; hubungi 999 jika anda dalam bahaya. | - |  |  |  |
| `card.T.action` | WHAT TO DO NOW | APA PERLU DIBUAT SEKARANG | - |  |  |  |
| `card.T.level` | JPS level | paras JPS | - |  |  |  |
| `card.T.river` | River | Sungai | - |  |  |  |
| `card.T.at` | at | pada | - |  |  |  |
| `card.T.above` | above | di atas | - |  |  |  |
| `card.T.below` | below | di bawah | - |  |  |  |
| `card.T.alert` | Alert | Waspada | - |  |  |  |
| `card.T.danger` | Danger | Bahaya | - |  |  |  |
| `card.T.peak` | the {event} peak | puncak {event} | - |  |  |  |
| `card.T.next24` | Next 24 h | 24 jam akan datang | - |  |  |  |
| `card.T.rain` | Rain next 24 h: {mm} mm (Open-Meteo) | Hujan 24 jam akan datang: {mm} mm (Open-Meteo) | - |  |  |  |
| `card.T.rain_past` | Rain past 24 h: {mm} mm (Open-Meteo archive, {date}); no rain forecast in a replay | Hujan 24 jam lepas: {mm} mm (arkib Open-Meteo, {date}); tiada ramalan hujan dalam ulang tayang | jargon ('replay') | Rain past 24 h: {mm} mm (Open-Meteo archive, {date}); a past day has no rain forecast | Hujan 24 jam lepas: {mm} mm (arkib Open-Meteo, {date}); tiada ramalan hujan untuk hari lepas |  |
| `card.T.synthetic_tag` | (SYNTHETIC) | (SYNTHETIC) | inconsistent with the page ('made-up test') | (made-up) | (rekaan) | FLAG - data honesty: SYNTHETIC is the B-75 label used everywhere. Keep unless Cowork agrees the page wording is enough. |
| `card.T.synthetic_src` | SYNTHETIC river levels (not JPS) | paras sungai SYNTHETIC (bukan JPS) | inconsistent with the page | made-up test river levels (not JPS) | paras sungai ujian rekaan (bukan JPS) | FLAG - data honesty (same as above). |
| `card.T.vs2014` | Compared with 2014: {d} m {rel} the Dec 2014 peak here ({p} m) | Berbanding 2014: {d} m {rel} puncak Dis 2014 di sini ({p} m) | - |  |  |  |
| `card.T.archive` | Open-Meteo archive (real rain up to the replay time) | arkib Open-Meteo (hujan sebenar sehingga masa ulang tayang) | - |  |  |  |
| `card.T.archive_short` | Open-Meteo archive | arkib Open-Meteo | - |  |  |  |
| `card.T.trend` | straight-line trend | unjuran garis lurus | jargon | if it keeps changing at this rate | jika terus berubah pada kadar ini |  |
| `card.T.falling` | falling - no level projected | turun - tiada unjuran paras | jargon | falling | sedang turun |  |
| `card.T.pass_danger` | expected to pass Danger | dijangka melepasi paras Bahaya | - |  |  |  |
| `card.T.stranded` | You said you're stranded: safety first | Anda terkandas: utamakan keselamatan | BM reads as a statement ('You are stranded') |  | Anda kata anda terkandas: utamakan keselamatan dahulu |  |
| `card.T.stranded_normal` | River level is normal, but local flooding can still trap you | Paras sungai normal, tetapi banjir setempat masih boleh memerangkap anda | - |  |  |  |
| `card.T.above_trend.rising` | still rising | masih naik | - |  |  |  |
| `card.T.above_trend.falling` | falling | turun | - |  |  |  |
| `card.T.above_trend.steady` | steady | stabil | - |  |  |  |
| `card.T.higher_2014` | higher than 2014 | melebihi paras 2014 | - |  |  |  |
| `card.T.tidal` | trend not projected (tide-influenced gauge) | trend tidak diunjurkan (stesen dipengaruhi pasang surut) | jargon; inconsistent with the page | the sea tide moves this river, so no trend is shown | pasang surut laut menggerakkan sungai ini, jadi trend tidak ditunjukkan |  |
| `card.T.confidence` | Confidence | Keyakinan | - |  |  |  |
| `card.T.conf_label.high` | high | tinggi | - |  |  |  |
| `card.T.conf_label.medium` | medium | sederhana | - |  |  |  |
| `card.T.conf_label.low` | low | rendah | - |  |  |  |
| `card.T.upstream` | Upstream | Hulu | - |  |  |  |
| `card.T.rain_up` | Heavy rain upstream: {items} | Hujan lebat di hulu: {items} | - |  |  |  |
| `card.T.rain_up_item` | {name} {mm72} mm in 3 days ({mm24} mm in 24 h) | {name} {mm72} mm dalam 3 hari ({mm24} mm dalam 24 jam) | - |  |  |  |
| `card.T.rain_up_fc_item` | {name} {mm} mm forecast in 24 h | {name} {mm} mm dijangka dalam 24 jam | - |  |  |  |
| `card.T.arrival_unknown` | arrival time not known | masa sampai tidak diketahui | - |  |  |  |
| `card.T.rain_here` | Heavy rain here: {mm} mm in 12 h | Hujan lebat di sini: {mm} mm dalam 12 jam | - |  |  |  |
| `card.T.small_rivers` | Small rivers and drains can rise fast in heavy rain - keep away from them | Sungai kecil dan longkang boleh naik dengan cepat ketika hujan lebat - jauhi kawasan itu | BM bare imperative (not urgent) |  | Sungai kecil dan longkang boleh naik dengan cepat ketika hujan lebat - sila jauhi kawasan itu |  |
| `card.T.thailand` | Rain upstream in Thailand is not checked yet | Hujan di hulu di Thailand belum disemak | - |  |  |  |
| `card.T.thai_rain` | Rain upstream in Thailand: {items} (arrival time not known) | Hujan di hulu di Thailand: {items} (masa sampai tidak diketahui) | - |  |  |  |
| `card.T.thai_item` | {name} {mm} mm in 3 days | {name} {mm} mm dalam 3 hari | - |  |  |  |
| `card.T.tide` | High tide can keep water in town longer | Air pasang boleh membuat air bertakung lebih lama di bandar | BM a little stiff |  | Air pasang boleh menyebabkan air banjir lambat surut di bandar |  |
| `card.T.thunder` | Thunderstorm warning: small streams and drains can rise within an hour or two | Amaran ribut petir: anak sungai dan longkang boleh naik dalam masa satu atau dua jam | - |  |  |  |
| `card.T.until` | Rain likely until about {t}, then easing | Hujan dijangka hingga kira-kira {t}, kemudian reda | - |  |  |  |
| `card.T.until_heavy` | Heavy rain likely until about {t}, then easing | Hujan lebat dijangka hingga kira-kira {t}, kemudian reda | - |  |  |  |
| `card.T.may_reach` | may reach here in {a}-{b} h | mungkin sampai ke sini dalam {a}-{b} jam | - |  |  |  |
| `card.T.rising` | rising | sedang naik | - |  |  |  |
| `card.T.warning` | MetMalaysia warning | Amaran MetMalaysia | - |  |  |  |
| `card.T.sources` | Sources | Sumber | - |  |  |  |
| `card.T.min_ago` | {n} min ago | {n} minit lalu | - |  |  |  |
| `card.T.h_ago` | {n} h ago | {n} jam lalu | - |  |  |  |
| `card.T.age_unknown` | update time unknown | masa kemas kini tidak diketahui | - |  |  |  |
| `card.T.met_today` | MetMalaysia forecast for today | ramalan MetMalaysia hari ini | - |  |  |  |
| `card.T.excluded` | Excluded: data.gov.my flood-warning (stale, last update {when}) | Diketepikan: data.gov.my flood-warning (lapuk, kemas kini terakhir {when}) | jargon ('stale') | Left out: data.gov.my flood warnings (out of date, last update {when}) | Diketepikan: amaran banjir data.gov.my (sudah lama tidak dikemas kini, kali terakhir {when}) |  |
| `card.T.not_checked` | Not checked: data.gov.my flood-warning (could not be read) | Tidak disemak: data.gov.my flood-warning (tidak dapat dibaca) | mixed English name in BM | Not checked: data.gov.my flood warnings (could not be read) | Tidak disemak: amaran banjir data.gov.my (tidak dapat dibaca) |  |
| `card.T.met_not_checked` | Not checked: MetMalaysia {what} (data.gov.my could not be read) | Tidak disemak: {what} MetMalaysia (data.gov.my tidak dapat dibaca) | - |  |  |  |
| `card.T.met_what.mygov_warning` | warnings | amaran | - |  |  |  |
| `card.T.met_what.mygov_forecast` | forecast | ramalan | - |  |  |  |
| `card.T.met_what.mygov_forecast+mygov_warning` | warnings and forecast | amaran dan ramalan | - |  |  |  |
| `card.T.excluded_short` | Excluded: data.gov.my flood-warning (stale) | Diketepikan: data.gov.my flood-warning (lapuk) | jargon ('stale') | Left out: data.gov.my flood warnings (out of date) | Diketepikan: amaran banjir data.gov.my (sudah lama tidak dikemas kini) |  |
| `card.T.conflict` | Sources disagree on {q}; VEDA did not pick one | Sumber tidak sepakat tentang {q}; VEDA tidak memilih | - |  |  |  |
| `card.T.no_reading` | no fresh reading from the controlling gauge | tiada bacaan terkini dari stesen utama | jargon ('controlling gauge') | no fresh reading from this place's main river gauge | tiada bacaan terkini dari stesen sungai utama tempat ini |  |
| `card.T.backup` | Note: {primary} {silent} - using the backup gauge {backup} | Nota: {primary} {silent} - menggunakan stesen ganti {backup} | - |  |  |  |
| `card.T.silent` | has no reading since {t} | tiada bacaan sejak {t} | - |  |  |  |
| `card.T.silent_never` | has no reading | tiada bacaan | - |  |  |  |
| `card.T.last` | Last reading: {m} m at {t} ({age}) - too old to use | Bacaan terakhir: {m} m pada {t} ({age}) - terlalu lama untuk digunakan | - |  |  |  |
| `card.T.replay_gap` | This replay has no verified JPS reading near this time | Ulang tayang ini tiada bacaan JPS yang disahkan berhampiran masa ini | - |  |  |  |
| `card.T.synthetic_gap` | This SYNTHETIC scene has no reading near this time | Senario SYNTHETIC ini tiada bacaan berhampiran masa ini | - |  |  |  |
| `card.T.synthetic_last` | Last SYNTHETIC reading: {m} m at {t} ({age}) - too far from this time to use | Bacaan SYNTHETIC terakhir: {m} m pada {t} ({age}) - terlalu jauh dari masa ini untuk digunakan | - |  |  |  |
| `card.T.replay_last` | Last verified reading: {m} m at {t} ({age}) - too far from this time to use | Bacaan disahkan terakhir: {m} m pada {t} ({age}) - terlalu jauh dari masa ini untuk digunakan | - |  |  |  |
| `card.T.discovered` | Discovered gauge {name} (approved by {by}; context only, not used for the verdict): {level} | Stesen ditemui {name} (diluluskan oleh {by}; konteks sahaja, tidak digunakan untuk keputusan): {level} | jargon ('verdict') | Gauge found by VEDA: {name} (approved by {by}; for information only - it does not change the result): {level} | Stesen yang ditemui VEDA: {name} (diluluskan oleh {by}; untuk makluman sahaja - tidak mengubah keputusan): {level} |  |
| `card.T.missing` | Missing: no fresh reading from {gauges}; VEDA looked for another upstream gauge on the same river and found none | Tiada bacaan terkini dari {gauges}; VEDA mencari stesen hulu lain di sungai yang sama, tiada ditemui | - |  |  |  |
| `card.T.pps` | Possible PPS — not an official list, confirm with APM / the village head: {items} | Kemungkinan PPS — bukan senarai rasmi, sahkan dengan APM / ketua kampung: {items} | - |  |  |  |
| `card.T.pps_none` | Possible PPS: none named in OpenStreetMap within 10 km — ask APM / the village head | Kemungkinan PPS: tiada yang bernama dalam OpenStreetMap dalam 10 km — tanya APM / ketua kampung | - |  |  |  |
| `card.T.bridge` | {name} crosses {river} ({km} km); river level there: {level} | {name} merentasi {river} ({km} km); paras sungai di situ: {level} | - |  |  |  |
| `card.T.bridge_on` | Bridge on {road} | Jambatan di {road} | - |  |  |  |
| `card.T.bridge_none` | Bridges: none over a named river in OpenStreetMap within 10 km | Jambatan: tiada yang merentasi sungai bernama dalam OpenStreetMap dalam 10 km | - |  |  |  |
| `card.T.no_level` | no recent reading | tiada bacaan terkini | - |  |  |  |
| `card.T.no_gauge` | no JPS gauge nearby on this river | tiada stesen JPS berdekatan di sungai ini | - |  |  |  |
| `card.T.low_ground` | Low ground not assessed | Kawasan rendah tidak dinilai | unclear | VEDA does not know yet which areas are low-lying | VEDA belum mengetahui kawasan mana yang rendah |  |
| `card.T.osm_failed` | Not checked: OpenStreetMap (could not be read) | Tidak disemak: OpenStreetMap (tidak dapat dibaca) | - |  |  |  |
| `card.T.osm_src` | © OpenStreetMap contributors (ODbL) | © OpenStreetMap contributors (ODbL) | - |  |  |  |
| `card.T.low_conf` | Low confidence: VEDA's reviewer did not approve the written explanation, so only the checked data is shown. | Keyakinan rendah: penyemak VEDA tidak meluluskan penjelasan bertulis, jadi hanya data yang telah disemak dipaparkan. | - |  |  |  |
| `card.BAND.below_normal` | Normal | Normal | - |  |  |  |
| `card.BAND.normal` | Normal | Normal | - |  |  |  |
| `card.BAND.alert` | Alert | Waspada | - |  |  |  |
| `card.BAND.warning` | Warning | Amaran | - |  |  |  |
| `card.BAND.danger` | Danger | Bahaya | - |  |  |  |
| `card.VERDICT_LABEL.NORMAL` | NORMAL | NORMAL | - |  |  |  |
| `card.VERDICT_LABEL.WATCH` | WATCH | BERJAGA-JAGA | - |  |  |  |
| `card.VERDICT_LABEL.PREPARE` | PREPARE | BERSEDIA | - |  |  |  |
| `card.VERDICT_LABEL.ACT` | ACT | BERTINDAK | - |  |  |  |
| `card.VERDICT_LABEL.INSUFFICIENT_DATA` | INSUFFICIENT DATA | DATA TIDAK MENCUKUPI | inconsistent with the page headline ('Can't confirm right now') |  |  | FLAG - verdict words are review-pack G3 (Dr Ariff); not proposed here. |
| `card.WORDS.level_vs` | {d} m {side} the {name} level ({t} m) | {d} m {side} paras {name} ({t} m) | - |  |  |  |
| `card.WORDS.trend.rising` | rising | naik | - |  |  |  |
| `card.WORDS.trend.falling` | falling | turun | - |  |  |  |
| `card.WORDS.trend.steady` | steady | stabil | - |  |  |  |
| `card.WORDS.vs2014` | {d} m {side} the Dec 2014 peak ({p} m) | {d} m {side} puncak Dis 2014 ({p} m) | - |  |  |  |
| `card.WORDS.excluded` | data.gov.my flood-warning (stale, excluded) | data.gov.my flood-warning (lapuk, diketepikan) | jargon ('stale') | data.gov.my flood warnings (out of date, left out) | amaran banjir data.gov.my (sudah lama tidak dikemas kini, diketepikan) |  |
| `card.WORDS.no_verified` | no verified reading near this time | tiada bacaan yang disahkan berhampiran masa ini | - |  |  |  |
| `card.WORDS.last` | {m} m at {t}, too old to use | {m} m pada {t}, terlalu lama untuk digunakan | - |  |  |  |
| `coordinator.SAFETY` | Not an official warning. Follow JPS / APM / police instructions. Emergency: 999, APM (Civil Defence): 991. | Bukan amaran rasmi. Ikut arahan JPS / APM / polis. Kecemasan: 999, APM: 991. | - |  |  |  |
| `card.LABEL_BM` | SYNTHETIC reading - made up for the offline demo, not a real JPS reading | bacaan SYNTHETIC - direka untuk demo luar talian, bukan bacaan JPS sebenar | - |  |  |  |
| `card.LABEL_BM` | estimated: reconstructed between the verified JPS readings | anggaran: dibina semula antara bacaan JPS yang disahkan | - |  |  |  |
| `card.LABEL_BM` | reported JPS reading ( | bacaan JPS dilaporkan ( | - |  |  |  |
| `card.LABEL_BM` | ; time approximate | ; masa anggaran | - |  |  |  |
| `card.LABEL_BM` | and | dan | - |  |  |  |
| `card.unavailable_reply` | VEDA cannot reach its river data right now, so it cannot check any place. VEDA cannot confirm the river level right now. Check JPS Infobanjir; call 999 if you are in danger. | VEDA tidak dapat mencapai data sungainya sekarang, jadi tidak dapat menyemak mana-mana tempat. VEDA tidak dapat mengesahkan paras sungai sekarang. Semak JPS Infobanjir; hubungi 999 jika anda dalam bahaya. | repeats itself (two 'cannot' sentences) | VEDA cannot reach its river data right now, so it cannot check any place. Check JPS Infobanjir; call 999 if you are in danger. | VEDA tidak dapat mencapai data sungai sekarang, jadi tidak dapat menyemak mana-mana tempat. Semak JPS Infobanjir; hubungi 999 jika anda dalam bahaya. |  |

## Emergency (5 strings)

| id / location | current EN | current BM | issue | proposed EN | proposed BM | note |
|---|---|---|---|---|---|---|
| `view.EMERGENCY.title` | If you are stranded or in danger | Jika anda terkandas atau dalam bahaya | - |  |  |  |
| `index.UI.sos_title` | If you are stranded or in danger | Jika anda terkandas atau dalam bahaya | - |  |  |  |
| `index.UI.call999` | Call 999 | Hubungi 999 | - |  |  |  |
| `index.UI.call991` | Call APM 991 | Hubungi APM 991 | - |  |  |  |
| `emergency.steps (= card.ADVICE.ACT, one step per sentence)` | see card.ADVICE.ACT | lihat card.ADVICE.ACT | - |  |  |  |

## How VEDA worked this out (18 strings)

| id / location | current EN | current BM | issue | proposed EN | proposed BM | note |
|---|---|---|---|---|---|---|
| `view.STEP_NAME.plan` | Understand the question | Memahami soalan | - |  |  |  |
| `view.STEP_NAME.gather` | Gather the data | Mengumpul data | - |  |  |  |
| `view.STEP_NAME.forecast` | Work out the risk | Menilai risiko | - |  |  |  |
| `view.STEP_NAME.draft` | Write the answer | Menulis jawapan | - |  |  |  |
| `view.STEP_NAME.critique` | Double-check the answer | Menyemak semula jawapan | - |  |  |  |
| `view.STEP_NAME.revise` | Fix the answer | Membetulkan jawapan | - |  |  |  |
| `view.STEP_NAME.safety` | Safety check | Semakan keselamatan | - |  |  |  |
| `index.UI.how_link` | See how VEDA worked this out › | Lihat bagaimana VEDA mendapat jawapan ini › | - |  |  |  |
| `index.UI.how_title` | How VEDA worked this out | Bagaimana VEDA mendapat jawapan ini | - |  |  |  |
| `index.UI.how_note` | Each line is copied from VEDA's step-by-step log. Your question is not shown. | Setiap baris disalin daripada log langkah demi langkah VEDA (dalam bahasa Inggeris). Soalan anda tidak ditunjukkan. | - |  |  |  |
| `index.UI.how_live` | Replay these steps live › | Main semula langkah-langkah ini › | - |  |  |  |
| `index.UI.total` | Total {s} s | Jumlah {s} s | - |  |  |  |
| `index.UI.queries` | {n} data queries through Zetaris | {n} pertanyaan data melalui Zetaris | jargon for the public ('Zetaris') |  |  | UNSURE: kept - this screen is for the curious and names the sponsor technology on purpose. |
| `index.UI.answered` | Answered by {m} | Dijawab oleh {m} | - |  |  |  |
| `index.UI.receipt` | receipt | resit | - |  |  |  |
| `index.UI.code_only` | Code only - no AI in this step | Kod sahaja - tiada AI dalam langkah ini | - |  |  |  |
| `index.UI.ai_failed` | AI step not used | Langkah AI tidak digunakan | - |  |  |  |
| `index.UI.fallbacks` | AI fallbacks in this run | Sandaran AI dalam larian ini | jargon ('fallbacks', 'larian') | AI steps replaced by code in this run | Langkah AI yang diganti dengan kod |  |

## Notices and errors (12 strings)

| id / location | current EN | current BM | issue | proposed EN | proposed BM | note |
|---|---|---|---|---|---|---|
| `config.no_recorded_data` | No recorded data for this time in this scene; available times: … | Tiada data yang direkodkan untuk masa ini dalam senario ini; masa yang ada: … | - |  |  |  |
| `index.UI.check_town` | Check {town} | Semak {town} | - |  |  |  |
| `index.UI.busy` | VEDA is answering another question - try again in a minute. | VEDA sedang menjawab soalan lain - cuba lagi sebentar lagi. | BM 'lagi ... lagi' |  | VEDA sedang menjawab soalan lain - sila cuba semula sebentar lagi. |  |
| `card.place_reply.did_you_mean` | Did you mean {names}? | Adakah maksud anda {names}? | - |  |  |  |
| `card.place_reply.kelantan` | Please name a town or district in Kelantan. Covered places: {covered}. | Sila nyatakan bandar atau daerah di Kelantan. Tempat yang diliputi: {covered}. | - |  |  |  |
| `card.place_reply.known_near` | {known} is in Kelantan but not covered by VEDA yet. Nearest covered place: {near} (about {km} km away). Covered places: {covered}. | {known} di Kelantan tetapi belum diliputi VEDA. Tempat terdekat yang diliputi: {near} (kira-kira {km} km). Tempat yang diliputi: {covered}. | BM missing verb |  | {known} terletak di Kelantan tetapi belum diliputi VEDA. Tempat terdekat yang diliputi: {near} (kira-kira {km} km). Tempat yang diliputi: {covered}. |  |
| `card.place_reply.known` | {known} is in Kelantan but not covered by VEDA yet. Covered places: {covered}. | {known} di Kelantan tetapi belum diliputi VEDA. Tempat yang diliputi: {covered}. | BM missing verb |  | {known} terletak di Kelantan tetapi belum diliputi VEDA. Tempat yang diliputi: {covered}. |  |
| `card.place_reply.unknown` | That place is not covered by VEDA yet. Covered places: {covered}. | Tempat itu belum diliputi VEDA. Tempat yang diliputi: {covered}. | - |  |  |  |
| `index.UI_DOWN` | VEDA can't answer right now. If you are in danger call 999. | VEDA tidak dapat menjawab sekarang. Jika anda dalam bahaya, hubungi 999. | - |  |  |  |
| `main.empty_question` | Ask a question about a place in Kelantan. | (EN only) | not bilingual (shown on the BM page) |  | Sila tanya tentang satu tempat di Kelantan. |  |
| `main.question_too_long` | Keep the question under 500 characters. | (EN only) | not bilingual | Please keep the question under 500 characters. | Sila pastikan soalan kurang daripada 500 aksara. |  |
| `main.busy` | VEDA is answering another question - try again in a minute. | (EN only from the API; the page shows UI.busy) | - |  |  |  |

## Live log (public header) (7 strings)

| id / location | current EN | current BM | issue | proposed EN | proposed BM | note |
|---|---|---|---|---|---|---|
| `live.header` | The question itself is never shown here. | (EN only) | no BM (public page) |  | Soalan itu sendiri tidak pernah ditunjukkan di sini. | UNSURE: the live log is a judge screen in English; add BM only if Cowork wants it bilingual. |
| `live.waiting` | Waiting for a question… Ask one on the main page (/) and every step appears here as it happens. | (EN only) | no BM; '(/)' is technical | Waiting for a question… Ask one on VEDA's main page and every step appears here as it happens. |  |  |
| `live.lost` | Connection lost - reconnecting… | (EN only) | - |  |  |  |
| `live.who` | Who is working | (EN only) | - |  |  |  |
| `live.note` | Word for word from the trace (logs/trace-<run_id>.jsonl). | (EN only) | - |  |  |  |
| `live.recorded` | Replay a recorded run… | (EN only) | - |  |  |  |
| `live.wait_bubble` | Waiting for {model}… ({agent}) | (EN only) | - |  |  |  |

## Session B's files (read-only - listed, not reviewed for change here)

| id / location | current EN | current BM | issue | proposed EN | proposed BM | note |
|---|---|---|---|---|---|---|
| `demo/nginx.conf` banner | Public demo: past flood replay and made-up test scenes only. Not live data. Not an official warning. · Give feedback | Demo awam: ulang tayang banjir lalu dan senario ujian rekaan sahaja. Bukan data masa nyata. Bukan amaran rasmi. · Beri maklum balas | - | | | consistent with the page |
| `demo/feedback/feedback.py` intro | Eight short questions about VEDA's demo. Everything is optional. Please don't write your phone number, email or address. | Lapan soalan ringkas tentang demo VEDA. Semuanya pilihan. Jangan tulis nombor telefon, e-mel atau alamat anda. | BM bare 'Jangan' (not urgent) | | Mohon jangan tulis nombor telefon, e-mel atau alamat anda. | Session B's file - for Session B to apply |
| `demo/feedback/feedback.py` q4 | Would you share this with your family group? | Adakah anda akan kongsi ini dalam *group* keluarga? | - | | | good: *group* kept and italic |
| `demo/feedback/feedback.py` other strings | (title, q1-q8, thanks, errors, privacy) | (BM equal) | - | | | read: polite, everyday words, no issue found |

