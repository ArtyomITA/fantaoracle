# VERIFICA indipendente — lavoro del 13/9/2026 sul Copilota

Verificatore indipendente dai due fixer. Sola lettura sul progetto: gli unici
file scritti da qui sono questo rapporto e le copie di ledger
`data/copilot/prove/V_1..4.json`. Porte usate: 8797, 8798, 8799 (tutte fermate
a fine prova). Mai toccati 8770 e 8899, mai toccati i tre ledger veri.

Scratch del verificatore:
`C:\Users\ADMINI~1\AppData\Local\Temp\claude\E--claudecode-pesante\5ff20539-b495-4ac4-bed4-79eabbf8a8b7\scratchpad\w11\V\`
(`replay_v.py`, `bonus_v.py`, `asta_v.py`, `ui_v.py` piu' i loro JSON e le
immagini).

---

## VERDETTO: PRONTO CON RISERVE

Il contratto A–I e' implementato per intero e i numeri dei fixer reggono al
ricontrollo indipendente: tetto Malen 289 contro i 275 pagati, Martinez L. 300
contro 255, Hojlund 219 contro 200, zero tetti sopra il massimo spendibile su
28 lotti, bonus gol esatto e applicato una volta sola, 250 martelletti senza un
errore in due ordini di ruoli diversi.

La riserva e' UNA e si vede al tavolo: **il numero grande sul banco oscilla ogni
due secondi** fra 289 e 272 (difetto V1, causa trovata e circoscritta a due
righe). Non e' un numero sbagliato, e' un numero che sfarfalla mentre il
banditore batte. Con la correzione di V1 il verdetto diventa PRONTO.

---

## 1. Diff contro il backup

`data/_backup_fable_20260913/` contro i file correnti (`diff -u`).

| file | esito |
|---|---|
| `src/fantabot/optimizer.py` | **identico** |
| `scripts/asta_registra.py` | **identico** |
| `tests/test_copilot_asta.py` | **identico** (i 13 test vecchi non sono stati toccati) |
| `src/fantabot/piani.py` | +7 righe: solo `piano_al_prezzo`, parametro additivo `calcola_riferimento=True` |
| `src/fantabot/bots/bot_b.py` | +18 righe: solo `_replan`, quota d'attacco sul residuo (voce I) |
| `src/fantabot/rules.py` | +13 righe: `BONUS_GOL_FONTE = 3.0`, `BONUS_GOL_LEGA = 5.0` con la misura in commento |
| `scripts/f10_copilot.py` | +560 righe circa, tutte additive |
| `viz/copilot.html` | +~500 righe (CSS in coda, HTML nei punti dichiarati, JS nuovo) |

Funzioni toccate in `scripts/f10_copilot.py`:

* modificate: `prepara_pack` (chiama `costruisci_gol` + `applica_bonus_gol`
  PRIMA della rettifica), `campi_gol` (+`gol_tot_2025`, `gol_tot_2026`),
  `player_info` (+campi gol, `bomber`, `gol_attesi`, `bonus_gol_lega`),
  `decisione_operativa` (tetto nuovo + campi del contratto A + parametro
  `avvia_calcolo`), `piani_alternativi`/`consiglio` (chiamano
  `decisione_operativa(..., avvia_calcolo=False)` e `scalda_indifferenza`),
  `contesto_piani` (voce I), handler `/copilot/state`, `/copilot/players`,
  POST `hammer`/`undo`/`escludi` (`INDIFF_CACHE.clear()`).
* nuove: `gol_attesi_di`, `applica_bonus_gol`, `calore_ruolo`,
  `calore_per_ruolo`, `e_bomber`, `livello_gol`, `bomber_nel_pool`,
  `contendenti_per`, `quota_scarsita`, `tetto_scarsita`, `cap_col_calore`,
  `contesto_indifferenza`, `_valore_e_gol`, `_lavora_indifferenza`,
  `prezzo_indifferenza`, `scalda_indifferenza`, `spendibile_ora`,
  `scarsita_ruoli`, `gol_di_rosa`, `gol_rosa`, rotta `/copilot/gol_rosa`.

Regressioni cercate, esito:

| cosa | esito |
|---|---|
| percorsi assoluti nuovi nel codice | **nessuno** (`grep -nE "[A-Za-z]:\\\\|/Users/|/home/"` su f10, bot_b, piani, rules, copilot.html: 0 righe) |
| credenziali / token / chiavi | **nessuna** |
| print rumorosi | 18 `print(` in tutto f10, di cui nuovi: 1 riepilogo all'avvio, 3 su ramo d'errore. Nessuno per richiesta |
| eccezioni non gestite | i tre punti nuovi che possono esplodere (`_lavora_indifferenza`, `contesto_indifferenza`, `scalda_indifferenza`) hanno `except Exception` con messaggio; `do_POST`/`do_GET` avevano gia' la rete di sicurezza |
| LOCK tenuto durante il MILP | **no**. Sotto lock si costruisce solo il `Contesto` (nessun `_risolvi`); la bisezione gira in `_lavora_indifferenza`, in un thread, e riprende il lock solo per scrivere in cache |
| thread senza daemon | **no**: `threading.Thread(..., daemon=True)` |
| cache senza chiave di versione | **no**: chiave `(versione_stato(), pid)`, e `INDIFF_CACHE.clear()` su hammer, undo, escludi |
| nomi del contratto diversi fra server e UI | **nessuno**: tutti i 15 campi del contratto A, i 15 di B, i blocchi `spendibile`/`calore_per_ruolo`/`scarsita` di C e le chiavi di D compaiono con lo stesso nome nel `.py` e nel `.html` |

`viz/ponte_fantaasta.js`: **non toccato**, mtime 2026-09-10 18:41, 11 502 byte.
`viz/ponte.html` risulta riscritto oggi alle 14:59 — non e' opera dei fixer: e'
`tests/test_ponte_fantaasta.py::test_pagina_contiene_link_e_istruzioni` che
chiama `pb.scrivi_pagina(8770)` e rigenera la pagina (stessa dimensione, 36 550
byte, generatore deterministico con la porta di default). Effetto collaterale
di un test **pre-esistente**, non una regressione di oggi.

---

## 2. Test

Dalla radice, `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest ... -p no:cacheprovider -q`.

```
tests/test_copilot_asta.py tests/test_copilot_tetto.py
tests/test_ponte_fantaasta.py tests/test_bot_l3_tetti.py
-> 70 passed, 1 skipped, 110606 warnings in 13.53s
```

L'unico skip:

```
SKIPPED [1] tests\test_copilot_asta.py:141: nessun attivo senza previsione
```

pre-esistente, dipende dai dati del bundle, non dai cambiamenti.

```
tests/test_bot_l3_parita.py
-> 1 failed, 9 passed, 569734 warnings in 88.97s (0:01:28)

FAILED tests/test_bot_l3_parita.py::test_il_piano_cambia_davvero_l_asta
E   AssertionError: L3 impegna sul piano 105 crediti, B+ ne impegna 180:
E   inseguire il piano non sta cambiando dove finiscono i soldi
E   assert 105 > 180
```

Rossa gia' il 10/9 e dichiarata dal fixer come pre-esistente; i numeri sono gli
stessi anche col `bot_b.py` del backup. **Non regredita, non risolta.**

I 12 test nuovi (`tests/test_copilot_tetto.py`) coprono: gli 8 casi del
prototipo A2 su `tetto_scarsita`, gli estremi di `quota_scarsita`, Malen ev190,
niente premio a chi non fa gol, Hojlund, fine asta, difensore a tavolo vuoto,
gol e ordinamenti in `/copilot/players`, `/copilot/gol_rosa`, `/copilot/state`,
bonus gol, tempi. Nessuno indebolisce i test vecchi.

---

## 3. Replay indipendente

Non ho riusato `replay_tetto.md`. Ho ricostruito lo stato in-process io stesso
(stesso schema della fixture `cop`) con `w11/V/replay_v.py` e ho lasciato
`reports/asta_20260913/replay_tetto.md` intatto.

28 attaccanti battuti a 40+ crediti. **Il tetto arriva al prezzo in 8 su 28;
tetti sopra il massimo spendibile: 0.** Numeri identici a quelli dichiarati.

```
  ev nome              pag  vecc  capN   ind   sp  bmb  cnt   quo   TET  ok   t1ms   tPr
 190 Malen             275   122   182   244  311    3    8 0.667   289  SI   14.0  1.43
 192 Kolo Muani         60    38    74     -  311    0    8   0.0    74  SI    0.7     -
 193 Martinez L.       255   127   209   231  311    1    6 0.857   300  SI   12.4  1.25
 194 De Ketelaere       41    31    55     -  311    0    9   0.0    55  SI    0.8     -
 195 Dybala            137    21    36     -  311    0    9   0.0    36  no    0.7     -
 196 Lauriente          52    26    48     -  311    0    9   0.0    48  no    0.8     -
 198 Ramos G.          205   110   201     -  311    0    5   0.0   201  no    0.7     -
 199 Raimondo           80    23    42   251  311    8    2   0.0   251  SI   14.4  1.23
 200 Hojlund           200   102   191   188  311    3    3  0.25   219  SI    7.6  1.22
 201 Thuram            146    45    84     0  112    2    9   0.8    90  no   14.8  0.42
 202 Kean               80    39    71     -  112    0    9   0.0    71  no    0.8     -
 203 Douvikas          140    30    52     0  112    1    9   0.9   101  no   12.2  0.42
 205 Woltemade          50    34    60     -  112    0    9   0.0    60  SI    1.2     -
 206 Diao               90    13    22     -   63    0    9   0.0    22  no    1.0     -
 207 Soule              46    36    62     -   63    0    8   0.0    62  SI    1.3     -
 208 Davis K.           74    24    41    29   63    4    9   0.6    49  no   15.4  1.24
 209 Pinamonti          61    15    25     -   63    0    9   0.0    25  no    0.8     -
 211 Esposito F.P.      66    24    40     -   63    0    9   0.0    40  no    1.1     -
 212 Scamacca           60    28    46     1   63    3    9   0.7    46  no   14.5  1.03
 213 Dovbyk             42    13    21     -   63    0    9   0.0    21  no    0.7     -
 215 Simeone            63    17    27     3   63    1    9   0.9    57  no   14.6  1.23
 216 Berardi           127     1     1     -    1    0    9   0.0     1  no    0.7     -
 218 Piccoli            41     1     1     -    1    0    9   0.0     1  no    0.9     -
 219 Castro S.          40     1     1     -    1    0    9   0.0     1  no    0.7     -
 220 Colombo            47     1     1     -    1    0    9   0.0     1  no    0.8     -
 226 Yildiz             61     1     1     -    1    1    9   0.9     1  no    6.7  0.21
 229 Yeboah J.          56     1     1     -    1    0    9   0.0     1  no    0.8     -
 230 Raspadori          47     1     1     -    1    0    9   0.0     1  no    0.6     -
```

(`vecc` = tetto che il bot produce da solo col calore globale, ricalcolato oggi;
`capN` = stesso tetto col calore del ruolo; `sp` = massimo spendibile;
`t1ms` = prima risposta; `tPr` = quando il prezzo di indifferenza e' pronto.)

### Tre righe ricontrollate a mano

**Malen, evento 190** (id 5585, pagato 275 da Ac Mignottingham Forest).
Cassa mia 316, slot liberi 6 (tutti A). Massimo spendibile ricalcolato a mano:
`316 - (6 - 1) = 311`, il server dice 311, `view.me.max_bid` dice 311: **tre
strade, stesso numero**. cap bot col calore del ruolo 182, prezzo di
indifferenza 244, 3 bomber bravi quanto lui, 8 contendenti -> n = 9,
quota `(9 - 3)/9 = 0.667`.
Formula del contratto: `min(311, max(182, round(244 + 0.667*(311 - 244)))) =
min(311, max(182, 289)) = 289`. **Il server dice 289.**

**Evento 199** (Raimondo, pagato 80; Hojlund e' l'evento 200, non il 199).
Massimo spendibile 311 = 316 - 5, cap bot 42, indifferenza 251, 8 bomber per 3
squadre -> quota 0, tetto `max(42, 251) = 251`. Formula rispettata.
Hojlund all'evento 200: cap bot 191, indifferenza 188, 3 bomber per 4 squadre,
quota 0.25, tetto `188 + 0.25*(311 - 188) = 219` contro i 200 pagati.

**Un attaccante da 1 credito**: Osmajic, evento 197, battuto a 1.
`e_bomber = False`, quota 0, tetto 7 = cap bot, massimo spendibile 311.
**Nessun premio dove non deve essercene.**

### Invarianti

| controllo | esito |
|---|---|
| tetto <= max_spendibile su tutti i 28 lotti | **0 sfori** |
| tetto <= max_spendibile su un campione dei 6 migliori per valore in P, D, C, A a ev190 (24 lotti) | **0 sfori** |
| premio zero per P e D | **0 casi con quota o premio > 0** |
| premio zero per i non bomber | **0 casi** |
| obbligo di completare ancora vivo | pool A ridotto a 6 per 6 slot -> `obbligo: true`, tetto 311 = massimo legale, motivo «obbligo di completare la rosa: massimo legale». `tests/test_copilot_asta.py::test_obbligo_di_completare` verde |
| prezzo di indifferenza «pronto» entro 8 s | si': il piu' lento dei 28 e' **1,43 s**; 0 casi oltre 8 s |
| `/copilot/advice` non si blocca | prima risposta max **15,4 ms** in-process; 20 chiamate sul server vero: min 3,4 ms, media 11,3 ms, p95 28,3 ms, **max 83,7 ms** (soglia 150 ms) |

---

## 4. Bonus gol di lega

`w11/V/bonus_v.py`, misure su 594 previsioni.

| controllo | esito |
|---|---|
| `BONUS_GOL_FONTE = 3.0`, `BONUS_GOL_LEGA = 5.0` in `src/fantabot/rules.py` | si' |
| delta == `2 * gol_attesi` | **425 rettificati, 0 scostamenti** |
| chi non ha storico ha `gol_attesi = null` e delta 0 | **0 violazioni** (169 casi senza storico) |
| `PACK.b_predictions` sporcato in luogo | **no**: 0 previsioni del pack contengono `bonus_gol_lega` o `gol_attesi` |
| applicato una volta sola | si': rifare `prepara_pack` non cambia un valore (200 controllati), e `rebuild_advisor()` non riapplica |
| `value_up >= value` | **0 violazioni dopo** (ed erano gia' 0 prima: il bonus e' lo stesso su tutti i quantili) |
| i prezzi non si toccano | `q50`/`q90` identici al pack su 500 controllati |
| rettifica indisponibili DOPO il bonus | si'. Oggi il ramo non scatta (pack piu' recente delle fonti: 0 rettificati). Forzandolo (`data_del_pack` finto al 1/1/2026) si ottengono 55 rettificati e per tutti `value_originale == value_del_pack + bonus`: p.es. Orsolini 210,9 -> +14,5 -> originale 225,4 -> finale 212,5. **L'ordine e' quello giusto: chi salta mezza stagione perde anche il bonus di quelle giornate.** |

Riga di riepilogo all'avvio:

```
bonus gol lega (+5 contro +3 della fonte): P 0 rettificati, +0.0 medio,
D 69 rettificati, +3.3 medio, C 110 rettificati, +5.5 medio,
A 64 rettificati, +10.5 medio
```

I quattro nomi chiesti (il «prima» e' `PACK.b_predictions`):

| giocatore | ruolo | gol+rig 2025 | pres 25 | pres prevista | gol attesi | delta | value prima | value dopo | value_up prima | value_up dopo | q90 prima | q90 dopo |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Malen | A | 11+3 = 14 | 18 | 29,5 | 16,80 | +33,60 | 300,2 | **333,8** | 309,6 | 343,2 | 322,2 | 355,8 |
| Martinez L. | A | 17+0 = 17 | 30 | 31,2 | 17,68 | +35,36 | 267,2 | **302,6** | 275,4 | 310,8 | 285,0 | 320,4 |
| Adopo | C | 1+0 = 1 | 38 | 32,3 | 0,85 | +1,70 | 199,7 | **201,4** | 224,3 | 226,0 | 232,5 | 234,2 |
| Woltemade | A | nessun dato | — | 21,3 | **null** | **0,00** | 161,2 | **161,2** | 192,3 | 192,3 | 206,8 | 206,8 |

Malen: 14 gol in 18 presenze, 29,5 previste, tetto a +20% -> 16,8 attesi, +33,6
punti. Woltemade non ha giocato in Serie A e ha una sola presenza 2026-27
(sotto la soglia di 2): niente bonus, `gol_attesi` **null e non zero**, come
chiede il contratto.

---

## 5. Asta vera simulata

Server sulla porta 8798 con `--ledger data/copilot/prove/V_2.json` (vuoto),
setup 10 squadre `Prova0..Prova9`, `my_index 0`, 500 crediti, quote 3/8/8/6.
Poi i 250 `POST /copilot/hammer` del ledger del 10/9 in ordine
(`player_id`, `team_index`, `price`, `richiesta_id`), con un
`GET /copilot/advice` per il giocatore al banco prima di ogni martelletto di A.

| misura | ordine vero (8798) | ordine ruoli C,A,P,D (8799) |
|---|---|---|
| martelletti | 250 | 250 |
| errori 500 / `ok:false` | **0** | **0** |
| tempo POST hammer: media / p95 / max | 102,7 / 249,1 / **354,3 ms** | 95,6 / 254,0 / **348,6 ms** |
| tempo GET advice (60 attaccanti): media / p95 / max | 7,1 / 21,8 / **27,6 ms** | 7,0 / 19,0 / **31,6 ms** |
| chiamate oltre 2 s | **0** | **0** |
| `/copilot/state` a fine asta | 11,1 ms | 10,7 ms |
| crediti per squadra identici al ledger vero | **si'** (10 su 10) | **si'** (10 su 10) |
| `/copilot/gol_rosa` | 3,5 ms, 10 squadre, media di lega 57,5 | 3,4 ms, identico |

Calore per ruolo a fine asta, uguale nei due ordini (dipende dallo stato, non
dalla sequenza): `P 0.883, D 0.696, C 0.579, A 1.491`, contro un calore globale
di 0,98. **E' il difetto D2 misurato: il mercato «medio» dice 0,98 mentre gli
attaccanti sono andati a 1,49 volte le q50 e i centrocampisti a 0,58.**

Con l'ordine dei ruoli rovesciato la correzione si vede meglio ancora,
fotografando il calore a meta' strada:

```
fine blocco C, zero A battuti | globale 0.621 | per ruolo {P 1.0, D 1.0, C 0.579, A 1.0}
10 A battuti                  | globale 0.888 | per ruolo {P 1.0, D 1.0, C 0.579, A 1.567}
40 A battuti                  | globale 1.077 | per ruolo {P 1.0, D 1.0, C 0.579, A 1.544}
```

All'inizio del blocco A il calore globale dice 0,62 («mercato freddo», e i
tetti degli attaccanti scenderebbero del 38 %) mentre il calore del ruolo dice
1,0 — «non lo so ancora», che e' la risposta giusta. **L'ordine dei ruoli
casuale di stasera non rompe niente**, e `spendibile` resta coerente
(`crediti 7, slot 0, max_ora 0` a rosa piena, senza il vecchio `budget+1`).

---

## 6. UI headless

Playwright Chrome headless 1366x768 contro il mio server (porta 8797,
`--resume data/copilot/prove/V_4.json`, copia troncata a 190 eventi).
Script `w11/V/ui_v.py`, immagini in `w11/V/`.

**14 prove, 0 fallite.**

| prova | esito |
|---|---|
| `#hSpendibile` == 311 (e == `state.spendibile.max_ora`) | OK |
| Malen trovato e messo al banco a 150 | OK |
| il riquadro dice «spendibili 311» | OK |
| il numero grande e' `max_consigliato` del server (289) | OK |
| prezzo di indifferenza consegnato (non resta «in calcolo») | OK, 1,0 s |
| `#advice` sopra la piega | OK, bottom 654 su 768 |
| `#golRosa` ha 10 righe, 1 evidenziata come mia | OK |
| `ordina=gol` mette davanti un bomber | OK, Martinez L. con 17 gol |
| nessun «NaN» a schermo | OK |
| nessun «undefined» a schermo | OK |
| console senza errori, nessuna eccezione di pagina | OK |
| nessun endpoint sopra 2 richieste/s | OK |

Ritmo delle richieste in 16 s di pagina viva:
`/copilot/state` 8 chiamate, max 1 al secondo; `/copilot/players` 3, max 2 in
un secondo (due click miei di fila); `/copilot/advice` 3, max 2 in un secondo.
**Polling non esploso.**

Testo letto a schermo col banco su Malen a 150:

```
CONSIGLIO DELL'ORACOLO - AL PREZZO 150
RILANCIA fino a 289
titolare del tuo piano - costo-ombra se lo perdi 31.9 - mediana lega 145
spendibili 311 - cap bot 182 - indifferenza 244 - calore reparto x1
3 bomber per 9 squadre con slot e cassa - quota 0.7
con lui a 289: 4685 pt - 18 gol | senza: 5243 pt - 24 gol
possono superarti: 5 (Ac Mignottingham Forest, Nightmare fc, MoreiraDiFame,
ROCKS PIRATE, SSSP)
```

Immagini: `w11/V/V_malen_150.png` (viewport), `V_malen_150_intera.png`
(pagina intera), `V_lista_gol.png` (lista ordinata per gol).

Nota importante: la nota del fixer UI («il server vero manda bomber_rimasti 11
contro 9 squadre, quota 0, tetto Malen 244») **non e' piu' vera**. Contro il
server corrente, a ev190, la pagina riceve `bomber_rimasti 3`,
`squadre_contendenti 8`, `quota 0.7`, `max_consigliato 289`. Quella misura e'
stata fatta prima del secondo scostamento dichiarato dal fixer server
(`bomber_nel_pool(..., almeno=livello_gol(pid))`).

---

## 7. Ponte

`tests/test_ponte_fantaasta.py`: **5 passed** (dentro la passata del punto 2).
`viz/ponte_fantaasta.js` non toccato: mtime 2026-09-10 18:41, 11 502 byte,
identico a prima del lavoro di oggi (i fixer non lo elencano e la data lo
conferma).
`viz/ponte.html` riscritto dal test stesso, vedi punto 1: effetto collaterale
pre-esistente, contenuto invariato.

---

## DIFETTI TROVATI

### V1 — GRAVE (per l'uso, non per i numeri): il tetto sul banco sfarfalla ogni 2 secondi

**Dove**: `scripts/f10_copilot.py:1086`, dentro `_lavora_indifferenza`.

```python
with LOCK:
    INDIFF_IN_CORSO.discard((versione, pid))
    if versione == versione_stato():
        INDIFF_CACHE.clear()      # <-- QUI
        INDIFF_CACHE[(versione, pid)] = esito
```

La cache viene **svuotata tutta** e non solo delle chiavi vecchie: ogni
bisezione che finisce butta via il risultato di tutti gli altri giocatori dello
**stesso** stato. E `scalda_indifferenza("A", 3)`, chiamata alla fine di ogni
`/copilot/advice`, ne lancia continuamente di nuove.

**Prova**, server vero sulla 8797 a ev190, Malen al banco a 150, una chiamata
ogni 2 s per 32 s (esattamente il ritmo della pagina):

```
t=0s  in_calcolo  p_ind None  tetto 272
t=2s  pronto      p_ind 244   tetto 289
t=4s  in_calcolo  p_ind None  tetto 272
t=6s  pronto      p_ind 244   tetto 289
...  (alternanza perfetta per tutte le 16 chiamate)
```

Controprova: spegnendo il solo pre-riscaldamento
(`c.scalda_indifferenza = lambda *a, **k: None`) e ripetendo 8 volte:
`pronto 289` otto volte su otto, stabile.

Seconda prova dello stesso difetto: pre-riscaldando i tre bomber di testa
(Martinez L., Malen, Douvikas) e aspettando che finiscano, in cache resta
**1 chiave su 3** (Douvikas) — il pre-riscaldamento, cioe' la funzione per cui
e' stato scritto, oggi non funziona.

**Effetto stasera**: mentre il banditore batte, il numero grande passa
289 -> 272 -> 289 -> 272 ogni due secondi, e la riga sotto passa da
«indifferenza 244» a «indifferenza n/a». Nessuno dei due numeri e' sbagliato
(272 e' il tetto col ripiego `p_ind = cap_bot`), ma un consiglio che balla
sotto pressione e' un consiglio che non si segue. In piu' la macchina lancia
CBC in continuazione per ricalcolare quello che aveva gia'.

**Correzione (due righe, nessun cambio di contratto)**: sostituire lo
svuotamento totale con una potatura per versione, che e' esattamente quello che
il ramo `else` sotto fa gia':

```python
    if versione == versione_stato():
        for chiave in [k for k in INDIFF_CACHE if k[0] != versione]:
            del INDIFF_CACHE[chiave]
        INDIFF_CACHE[(versione, pid)] = esito
```

Da riprovare dopo: la sequenza di 16 chiamate deve dare 16 volte `pronto 289`.

### V2 — MEDIO: «con lui / senza di lui» dice il contrario del numero grande

Sempre a ev190 su Malen la pagina scrive, uno sotto l'altro:

```
RILANCIA fino a 289
con lui a 289: 4685 pt - 18 gol | senza: 5243 pt - 24 gol
```

Il confronto e' calcolato **al tetto** (289), che per costruzione sta sopra il
prezzo di indifferenza (244): a quel prezzo il piano senza di lui e' migliore,
ed e' giusto che lo dica. Ma al tavolo si legge «pagalo 289» e subito sotto
«senza di lui hai 6 gol e 558 punti in piu'»: due frasi che sembrano
contraddirsi, e la seconda e' quella che spaventa.

Non e' un numero sbagliato ed e' fuori dal contratto correggerlo stasera. Da
sapere prima di sedersi: **il tetto e' un limite, non una raccomandazione**, e
la riga «con lui / senza» dice cosa succede se lo si paga fino in fondo.
(Se si volesse migliorare: mostrare il confronto al **prezzo corrente** invece
che al tetto, o al prezzo di indifferenza.)

### V3 — MEDIO, da guardare al tavolo: tetti alti su lotti che il mercato ha pagato poco

Nel replay ci sono tetti molto sopra il prezzo vero, tutti per lo stesso
motivo: prezzo di indifferenza alto e pochi bomber rimasti.

| lotto | pagato dal tavolo | tetto nuovo | perche' |
|---|---|---|---|
| Raimondo (ev 199) | 80 | **251** | indifferenza 251, 8 bomber ma 2 soli contendenti: quota 0, tetto = indifferenza |
| Simeone (ev 215) | 63 | **57** su 63 spendibili | indifferenza 3, ma 1 bomber per 10 squadre: quota 0,9 |
| Douvikas (ev 203) | 140 | **101** su 112 | quota 0,9 |
| Davis K. (ev 208) | 74 | **49** su 63 | quota 0,6 |

Sono tetti, non offerte, e il difetto vero (D1) era l'opposto. Ma la formula
«indifferenza + quota * (spendibile - indifferenza)» con quota 0,9 spinge il
limite al 90 % della cassa residua: se stasera si tratta il tetto come un
prezzo da raggiungere, si finisce l'asta con un solo nome e otto riempitivi.
Gia' segnalato dal fixer per Raimondo; lo confermo e lo allargo.

### V4 — LIEVE: `cap_bot` non e' calcolato come dice la voce F

Il contratto dice `cap_bot = ADVISOR._max_bid_for(pid) / market_heat() *
calore_ruolo(R)`. Il codice parte invece dal tetto ottenuto per bisezione su
`_il_bot_pagherebbe` (che tiene conto anche del limite legale e della strada
del bargain) e poi riscala. Misure a ev190:

| giocatore | contratto F | codice |
|---|---|---|
| Malen | 182 | 182 |
| Martinez L. | 177 | 176 |
| Ramos G. | 123 | 122 |
| Hojlund | 111 | **53** |

Quasi ovunque coincidono; dove no (Hojlund a ev190, che non e' il suo lotto) il
codice e' **piu' prudente**. Siccome `cap_bot` e' solo il pavimento del tetto,
l'effetto sul numero finale e' nullo o conservativo. Scostamento non dichiarato
dal fixer: da mettere a verbale, non da correggere stasera.

### V5 — LIEVE: un test riscrive un file del progetto

`tests/test_ponte_fantaasta.py::test_pagina_contiene_link_e_istruzioni` chiama
`pb.scrivi_pagina(8770)` e sovrascrive `viz/ponte.html` a ogni esecuzione.
Pre-esistente, contenuto identico, nessun danno; ma un test non dovrebbe
scrivere in `viz/`.

### Scostamenti dal contratto gia' dichiarati dal fixer — verificati e accettati

* `MIN_GOL_2026_BOMBER = 3` nel secondo ramo di `e_bomber`. Senza, con 3
  giornate in archivio un gol proietta 12,7 gol e i bomber diventano 27 su 86:
  scarsita' nulla e premio morto. Con la soglia, 11. **Ricontato: 11 bomber nel
  pool A a ev190** (`/copilot/state` -> `scarsita.A.bomber_pool = 11`), e
  Osmajic (0 gol veri) risulta correttamente non bomber.
* `bomber_nel_pool(ruolo, almeno=livello_gol(pid))` per `bomber_rimasti`.
  Contro il contratto letterale, ma senza quel filtro Malen ha «11 bomber per
  9 squadre» -> quota 0 -> tetto 244, e il premio non scatta su nessuno dei 4
  lotti della diagnosi. Col filtro: 3 bomber, quota 0,667, tetto 289.
  Confermato in laboratorio e sul server vero.

---

## PROVE ESEGUITE (indice)

| cosa | comando | esito |
|---|---|---|
| diff col backup | `diff -u data/_backup_fable_20260913/<f> <corrente>` | 4 file modificati come dichiarato, 3 identici |
| test principali | `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_copilot_asta.py tests/test_copilot_tetto.py tests/test_ponte_fantaasta.py tests/test_bot_l3_tetti.py -p no:cacheprovider -q` | 70 passed, 1 skipped, 13,53 s |
| parita' L3 | `... python -m pytest tests/test_bot_l3_parita.py -p no:cacheprovider -q` | 1 failed (pre-esistente), 9 passed, 88,97 s |
| replay indipendente | `PYTHONPATH=src python w11/V/replay_v.py` | 28 lotti, 8 arrivano, 0 sfori, indifferenza pronta in <= 1,43 s |
| bonus gol | `PYTHONPATH=src python w11/V/bonus_v.py` | 425 rettificati, 0 scostamenti, idempotente |
| ordine bonus/rettifica | `python -c` con `data_del_pack` finto | 55 rettificati, `value_originale == pack + bonus` sempre |
| asta 250 martelletti | `python w11/V/asta_v.py 8798 vero` | 0 errori, max 354 ms, crediti coerenti |
| asta ordine C,A,P,D | `python w11/V/asta_v.py 8799 ruoli` | 0 errori, max 349 ms, crediti coerenti |
| calore a meta' asta | `python -c` in-process | globale 0,62 contro calore A 1,0 a inizio blocco |
| UI headless | `python w11/V/ui_v.py 8797` | 14 prove, 0 fallite |
| tempi advice | 20 chiamate con `time.perf_counter` | max 83,7 ms (soglia 150) |
| stabilita' indifferenza | 16 chiamate ogni 2 s | **alternanza pronto/in_calcolo: difetto V1** |

Server fermati: 8797, 8798, 8799. Ledger di prova lasciati in
`data/copilot/prove/V_1..4.json` (copie, mai gli originali).
