# Livello 0 chiuso e Livello 1 avviato — 6-7 settembre 2026

Lavoro autorizzato dopo il controllo indipendente. Sostituisce le parti
superate di `LIVELLO0.md`, `CHECK_20260906.md` e `CHECK_O3_O4.md`, che restano
come storia. Ogni numero qui e' riproducibile con lo script citato.

---

## 1. Anticipazione nel simulatore: chiusa

**Problema.** Due punti guardavano avanti quando sceglievano la formazione.

| File | Riga | Cosa faceva | Cosa alimenta |
|---|---|---|---|
| `src/fantabot/season/simulate.py` | 85 | alla **prima** giornata passava a `pick_lineup` chi avrebbe preso voto | f13, torneo, O3, tutti i confronti fra rose |
| `src/fantabot/season/detail.py` | 38 | lo faceva a **tutte** le 38 giornate | vista della stagione dopo la Sedia (`f6_live_auction.py:334`) |

`lineup.py:40` conferma che l'argomento conta: `rank_key` mette in fondo chi non
e' nell'elenco, quindi cambia gli undici.

**Correzione.** In entrambi la formazione usa ora chi ha giocato la giornata
precedente; alla prima giornata nessuna informazione. Le sostituzioni
automatiche continuano a usare i voti realizzati: avvengono a consuntivo, come
da regolamento.

**Controllo permanente.** `tests/test_non_anticipazione.py`: tiene identico il
passato, cambia gli esiti del turno e pretende la stessa formazione; in piu'
registra cosa i due moduli passano a `pick_lineup` giornata per giornata.
Prima della correzione il test su `detail.py` falliva; ora i tre test passano.

**Onesta'.** Non attribuisco a questo il 99% di vittorie ne' il residuo di
cassa: sono misure distinte e non le ho legate.

---

## 2. Contratto dei dati (Livello 1, parte A)

**Semantica dei gol, verificata invece che assunta.** Il rigore segnato **non**
e' compreso in `gol_fatti`. Prova: ricostruendo il punteggio della fonte senza
sommarlo restano 100, 78 e 81 righe discordanti nelle tre stagioni, tutte con
`rigore_segnato > 0` e scarto esattamente -3.0 (o -6.0 con due rigori).
Sommandolo a parte:

| stagione | righe con voto | riconciliate entro 0.01 |
|---|---|---|
| 2021-22 | 10.654 | 100.0000% |
| 2023-24 | 10.805 | 100.0000% |
| 2024-25 | 10.719 | 99.9907% (1 discordante) |
| 2025-26 | 10.787 | 100.0000% |
| 2026-27 | 586 | 100.0000% |

Formula del contratto, valida prima di qualunque regola di lega:

    fantavoto = voto + 3*(gol_fatti + rigore_segnato) + assist
                - 0.5*ammonizione - espulsione
                + 3*rigori_parati - 3*rigori_sbagliati - 2*autogol
                - gol_subiti (solo portieri)

L'unica discordanza rimasta e' Delprato (Parma, giornata 3 del 2024-25): voto
6.5, fantavoto della fonte 4.0, scarto 2.0. Non spiegata. **Da chiarire**, non
corretta.

**Panel.** `scripts/f14_build_panel.py` costruisce
`data/processed/panel_{stagione}.parquet`: una riga per giocatore x partita,
con identificativi, giornata, data, minuti, avversario, risultato, componenti
del punteggio, stato e provenienza di ogni blocco. Stati tenuti distinti:
`con_voto`, `senza_voto`, e per costruzione mai confusi con "infortunato": la
fonte non dice il motivo.

Verifiche stratificate:

| stagione | righe | master_id | partita agganciata | duplicati | nuovi vs vecchi (partita) |
|---|---|---|---|---|---|
| 2021-22 | 11.674 | 99,5% | 97,1% | 1 | 96,19% / 97,49% |
| 2023-24 | 11.904 | 99,66% | 98,55% | 2 | 98,11% / 99,12% |
| 2024-25 | 11.886 | 99,73% | 99,21% | 0 | 99,54% / 99,45% |
| 2025-26 | 11.926 | 99,76% | 98,24% | 0 | 96,26% / 99,13% |
| 2026-27 | 638 | 99,06% | **0%** | 0 | 0% / 0% |

Tre difetti, tutti dichiarati e **non corretti**:

1. **2026-27 senza partite**: `games.csv.gz` copre fino alla stagione 2025.
   Per la stagione in corso il panel non ha minuti, avversario ne' risultato.
2. **1-2 coppie (giocatore, giornata) duplicate** nel 2021-22 e 2023-24: sono
   omonimi che condividono lo stesso identificativo Transfermarkt (es. Ricci S.
   dell'Empoli agganciato a due partite della stessa giornata). Una riga su
   ~11.900.
3. **Universo atteso non ancora imposto**: il panel parte dai voti, quindi chi
   non compare non genera una riga `non_convocato`. Va aggiunto incrociando il
   listone con le partite della sua squadra.

Il "99,5%" di prima era **copertura di identita'**, non correttezza del join
per partita: quello e' verificato ora, separatamente (0 coppie doppie nel
2024-25, 100% delle presenze Transfermarkt agganciate a una partita).

**Disciplina temporale, un punto aperto.** `f0b_match.py:475` sceglie la
rilevazione fanta.soccer piu' vicina al 1° settembre **in valore assoluto**.
Verificato: 2021-22 al 27/08, 2023-24 al 01/09, 2024-25 al 30/08, 2025-26 al
29/08, **2026-27 al 04/09**, cioe' dopo. Le stagioni di addestramento usano una
foto precedente, quella in produzione una successiva. Non e' leakage per l'uso
reale (l'asta e' dopo il 4/9) ma e' un'asimmetria fra addestramento e
produzione. **Non corretta**: propongo una data di riferimento esplicita per
esperimento, con filtro "solo cio' che esisteva entro quella data".

---

## 3. Banco di prova, baseline (Livello 1, parte B)

`scripts/f15_banco.py` misura il comportamento attuale su tre livelli
separati. Non fissa criteri di accettazione: quelli vanno decisi guardando
questi numeri e scritti prima del prossimo esperimento.

| | 2024/25 | 2025/26 |
|---|---|---|
| **prezzo** (n=255, target = media aste estive reali) | errore 5,64 cr, scarto +1,38, ordinamento 0,833 | nessun prezzo osservato: diagnostico |
| copertura q10-q90 | 68% (sotto 24%, sopra 9%), ampiezza 10,7 cr | — |
| **punti** | errore 31,45, scarto -9,31, ordinamento 0,864 | errore 32,7, scarto -5,3, ordinamento 0,857 |
| sopra la stima alta | 29% | 27% |
| **presenze** | errore 5,52 partite, scarto -0,97 | errore 5,62, scarto -1,90 |
| **effetto squadra x giornata** (dai voti reali) | 25,4% della varianza | 29,1% |
| covarianza media fra compagni | 0,0624 | 0,0762 |
| correlazione portiere-difensori | 0,181 | 0,217 |

Le ultime tre righe sono **bersagli** per il simulatore, non sue prestazioni.
Attenzione al metodo: questa quota (25-29%) e' calcolata sullo scarto dalla
media individuale del voto, ed e' un'altra cosa dal 13-20% citato nei report
precedenti, che veniva da una decomposizione diversa. **Non vanno confrontate.**
Il valore oggi nel codice (`TEAM_SHOCK_SD = 0.25`, cioe' varianza 0,0625) sta
sotto il bersaglio misurato qui (0,0805-0,0937, cioe' scarto 0,28-0,31).
**Non modificato**: prima va deciso quale delle due decomposizioni e' quella
giusta per il simulatore.

Avvertenze scritte nello script: 2024/25 e 2025/26 sono state consultate molte
volte e non sono piu' test puliti; cambiare seme non le ripulisce; cento
calendari sulle stesse rose non sono cento stagioni indipendenti.

---

## 4. Tracciabilita' senza controllo di versione

`scripts/f16_istantanea.py` copia i file che determinano un risultato e ne
registra l'impronta, piu' l'ambiente. Perimetro: `src/`, `scripts/`, `config/`,
`tests/`, i pack, le predizioni e i `players_*.parquet`; di `data/raw`
(153 MB) si registra solo l'impronta, senza copiarlo. In tutto 335 file, di cui
125 copiati per 3,0 MB. Con `--verifica` dice cosa e' cambiato dall'ultima
istantanea senza scrivere nulla.

Detto chiaramente: le impronte identificano il codice e i dati, **non bastano a
riprodurre**. Servono anche i semi casuali e i parametri, che vanno scritti
nelle note dell'esperimento.

---

## 5. Inventario, con dipendenze verificate

Nessun file spostato o cancellato.

| Percorso | Dim | Funzione | Dipendenze verificate | Proposta |
|---|---|---|---|---|
| `data/raw/` | 153 MB | fonti originali | tutta la pipeline | **tenere** |
| `data/processed/` | 13,4 MB | parquet, predizioni, panel | tutto | **tenere** |
| `data/packs/` | 1,2 MB | ciò che leggono bot e Copilota | f6, f10, f12, f13 | **tenere** |
| `data/baseline_20260905/` | 1,7 MB | stato del 5/9 | `rerun_appaiato_baseline.py` | **archiviare** |
| `data/live_logs/` | 3,7 MB | **partite di allenamento contro bot**, non aste reali (verificato: al tavolo ci sono A/B/C e "TU") | menu, `fantaoracle_app.py:92,126,171` per la ripresa | **tenere**: spostarli rompe "Riprendi" |
| `data/copilot/` | 1 KB | 2 ledger con squadre "asd", "23155": **prove di digitazione**, 2 acquisti e 0 | `fantaoracle_app.py:98,157` | **tenere** (costano nulla), non sono prove di aste vere |
| `data/tournament_fix/` | 10,7 MB | torneo di agosto | `viz/index.html:393` usa `replica_0125.jsonl` per il replay | **tenere** |
| `data/sample_logs/` | 347 KB | log dimostrativo | `viz/index.html:392` | **tenere** |
| `data/tournament/` | 9,9 MB | torneo 1ª generazione | `f3_run_tournament.py`, `realismo_aste.py` | **archiviare** |
| `data/tournament_mod/` | 10,7 MB | torneo con modificatore | `ind_analisi.py`, `realismo_aste.py` | **archiviare** |
| `data/counterfactuals/` | 5,4 MB | prove E1/E2 del REPORT_FINALE | `f5_counterfactuals.py` | **archiviare** |
| `data/indagine/` | 10,4 MB | 157 file: 40+ varianti `pred_valore_s4*`, log di stage intermedi | `f1_make_predictions.py` usa **solo** `tabpfn_cache/` (780 KB) | **da chiarire**: tenere cache e `backtest_valore_*.json`, archiviare il resto |
| `data/livello0/` | 1,2 MB | prove del Livello 0 e dei check | i tre script di check | **archiviare** |
| `data/smoke_bot_b/`, `data/smoke_tournament/` | 1,7 MB | output dei test smoke | **rigenerabili** da `tests/smoke_*.py` | **eliminabili** |
| `nul` | 12 KB | redirect Windows sbagliato | nessuna | **eliminabile** |
| `config/league.yaml` | 2 KB | promemoria regole | nessuno script lo legge | **tenere** come promemoria |

Correzioni ai miei errori precedenti: `data/livello0/http_test.log` pesa **887
byte**, non zero; i `live_logs` **non** sono aste reali; le date di modifica non
provano quando ne' da chi un file sia stato scritto, quindi ritiro l'ipotesi
sui report "toccati oggi".

---

## 6. Regole della lega: confermate, implementate, ipotizzate

| Regola | Stato |
|---|---|
| 10 squadre, 500 crediti, 3P/8D/8C/6A, 3 cambi | **confermata** da te, **implementata** in `rules.py` |
| porta inviolata +1, nessun bonus gol vittoria o pareggio | **confermata**, **implementata** |
| modificatore 6/6,25/6,5/6,75/7 → +1/+2/+3/+4/+5 | **confermata**, **implementata** |
| primo gol a 66, poi uno ogni 6 | **implementata** (`lineup.py:100`), **non riconfermata** di recente |
| spareggio: punti negli scontri diretti, poi punti totali | **implementata**, **mai confermata** |
| modificatore solo se restano almeno 4 difensori **con voto** dopo i cambi | **implementata**, **mai confermata** |
| sostituzione solo con un giocatore dello stesso ruolo | **implementata**, **mai confermata** |

Le ultime tre sono ipotesi del codice, non regole verificate con te.

---

## 7. Rerun dopo la correzione dell'anticipazione

Stessi seed, stesso tavolo, stessi pack: cambia solo il codice del simulatore.

| | prima | dopo |
|---|---|---|
| O3 2024/25: punti di B | 2919,9 | 2915,2 |
| O3 2024/25: vittorie | 99,3% | 99,2% |
| O3 2024/25: cassa finale | 73,9 cr | 73,9 cr |
| O3 2025/26: punti | 2875,3 | 2875,3 |
| O3 2025/26: cassa | 121,3 cr | 121,3 cr |
| f12 2026/27: P(1°) su scenari nuovi | 53,0% ± 5,0% | 53,0% ± 5,0% |
| f13 2024/25: punti / vittorie | 2972 / 96,7% | 2972 / 96,7% |
| f13 2025/26: punti / vittorie | 2946 / 69,3% | 2946 / 69,3% |

**Lettura.** L'effetto e' piccolo e nella direzione attesa: `simulate.py`
guardava avanti su **una giornata su 38**, e i punti scendono di 4,7 su 2920
(0,16%). Il residuo di cassa non si muove di un credito: conferma che
l'anticipazione e il budget non speso sono due problemi separati, come detto.
`detail.py` guardava avanti su tutte le giornate, ma alimenta solo la vista
mostrata dopo la Sedia: nessuna metrica di modello ne dipendeva.

I valori di f13 sono arrotondati all'intero nella stampa: differenze di pochi
punti non sono visibili li'.

**Il 99% resta un effetto soffitto**: contro questo tavolo B non puo' migliorare
e nessun confronto misura quanto valgano i crediti lasciati in cassa.

---

## 8. Istantanea creata

`data/istantanee/20260906_2102/` (3,1 MB): 125 file copiati, 335 impronte,
ambiente registrato. E' il riferimento con cui confrontare le versioni future
(`python scripts/f16_istantanea.py` senza argomenti dice cosa e' cambiato).
Non certifica gli esperimenti precedenti alla sua creazione.

---

## 9. Che cosa resta aperto

Per impatto sull'asta:

1. **Residuo di cassa**: 73,9 e 121,3 crediti, causa non identificata. Il
   meccanismo (13 target persi su 25, andati via per 237-282 crediti) descrive
   cosa succede, non perche': cap, ordine delle chiamate, valutazioni, vincoli
   e alternative disponibili possono contribuire tutti. Serve O3b, con disegno
   gia' corretto (margine pratico deciso prima, intervalli sul confronto
   appaiato, nessuna regola legata alla vittoria di B).
2. **Effetto soffitto**: serve un tavolo dove B non domini, con parita'
   informativa, prima di poter misurare qualunque miglioramento.
3. **Intervalli di prezzo**: copertura 68% nel 2024/25 (unica stagione con
   prezzi osservati). O4 resta aperto: nessun passaggio all'inviluppo.
   Ricordare che il q90 del prezzo non e' il massimo conveniente da offrire.
4. **Effetto squadra**: bersaglio misurato 25-29% della varianza contro lo
   0,25 di scarto nel codice, ma con una decomposizione diversa da quella che
   aveva prodotto il valore attuale. Da riconciliare prima di toccare.
5. **Snapshot 2026-27 posteriore al 1° settembre** (asimmetria addestramento
   e produzione).
6. **Panel**: universo atteso da imporre, 1-2 omonimi da sciogliere, stagione
   in corso senza partite.
7. **Regole non confermate**: spareggio, condizione del modificatore,
   sostituzione per ruolo.

---

## 10. O3b: diagnosi e confronto appaiato

### Perche' perde gli obiettivi

`scripts/indagine/o3b_diagnosi.py`, 3 aste, tavolo e seed del torneo, con
registrazione lotto per lotto del massimo che il bot si era dato:

| causa | casi | quota |
|---|---|---|
| battuto **sopra** il suo massimo | 32 | 86% |
| sotto il suo massimo, non ha rilanciato | 5 | 14% |
| reparto pieno, budget insufficiente | 0 | 0% |

Obiettivi presi: 41. Quando il prezzo supera il suo massimo, l'eccesso e' di
3 crediti in mediana, 8 in media, 18 al novantesimo percentile: quindi molti
obiettivi si perdono per pochissimo, alcuni per moltissimo (Dovbyk battuto 204
contro un massimo di 137).

Causa individuata: **il tetto**, non l'ordine delle chiamate, non i vincoli di
reparto, non il budget del momento.

**Perche' il tetto e' basso.** Il tetto dei titolari e' `q90 + 0.5 * prezzo
ombra`, e il q90 e' tarato sul prezzo MEDIO fra aste diverse. Ma in una singola
asta il prezzo varia: su 206 giocatori con almeno tre aste osservate, il prezzo
medio supera il q90 l'11,2% delle volte (vicino al 10% nominale), il singolo
martelletto il **16,9%**. La dispersione fra aste dello stesso giocatore ha
scarto pari al 48% della media.

### Confronto appaiato fra due politiche

`scripts/indagine/o3b_confronto.py`, 20 aste appaiate (stesso seme, stesso
tavolo, stesso pack), stagione 2024/25. Tavolo piu' informativo del torneo: due
seggi A+ e tre bot C che conoscono la lista prezzi. Trattamento: **solo** il
peso del prezzo-ombra, da 0,5 (attuale) a 1,0 (variante). Nient'altro cambia,
e in particolare non si offre di piu' "perche' si e' risparmiato".

Criteri fissati **prima** di guardare i risultati: la cassa media doveva
scendere di almeno 30 crediti (prezzo di un titolare di fascia media); le
vittorie non dovevano calare di piu' di 3 punti percentuali.

| misura | attuale | variante | differenza | IC95 appaiato |
|---|---|---|---|---|
| cassa lasciata | 67,7 | 66,4 | **-1,2** | [-13,2 , +9,2] |
| speso | 432,4 | 433,6 | +1,2 | [-9,2 , +13,2] |
| valore della rosa | 4896,6 | 4902,5 | +5,9 | [-29,5 , +42,4] |
| punti stagione | 2908,4 | 2907,6 | -0,8 | [-12,4 , +10,7] |
| vittorie | 99,6% | 99,6% | 0,0% | [-0,2% , +0,2%] |

**Verdetto: la variante non funziona.** La cassa scende di 1,2 crediti contro i
30 richiesti, e l'intervallo di confidenza sta interamente sopra la soglia: il
criterio non e' superato. Nessuna delle altre misure si muove oltre il rumore.
Rose complete 20 su 20 in entrambe le politiche.

**Il criterio sulle vittorie e' passato per un motivo che non vale.** Anche sul
tavolo informativo B vince il 99,6%: con un valore cosi' vicino al massimo, la
non inferiorita' e' garantita per costruzione e non dimostra niente. La metrica
che qui separa davvero e' quella dei punti, e neanche quella si muove.

**Il default resta 0,5**: `peso_ombra` e' stato aggiunto come parametro con
quel valore, il comportamento del bot e' identico a prima. La variante e'
riproducibile ma non adottata.

**Cosa si impara.** L'ipotesi "il tetto e' basso, alzarlo recupera obiettivi e
riduce la cassa" e' falsa cosi' com'e' formulata: alzando il tetto il bot
recupera qualche obiettivo ma lo paga di piu', e la cassa resta dov'e'. Le
strade non ancora provate: intervenire sul q90 (che e' tarato sul prezzo
sbagliato, quello medio invece del singolo martelletto), oppure sul finale
d'asta invece che sul tetto di ogni lotto. Nessuna delle due e' stata
implementata.

### Limite del banco, tuttora aperto

Nessun tavolo provato finora toglie l'effetto soffitto: B vince fra il 99% e il
100% sia contro il tavolo del torneo sia contro quello informativo, perche' il
suo vantaggio viene dal modello valore e nessun avversario disponibile lo usa.
Per misurare le politiche d'asta servirebbe un avversario che parta dalle stesse
stime, per esempio due seggi B nella stessa asta con politiche diverse. Non
implementato: cambia la natura del confronto e va deciso prima.

---

## 11. Pulizia eseguita

Spostati in `data/_cestino_20260906/`, **non cancellati**:

| Percorso | Dim | Perche' |
|---|---|---|
| `nul` | 16 KB | file nato da un reindirizzamento Windows sbagliato, nessun riferimento nel codice |
| `data/smoke_bot_b/` | 1008 KB | output del test `tests/smoke_bot_b.py`, che ricrea la cartella |
| `data/smoke_tournament/` | 744 KB | idem per `tests/smoke_tournament.py` |

Nulla che avesse dipendenze e' stato toccato: `data/live_logs/` e
`data/copilot/` restano perche' il menu li legge per la ripresa
(`fantaoracle_app.py:92,98,126,157,171`), `data/tournament_fix/` e
`data/sample_logs/` perche' `viz/index.html:392-393` li usa per il replay.
Verificato dopo lo spostamento: il pack si carica, l'app si importa.

Scritto `reports/INDICE.md`: stato di ogni report e artefatto (corrente,
superato, diagnostico, non riproducibile) e comando per rifare ogni misura.
