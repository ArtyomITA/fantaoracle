# -*- coding: utf-8 -*-
"""Assembla INVENTORY.md finale: intestazione + inventario file + test overlap
nomi + analisi buchi vs fabbisogno. Le sezioni 1 e 2 sono prodotte da
inventory_raw.py e overlap_nomi.py."""
import datetime
import os

RAW = r"data\raw"

HEADER = f"""# INVENTORY — censimento dati grezzi FantaBot

Generato il {datetime.date.today().isoformat()} da `scripts/inventory_raw.py`,
`scripts/overlap_nomi.py`, `scripts/inventory_build_md.py`.

Radici censite:
- `data\\raw` (gruppoesperti, quotazioni, transfermarkt, understat, voti, wayback_prices)
- `E:\\claudecode pesante\\fonti_prezzi` (file preesistenti congelati)

## Quadro d'insieme

| Sorgente | Contenuto | Copertura stagioni | Righe |
|---|---|---|---|
| gruppoesperti | 245 aste reali (55.678 righe giocatore-asta) in `aste_reali_tidy.csv` + 11 xlsx sorgente | 2021/22, 2023/24, 2024/25 | 55.678 |
| wayback_prices | 9 CSV prezzi fantacalcio-online.com da Wayback | 2018/19→2022/23, 2024/25, 2025/26 | ~5.900 |
| quotazioni | 153 CSV fanta.soccer per-giornata + 6 CSV fantacalcio.it (Qt.I/Qt.A/FVM) + mappa date | 2020/21→2025/26 | ~96.500 |
| voti | 5 CSV voti+fantavoti+bonus per giornata (190/190 giornate) | 2021/22→2025/26 | 59.306 |
| understat | 7 CSV giocatori (xG/xA) + 7 CSV squadre | 2019/20→2025/26 | 4.126 + 140 |
| transfermarkt | anagrafica, valutazioni, trasferimenti, presenze IT1 | 2004→2026 (presenze 2019/20→2025/26) | ~180.700 |
| fonti_prezzi (preesistente) | 4 CSV prezzi fantacalcio-online (sep `;`) + 2 xlsx GE originali | 2023/24, 2024/25, 2025/26 | ~2.600 |

Totale censito: **196 CSV (404.945 righe dati) + 13 XLSX** (piu' 152 .xls legacy fanta.soccer identici ai CSV).

---

# 1. Inventario file per file
"""

GAPS = """
---

# 3. Buchi rispetto al fabbisogno del progetto

Fabbisogno dichiarato: prezzi 2023/24+2024/25+2025/26; voti 2021/22–2025/26;
quotazioni snapshot settembre 2024 e 2025; xG; valori di mercato.

## 3.1 Fabbisogno coperto (nessuna azione)

| Requisito | Stato | Dove |
|---|---|---|
| Prezzi 2023/24 | OK | `fonti_prezzi/wayback_20240519_stagione2023-24.csv` (733 righe, 612 con prezzo). In `wayback_prices/` NON emesso (lo snapshot trovato aveva meno copertura). |
| Prezzi 2024/25 | OK | `wayback_prices/prezzi_2024-25_20250214053906.csv` (541 con prezzo) + secondario giu-2025 (497) + preesistente ott-2024 (519) |
| Prezzi 2025/26 | OK | `wayback_prices/prezzi_2025-26_20260411054907.csv` (480 con prezzo) + congelata dic-2025 (474) + live ago-2026 (397) |
| Voti 2021/22–2025/26 | OK | `voti/voti_*.csv`: 190/190 giornate, 59.306 righe, zero buchi squadra-giornata |
| Quotazioni snapshot settembre 2024 | OK | fanta.soccer `fantasoccer_2024-25_g03.csv` (30/08/2024) e `_g04.csv` (14/09/2024); in piu' Qt.I in `fantacalcioit_2024-25.csv` |
| Quotazioni snapshot settembre 2025 | OK | fanta.soccer `fantasoccer_2025-26_g02.csv` (29/08/2025) e `_g03.csv` (13/09/2025); in piu' Qt.I in `fantacalcioit_2025-26.csv` |
| xG | OK | `understat/understat_players_2019..2025.csv` (7 stagioni complete, 4.126 righe) + teams |
| Valori di mercato | OK | `transfermarkt/transfermarkt_valuations_seriea.csv` (38.707 righe, 2004→2026) |
| Bonus non richiesto | — | prezzi storici 2018/19–2022/23 (wayback), aste reali GE 3 stagioni, quotazioni per-giornata 2020/21–2022/23 complete |

## 3.2 Buchi veri — da recuperare A MANO

1. **Aste GE stagioni 2022/23 e 2025/26**: i 3 Google Sheet candidati sono stati
   rimossi (2x HTTP 410, 1x 404). Serve un nuovo link dal thread forum
   gruppoesperti `t=181911`; l'edizione 2025-26 (e la futura 2026-27) va cercata
   sul forum verso fine agosto 2026.
2. **Rose ufficiali + quotazioni 2026/27** (la stagione target dell'asta): non
   esistono ancora in nessuna fonte. Listone fantacalcio.it/fanta.soccer atteso
   fine agosto–inizio settembre 2026. Necessario anche per correggere
   transfermarkt (last_season=2025: gli acquisti estate 2026 risultano ancora al
   club precedente).
3. **fanta.soccer per-giornata, set completo**: il download in background e'
   stato interrotto a 153/228 file. Mancano 2023-24 g27–g38, 2024-25 e 2025-26
   tutte le giornate tranne le minime (1–4, 19, 38, gia' presenti). Le giornate
   minime richieste ci sono TUTTE: rilanciare `scripts/download_fantasoccer.py`
   (idempotente) solo se servira' il set completo.

## 3.3 Difetti di qualita' da sistemare in Fase 0b (non buchi di copertura)

1. **Entita' HTML nei voti**: `&#x27;` (apostrofo) presente nei nomi di tutte e
   5 le stagioni (176+356+307+369+58 = 1.266 righe; es. `D&#x27;Ambrosio`,
   `Dodo&#x27;`). Fix: `html.unescape` prima del matching.
2. **GE aste duplicate**: 13 aste 2024/25 identiche fra file principale/1Uxv42/1J4t
   (245 → 225 aste uniche); fingerprint in `gruppoesperti/build_stats.json`.
3. **GE `player_raw` sporco**: lowercase, refusi (`mikitarian`, `saelemakers`,
   `deroon`, `de cunha`), iniziali attaccate (`thuram m`). 110 aste su 245 con
   righe != componenti*25 (rose incomplete, dato crowdsourced).
4. **Separatori/formati eterogenei**: i CSV preesistenti in `fonti_prezzi/` usano
   `;` + BOM + decimali con virgola (`6,41`); tutto il resto e' virgola/UTF-8.
   Armonizzare in ingestione.
5. **Voti**: ~9,3% righe S.V. (filtrare con `sv=1`); allenatori assenti;
   ammonizioni/espulsioni derivate dalla classe CSS.
6. **Understat**: `position` e' il ruolo tattico (non P/D/C/A fantacalcio);
   trasferiti di gennaio in riga unica con team multiplo (35 casi nel 2024/25).
7. **Transfermarkt**: `transfer_fee` null in ~32% righe (fee ignota vs zero);
   1.000 presenze in meno nel 2019/20 (3 sostituzioni pre-COVID, atteso).
8. **Prezzi wayback storici**: 2018/19 e 2022/23 hanno solo la colonna
   `p350_8sq` e copertura prezzo parziale (194/641 e 386/668): utilizzabili per
   trend, non per training completo.

## 3.4 Regole di name matching che serviranno (esito del test overlap, sez. 2)

Il match esatto tra convenzioni diverse e' quasi nullo (1–3%) tranne
GE ↔ voti (73,7%: stessa convenzione "cognome"). Regole necessarie:

- **Convenzioni per fonte**: GE/voti = `COGNOME [iniziale]` (GE lowercase);
  wayback/fonti_prezzi = `COGNOME Nome`; understat = `Nome Cognome` con
  diacritici; fantacalcio.it quotazioni = `Cognome` con id numerico stabile;
  transfermarkt = `Nome Cognome` + player_id stabile.
- **Chiave consigliata**: squadra + ruolo + cognome normalizzato (NFKD,
  uppercase, no punteggiatura) + iniziale nome quando presente; fuzzy
  (Levenshtein/Jaro) come fallback; tabella alias manuale per i casi difficili.
- **Casi difficili emersi**: omonimi con iniziale (`MARTINEZ L`/`MARTINEZ J`,
  `KONE M`/`KONE B`, `VLAHOVIC`/`VLAHOVIC V`, `CARBONI A`); cognomi composti
  (`VAN DER BREMPT`, `GOURNA DOUATH`, `AKPA AKPRO`, `KOLO MUANI`, `DE ROON`
  scritto `deroon` in GE); nomi d'arte (`DODO'`, `TETE MORENTE`, `KIKE PEREZ`);
  nomi lunghi lusofoni (`ESTEVES GONCALO DO LAGO PONTES`); refusi GE
  (`SAELEMAKERS`→Saelemaekers, `MIKITARIAN`→Mkhitaryan, `DE CUNHA`→Da Cunha).
- Ancoraggio consigliato: usare `fantacalcioit_*.csv` (player_id) come spina
  dorsale dell'id giocatore per stagione e mappare le altre fonti su di essa.
"""


def main():
    with open(os.path.join(RAW, "_inventory_section.md"), encoding="utf-8") as f:
        inv = f.read()
    with open(os.path.join(RAW, "_overlap_section.md"), encoding="utf-8") as f:
        ove = f.read()
    out = HEADER + inv + "\n---\n\n# 2. Test overlap nomi (stagione 2024/25)\n" + ove + GAPS
    dest = os.path.join(RAW, "INVENTORY.md")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    print("OK ->", dest, f"({len(out.splitlines())} righe)")


if __name__ == "__main__":
    main()
