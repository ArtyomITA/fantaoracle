# Ragionamenti umani all'asta e in stagione — censimento e mappatura sul sistema

> Fonti: ~27 ricerche + ~32 pagine lette (SOS Fanta, Fantacalcio.it, FantaMaster, Sky, fantamagazine, pazzidifanta, wikifanta, consiglifantacalcio, Goal, Puntero, Superscudetto, forum GruppoEsperti, newsletter indipendenti). Ogni pattern → mappatura: **[C]** comportamento bot avversari · **[B]** feature/logica del nostro bot · **[R]** regola del modulo riparazione.

## PARTE 1 — Pre-asta e asta estiva

### 1. Infortunati di lunga degenza: sconto ~90%+
Il top ai box mesi diventa "slot morto": Ferguson (top di ruolo, crociato, rientro novembre) 3-6 crediti su 500; Schuurs 1. Chi lo compra lo parcheggia come ULTIMO slot con sostituto affidabile accanto. Se il rientro è imminente (Bremer) lo sconto quasi sparisce.
**[C]** malus infortunio sul valore privato: ×0.05-0.15 se lunga degenza, ×0.85 se rientro breve. **[B]** feature `infortunato_al_1_9` + `giornate_out_attese` (fonte storica: Transfermarkt injuries già nei dati); il modello valore già "vede" i minuti persi a posteriori, ma la feature esplicita separa sconto-mercato da valore vero → è dove nascono i bargain asimmetrici. **[R]** l'infortunato comprato a sconto è asset da ritorno: valore residuo = punti attesi solo ritorno.

### 2. Squalificati e Coppa d'Africa: sconto ~10-15%
CdA (dic-gen) = 3-7 giornate perse; guide: sconto ~10%, serve il vice. Squalifiche brevi quasi non prezzate; lunghe+cumulate = evitato (Okoye → 1-2 crediti).
**[C]** malus lieve sui convocati CdA. **[B]** feature `giornate_perse_attese` (squalifiche note + CdA se nazione qualificata). Compra il top CdA a sconto se il calendario del ritorno lo ripaga.

### 3. Declino per età — il pattern "Immobile" (raffinato)
La "tassa sulla fama" regge SOLO finché regge la titolarità percepita: Immobile 35enne da panchina → nessuno lo strapaga, parte la caccia al saldo nostalgico (1-5 crediti). Ma il top in parabola ANCORA titolare (Barella, De Bruyne 34) paga premio pieno da fama.
**[C]** profilo tifoso/nostalgico: premio fama solo se titolarità percepita alta; altrimenti sconto brutale. **[B]** interazione età×titolarità nel modello valore (già parzialmente in Qt.I/FVM); feature `delta_fantamedia_yoy` per catturare la parabola PRIMA del mercato — il caso Immobile 2024/25 (2 gol) è esattamente questo.

### 4. Recency bias: premio 30-50% sugli overperformer
"Non comprare la stagione scorsa": Posch 6 gol da difensore, Laurienté, Sanabria career-high → il tavolo li paga come garanzie. Le guide fissano tetti ("Orsolini max 220/1000"). Specchio: il flop dell'anno prima si prende a saldo (Martin a 1-2).
**[C]** già implicito nei prezzi reali di riferimento; aggiungere moltiplicatore breakout (+20-40%) nei profili aggressivi. **[B]** il CatBoost già regredisce verso la media (è il suo edge principale — le "gemme" 2024/25 erano proprio flop puniti troppo: Martin comprato a 1.5, 227 punti reali). Feature esplicita `overperformance_yoy` (gol vs xG, fantamedia vs storico) per raffinare.

### 5. Nuovi dall'estero: doppio binario
Nome esotico con highlights → asta feroce (nessuno sa prezzarlo); incognita adattamento → sconto sui non-nomi. Big da Premier saltano il filtro (De Bruyne = prezzo massimo a prescindere).
**[C]** varianza extra (sigma ×1.5) sui `nuovo_in_serie_a` + premio hype sui nomi con valore Transfermarkt alto. **[B]** già in casa: flag nuovo + valore TM + (futuro B2) valutazione Claude sul campionato di provenienza.

### 6. Nuovo allenatore/modulo: ±1-2 fasce
Soulé "tornado sotto Gasperini" prima di una partita; l'arrivo del concorrente crolla il prezzo (Neres dopo Lang).
**[B]** feature `cambio_allenatore` (flag squadra) + (B2 prospettico) giudizio Claude su fit tattico — qui il quantitativo puro è cieco, è il punto dove il tuo "rivalutato da te in un secondo momento" vale di più.

### 7. Rigoristi: salto di fascia
75-80% conversione = 4-6 bonus +3/anno. Premio liquido e noto; value hunt = il rigorista non ovvio della provinciale (Mina a 1 credito).
**[B]** feature `rigorista` (abbiamo rig_segnati storici; per la stagione target: liste rigoristi pre-asta). Alta priorità: churn di rigoristi in corso d'anno = rischio da prezzare.

### 8. Neopromosse: sconto sistematico + trappola del gioiello di B
Titolari veri a 1-3 crediti (miglior rapporto punti/prezzo per completare); MA "di 5 fenomeni di Serie B solo 1 conferma in A" — il gioiello mediatico (Tramoni) somma pattern 4+8 e viene strapagato.
**[C]** sconto flat neopromossa + eccezione hype sul top mediatico. **[B]** flag già presente (`squadra_neopromossa`); il modello impari da solo il tasso di conversione B→A (voti storici li abbiamo).

### 9. Coppe/turnover: quasi non prezzato sui top
Il mercato non sconta i top Champions; reale sui mezzi-giocatori da rotazione → coppia titolare+backup.
**[B]** feature `squadra_in_coppa` a costo zero; bassa priorità (segnale debole).

### 10. Ballottaggi: -80/90% vs titolare equivalente
"Il mercato odia l'incertezza più del rendimento mediocre" (Mazzocchi 2-8 crediti vs esterno titolare 10×). I modelli ammettono di non saper predire i ballottaggi d'agosto.
**[B]** è IL collo di bottiglia (letteratura + nostro mining concordano): modello titolarità dedicato = miglioramento n.1 in agenda. Feature `pct_titolarita_attesa` da probabili formazioni pre-asta (SOS Fanta la pubblica).

### 11. Portieri: top singolo vs accoppiata
Col modificatore (la vostra lega): "portiere della difesa forte" caposaldo. Budget porta 5-10%; coppie quantificate 2-9% per fascia.
**[B]** il MILP oggi tratta i 3 portieri come slot indipendenti; upgrade: vincolo/bonus "coppia stessa squadra" e valore portiere che include contributo al modificatore (voto medio alto). **[C]** profili con strategia porta differenziata.

### 12. Psicologia d'asta (già nei nostri profili C, da raffinare)
Ancoraggio (primo top sotto-pagato → nostro motore lo RIPRODUCE, verificato dal mining); alzatore con regola "solo giocatori che terresti"; sfruttare il tifoso (alzare sui giocatori della sua squadra); giocatore feticcio (pagato ogni anno, gli avversari lo tirano su apposta); panic (sforo max 1-2 crediti pianificato, 10 sui top); rilanci fuori scala +5/+15 per destabilizzare; pressione della necessità (chiamare mediocri quando un rivale deve riempire il reparto → sovrapprezzo forzato).
**[C]** aggiungere: feticcio per-bot (1-2 giocatori fissi ×1.5), pressione-necessità nell'enforcer, rilanci a salto già presenti. **[B]** la "pressione della necessità" è una tattica di nomination che B può usare: chiamare riempitivi quando i rivali hanno slot scoperti e crediti contati (endgame).

### Extra: norme collettive
Ripartizione budget = àncora sociale (P 5-10 / D 10-15 / C 25-30 / A 45-60): chi devia crea le distorsioni che gli altri arbitraggiano — B già devia scientemente (21.7% sulla difesa col modificatore). Attaccante zero-bonus = slot più odiato (crolla a 1 anche con xG buoni) → bargain sistematico per B se l'xG è vero.

## PARTE 2 — Stagione e riparazione

### R1. Svincolo del flop pagato caro (Immobile/Kean/Openda)
Conflitto sunk cost vs razionalità: svincolare il big da 100 = cristallizzare -50 (rimborso 50%). Soglia operativa delle guide: calo quotazione 25-35% → agire. "Un giocatore indietro nelle gerarchie 9 volte su 10 ci resta" vs "certi profili si riprendono nel ritorno" — la discriminante è: problema di GERARCHIE (svincola) vs problema di FORMA (tieni).
**[R]** policy svincoli B: MILP marginale con la regola gerarchie/forma (proxy: minuti a risultato acquisito = bocciatura). **[C-R]** i bot C svincolano col sunk cost bias: tengono i flop pagati cari più del razionale.

### R2. Crediti per gennaio: la vostra lega è testo da manuale
Guide: arrivare a gennaio col 5-10% del budget; quota extra consigliata ≤10% del budget estivo. Vostra lega: +50 su 500 = esattamente 10%; "quasi nessuno sopra 50 residui" = norma nazionale. Errore censito: crediti non spesi a fine riparazione = zero.
**[R]** config già coerente; i bot devono spendere ~tutto a gennaio.

### R3. Cosa si compra: gerarchia dei prezzi di riparazione
Il titolare emerso nell'andata si STRAPAGA (Vergara quotazione 2, FVM 23 = 11×; Palestra 17 vs 79): "feedback concreto" + tutti lo vogliono. I nuovi arrivi di gennaio = hype tax (meglio chi conosce già il campionato). Dosaggio: 2 acquisti mirati, non rivoluzione. Svincolati a 1 credito e "spacca-match" da subentro = dove si vincono le riparazioni.
**[R]** prezzi di riferimento riparazione ≠ estivi: moltiplicatore hype sugli emersi (misurabile: FVM gennaio / quotazione), sconto sugli invenduti. B ri-scora su giornate 1-19 → vede gli emersi PRIMA del prezzo? No: il prezzo di gennaio li sconta già (FVM aggiornato). L'edge di B a gennaio = stesso schema estivo: chi è emerso "per caso" (overperformance) vs chi ha segnale vero (xG, minuti).

### R4. Timing: vendere il big in calo prima del crollo
Quotazioni flop 2025/26: Openda 22→4, Kean 33→16. Chi aspetta recupera sempre meno. Scambi interni: piazzare il nome finché fa gola.
**[R]** (scambi fuori scope per ora — nella lega dell'utente esistono ma non li simuliamo; annotato come estensione).

### R5. La stagione plasma l'asta successiva
Memoria dei flop → prezzi d'apertura depressi l'anno dopo (già NEI nostri dati: è parte del perché il CatBoost trova gemme tra i puniti); fedeltà/effetto dotazione → il tifoso ricompra i suoi.
**[C]** memoria cross-stagione nei profili (feticcio = proxy). **[B]** niente da fare: il modello già arbitra questa distorsione.

### R6-R7. Scambi e errori di riparazione
Regole negoziali (mai essere il richiedente; l'infortunato rifilato prima che i tempi di recupero siano prezzati — molte leghe lo vietano). Errori: panic da classifica, strapagare hype, troppe scommesse ("a gennaio servono certezze"), svincolare troppo presto il top in ripresa, doppioni stessa squadra.
**[R]** catalogo comportamenti per i bot C alla riparazione.

### R8. Quanto incide la riparazione
Nessun dato rigoroso in letteratura; consenso tecnico: "correzione, non rivoluzione" — 2 colpi mirati, vittorie dai low cost azzeccati. Il nostro simulatore potrà QUANTIFICARLO per primo (torneo con/senza riparazione, flag già progettato).

## PARTE 3 — Priorità di implementazione

| # | Intervento | Dove | Impatto atteso | Costo |
|---|---|---|---|---|
| 1 | Modello titolarità (`pct_titolarita_attesa`) | B valore | ALTO — collo di bottiglia riconosciuto ovunque | medio |
| 2 | Feature `rigorista` | B valore | alto, dato quasi gratis | basso |
| 3 | Feature infortunio/squalifica/CdA alla data d'asta | B + C | medio-alto (bargain asimmetrici) | medio (dati TM già in casa) |
| 4 | Cap top price bot C (~0.36-0.40) + shift 3pp verso attacco | C realismo | alto per la fedeltà del torneo (fix del +25% sui top) | basso |
| 5 | `delta_fantamedia_yoy` + `overperformance_yoy` | B valore | medio (pattern Immobile/recency) | basso |
| 6 | Feticcio + pressione-necessità nei C; nomination endgame per B | C + B policy | medio | basso |
| 7 | Coppia portieri nel MILP + valore-modificatore | B | medio (col modificatore attivo) | medio |
| 8 | Riparazione completa coi comportamenti R1-R7 | modulo R | da quantificare (saremo i primi) | 1 giornata |
