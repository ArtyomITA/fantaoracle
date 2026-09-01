# Guida rapida — usare FantaOracle all'asta vera

Stagione 2026/27. Questa guida spiega cosa fare **prima**, **durante** e **dopo** l'asta con i tuoi amici. Tutto si fa dal menu (`FantaOracle.bat` oppure `python scripts/fantaoracle_app.py` e poi `http://localhost:8899/viz/index.html`).

## Prima dell'asta (anche il giorno stesso, ci vogliono 5 minuti)

1. Dal menu premi **🔄 Aggiorna mercato**. Il programma scarica da solo: listone e quotazioni ufficiali, prezzi medi delle aste già fatte quest'anno, probabili formazioni con percentuali di titolarità, infortunati e squalificati con data di rientro, rigoristi, voti delle giornate già giocate, xG. Poi riallena le predizioni e ricostruisce il pack 2026/27. Il log scorre nella card; alla fine compare "tutto ok" con l'ora dell'ultimo aggiornamento.
2. Ogni copia scaricata viene datata e conservata in `data/snapshots/AAAAMMGG/`: se un sito cambia o sparisce, i dati restano.
3. Se vuoi allenarti: card **Sedia** → AVVIA → giochi contro 9 bot con i dati aggiornati. È lo stesso oracolo che userai all'asta vera, ma senza amici.

## Durante l'asta vera (card **🏟️ ASTA VERA — Copilota**)

1. **AVVIA** → si apre il tavolo. Inserisci il numero di partecipanti e i **nomi dei tuoi amici**, scegli quale sei tu, conferma il budget (500).
2. Quando un giocatore sale al banco: cercalo nel campo di ricerca (nome, ruolo o squadra), selezionalo, e aggiorna il prezzo man mano che salgono i rilanci (+1, +5 o scrivi la cifra). Il **CONSIGLIO** grande cambia colore:
   - **verde "rilancia fino a X"**: è nel tuo piano, spingiti fino a X;
   - **giallo "bargain"**: non era in piano ma a questo prezzo vale prenderlo;
   - **rosso "lascialo"**: sopra il tuo massimo o fuori piano — lascia che paghino gli altri.
   Accanto vedi la forchetta di prezzo attesa (q10-q50-q90), il valore atteso in punti e i **motivi di mercato** (infortunio, titolarità, prezzo reale nelle altre leghe).
3. Quando il martelletto cade: premi il nome di **chi l'ha comprato** e la cifra → il tavolo si aggiorna (budget, rose, offerta massima legale di ognuno) e il piano viene ricalcolato. Se sbagli: **UNDO**.
4. Al tuo turno di chiamata: pannello **"Chi chiamo?"** per ruolo → l'oracolo propone un'**esca** (un big che non vuoi, per drenare i budget altrui) oppure un tuo riempitivo economico.
5. Il pannello **IL MIO PIANO** mostra la rosa target aggiornata: titolari, prezzi attesi, massimo consigliato per ciascuno, costo totale del piano contro il tuo budget, e il termometro del mercato (sopra 1 = il tavolo sta pagando più delle stime).
6. **Salvataggio**: ogni acquisto è scritto subito su disco (`data/copilot/ledger_*.json`). Se il PC si spegne, chiudi il browser o cade tutto: riapri il menu → **RIPRENDI l'ultima asta vera** e sei di nuovo al punto esatto.

## Consigli d'uso (dall'analisi di 216 aste reali e dai tornei simulati)

- La forza dell'oracolo è il **modello valore**: sceglie titolari veri che il mercato sottovaluta. Fidati dei "bargain" gialli, sono il suo pane.
- Non superare il massimo consigliato sui **panchinari**: sono quasi sempre sostituibili alla pari. Sui **titolari di piano** il massimo include già il "prezzo-ombra" (quanto perdi ripiegando sull'alternativa).
- **Mai price enforcing** (alzare per far pagare gli altri) su un ruolo dove hai ancora slot scoperti.
- Chiudi l'asta con **pochi crediti residui**: i crediti non spesi valgono zero (la lega aggiunge 50 crediti a gennaio per la riparazione).
- Il modificatore difesa è attivo nella tua lega: il piano lo sa e spinge sulla difesa più delle guide classiche.

## Dopo l'asta

- Nella modalità Sedia, a fine asta, puoi guardare la stagione simulata coi voti (funziona per le stagioni passate; per il 2026/27 arriverà giornata per giornata man mano che i voti escono e rilanci "Aggiorna mercato").
- Riparazione di gennaio: modulo progettato (PIANO.md §11-bis), da attivare quando serve.
