# Copilota d'asta — guida rapida

Asta del 10 settembre 2026, 19:30. Dieci partecipanti, 500 crediti, rosa
3 portieri, 8 difensori, 8 centrocampisti, 6 attaccanti.

## Avviare

Doppio click su `FantaOracle.bat`: apre il menu su http://localhost:8899.
Nel riquadro **ASTA VERA — Copilota** lascia la porta a **8770**, scegli
`2026-27` e premi **AVVIA l'asta vera**. (Il campo porta del menu non viene
sempre letto all'avvio: con 8770 non serve toccarlo.)

A mano, se preferisci:

```bash
python scripts/f10_copilot.py 2026-27 --porta 8770
```

poi apri http://localhost:8899/viz/copilot.html?live=http://localhost:8770.

All'avvio il terminale scrive le righe da leggere:

```
  eleggibilita': 63 fuori Serie A esclusi dai consigli, pool 531 (fonti del 2026-09-09)
Copilota 2026-27 su http://localhost:8770 — ledger data\copilot\ledger_<numero>.json
```

Se dice **«nessun filtro di eleggibilità»**, fermati e rigenera con
`python scripts/f4_eleggibilita.py`. Se dice **«porta 8770 non disponibile»**
c'è già un Copilota acceso: usa quello, o chiudilo dal task manager
(`python.exe` con `f10_copilot.py`) e riavvia.

**Segnati il nome del ledger**: serve per riprendere.

## Prima dell'asta: il listino di carta

`data/copilot/listino_offline_2026-27.html` è una pagina da stampare o
tenere sul telefono: per ruolo, i giocatori in ordine di valore con mediana,
tetto a tavolo vuoto, prezzo di mercato, stato sportivo e nota dell'esperto.
Se il computer muore a metà asta, si va avanti con quella. Si rigenera con
`python scripts/f14_listino_offline.py 2026-27`.

## Apparecchiare il tavolo

Alla prima apertura inserisci i nomi veri dei dieci partecipanti, quale sei tu
e il budget. Il server rifiuta configurazioni impossibili — nomi ripetuti,
indice inesistente, budget sotto il minimo — e in quel caso **non salva
niente**: correggi e rimanda. Ad asta iniziata il tavolo non si può
riconfigurare con un budget che non copra gli acquisti già registrati.

## Durante l'asta

1. **cerca** il giocatore chiamato (tasto `/`; gli accenti non servono:
   «calo» trova Calò). Con più omonimi il primo Invio evidenzia, il secondo
   conferma, le frecce cambiano scelta;
2. leggi il consiglio: **verde** rilancia fino a N, **rosso** lascialo,
   **giallo** fuori piano ma entro N, **grigio** non offrire. Verde con
   «DEVI PRENDERLO» vuol dire che i comprabili del ruolo bastano appena per i
   tuoi slot: si sale fino al massimo legale;
3. metti il prezzo battuto e premi il pulsante della squadra che se l'è preso.
   La griglia del martelletto sta subito sotto il consiglio, senza scorrere.

Il numero grande è il **massimo consigliato**, già ridotto al massimo legale
(un credito per ogni slot che ti resta). Sopra quel numero il Copilota dice di
lasciarlo, e ha alternative pronte.

Nella scheda del giocatore compaiono anche:

- **INDISPONIBILE** con il testo della fonte: resta comprabile, ma il valore
  con cui il modello lo pesa tiene già conto delle giornate che perderà;
- **mercato 10 sq./500**: prezzo medio nelle leghe come la tua, riferimento
  di mercato, non un tetto;
- **l'esperto (4/9)**: opinione di un esperto (video Carmi Special del 3-4
  settembre), non un dato del modello. Serve a leggere il consiglio con
  un'informazione in più;
- **possono superarti: N (nomi)**: quanti avversari hanno ancora uno slot
  libero in quel ruolo e cassa legale sopra il tuo tetto. È un'informazione,
  non cambia il tetto: se sono in tanti, non contare di prenderlo al tetto;
  lo stesso numero sta in piccolo accanto a ogni target della ROSA TARGET;
- **non lo voglio nel piano**: se non sei d'accordo col modello su un nome
  (per esempio Colombo, che l'esperto giudica «copertura, non da
  fantacalcio»), lo togli dal piano con un click. Il piano si ricalcola,
  il giocatore resta registrabile se lo compra un altro, e lo riammetti
  quando vuoi. Gli esclusi sono elencati nel riquadro «DATI DI QUESTA
  SESSIONE» e restano salvati nel ledger.

Se registri per sbaglio, `U` annulla l'ultimo acquisto (primo tocco arma,
secondo conferma; col mouse due click sul pulsante ANNULLA). Premerlo due
volte di fila non toglie due acquisti.

Se un avversario compra un giocatore che la ricerca non mostra (fuori lista
secondo il listone, o escluso da te), spunta **«anche fuori lista ed
esclusi»**: compare e si registra.

## Rigoristi

Il pannello **RIGORISTI** (sotto i piani) elenca per ogni squadra di Serie A i
tre rigoristi nell'ordine della fonte (fantacalcio.it, 10/9 ore 17): il primo
ancora comprabile è in verde, i venduti sono barrati con chi li ha presi, i
tuoi in giallo, gli indisponibili in grigio. Si aggiorna a ogni martelletto;
un click sul nome lo porta al banco. Attenzione: Sky (3/9) dà gerarchie
diverse per Atalanta (Kessié), Fiorentina (Beto) e Udinese (Davis).

## Collegamento automatico a FantaAsta Live (il ponte)

FantaAsta Live tiene le assegnazioni nel browser; un piccolo script («ponte»)
che gira nella scheda di FantaAsta le manda al Copilota ogni 1,5 secondi, e la
pagina del Copilota si aggiorna da sola. Provato su un'asta a 10 squadre:
43 assegnazioni su 44 identiche (giocatore, squadra, prezzo), ritardo medio
0,6 s, nessun doppione dopo un ricaricamento.

1. Copilota avviato dal menu (porta 8770) e setup con **gli stessi nomi** delle
   squadre di FantaAsta, nello stesso ordine.
2. Apri http://localhost:8899/viz/ponte.html, premi «prova connessione» (deve
   elencare i 10 nomi) e trascina il link **PONTE FantaAsta** nei preferiti.
3. Nella scheda di FantaAsta clicca il preferito. Alternativa: F12 → Console →
   incolla `viz/ponte_fantaasta.js`.
4. Chrome chiede «consentire l'accesso alla rete locale»: **Consenti**. Se non
   chiede e il riquadro dice ERRORE: `chrome://flags/#local-network-access-check`
   → Disabled, riavvia Chrome, riclicca il preferito.
5. In basso a destra su FantaAsta compare «PONTE: N assegnazioni inviate ·
   ultimo giro · OK»: il numero sale a ogni martelletto.
6. Se ricarichi FantaAsta, riclicca il preferito: gli inviati sono ricordati.
7. Se annulli un'assegnazione in FantaAsta: se è l'ultima il ponte la annulla
   anche nel Copilota; se non lo è, il riquadro va in ERRORE, annulli a mano nel
   Copilota e in console `window.PONTE.sblocca(<indice>)`. Un giocatore fuori
   dal pack (raro) va registrato a mano.
8. Una sola scheda di FantaAsta aperta. Comandi: `window.PONTE.stato()`,
   `window.PONTE.ferma()`, `window.PONTE.rimappa()`.

Il ponte manda solo le aggiudicazioni, non i rilanci. Se il ponte non parte,
resta la via manuale sotto.

## Registrare dal terminale (o da uno screenshot)

Se qualcuno ti passa gli acquisti a voce o con una foto, si registrano in
blocco senza toccare la pagina, che si aggiorna da sola entro due secondi:

```bash
python scripts/asta_registra.py "Malen > Marco : 205" "calo > io : 12"
```

Nomi senza accenti e parziali; un nome ambiguo non viene registrato e ti
mostra i candidati. `--undo`, `--escludi Nome`, `--riammetti Nome`, `--stato`.

## Piani con bomber diversi

Il pannello **PIANI CON BOMBER DIVERSI**, pulsante «calcola», mostra come
cambia tutta la rosa se prendi un attaccante invece di un altro: costo, spesa
per reparto, chi entra e chi esce. Il piano di riferimento è **lo stesso** su
cui il banco calcola i tetti (stessi vincoli, compresa la quota di spesa in
attacco). Sul pack di stasera: riferimento con Malen, alternative Ramos G.,
Laurienté, Martinez L., Hojlund a meno dell'1,1 % di scarto.

Il numero accanto a ogni scheda è il **punteggio del modello**, non una
probabilità di vittoria. Scorrere fra le schede non registra niente e non
autorizza a rilanciare oltre il tetto.

Il campo «se lo compro a …» ricalcola il completamento a un prezzo che decidi
tu, senza toccare il registro. Dopo ogni martelletto, annullamento o
esclusione i piani vanno **ricalcolati**: la scheda te lo dice.

## Riprendere dopo un riavvio

Dal menu: **RIPRENDI l'ultima asta vera** (riapre il ledger salvato più di
recente). A mano:

```bash
python scripts/f10_copilot.py 2026-27 --porta 8770 --resume data/copilot/ledger_<numero>.json
```

Rose, budget, disponibilità ed esclusioni vengono ricostruiti dagli acquisti
registrati: il risultato è identico a prima dello spegnimento (provato).

Se il file fosse danneggiato, il Copilota riparte dall'**ultima copia buona**
(`ledger_<numero>.buono.json`) e la pagina lo dice con un banner giallo: in
quel caso controlla che l'ultimo acquisto ci sia. Se non c'è niente di
leggibile si ferma invece di ripartire da uno stato inventato. Un ledger già
aperto da un altro Copilota vivo viene rifiutato (file `.lock` con il PID).

## Salvare una copia

Il pulsante **esporta**, nel riquadro «DATI DI QUESTA SESSIONE», scarica un
JSON con acquisti, rose, budget, esclusioni e il listino completo con prezzi
di riferimento, indisponibilità e chi è fuori Serie A. Si legge senza rete e
senza il server. Conviene esportare una volta a metà asta e una alla fine.

## Se qualcosa va storto

| succede | che fare |
|---|---|
| «Copilota non raggiungibile» | il server si è chiuso: dal menu RIPRENDI, o a mano con `--resume`. Gli acquisti registrati sono già su disco |
| «porta 8770 non disponibile» all'avvio | c'è già un Copilota acceso (anche orfano di un menu chiuso): riusalo, oppure chiudi `python.exe f10_copilot.py` dal task manager |
| l'acquisto è registrato ma il consiglio non si aggiorna | previsto: il registro ha la precedenza, il consiglio torna al martelletto successivo |
| il prezzo viene rifiutato | crediti interi, almeno 1, entro il massimo legale: il messaggio dice quale |
| il pannello piani dice «superato» | è arrivato un acquisto durante il calcolo: premi di nuovo «calcola» |
| ho chiuso tutto per sbaglio | RIPRENDI dal menu: si riparte dall'ultimo acquisto |

## Che dati sta usando

- **pack** `pack_2026-27.pkl` rigenerato il **10 settembre alle 06:21** con i
  voti delle prime **tre** giornate (K = 3) e riaggiornato alle **17:35** con
  probabili, indisponibili (56: entrati Cambiaso, Basic, Havel; uscito Gabbia),
  rigoristi e prezzi live scaricati alle 17:00: 594 giocatori, impronta
  `2303dcbf9de8`;
- **obiettivo del piano** (lam 0,5, quota attacco 35-50 %, 3-4-3): ricalcolato
  alle 07:20 con f12 su 100 simulazioni sul pack nuovo — stessa scelta del 6/9,
  P(1°) 56 % in scelta e 57 % ± 5 in verifica contro archetipi (numero
  interno del modello, non una promessa);
- **eleggibilità, indisponibili, prezzi di mercato**: bundle del 9 settembre
  22:35 UTC; gli indisponibili del 10/9 sono gli stessi 54;
- **pool acquistabile**: 531 (tutti gli attivi del listone hanno una previsione);
- la **mediana di prezzo** del pack è già una miscela: 60 % prezzo live
  osservato + 40 % modello. Il «mercato 10 sq./500» in scheda viene dal bundle
  del 9/9 (379 giocatori): non è un secondo parere indipendente, è lo stesso
  mercato aggregato in modo diverso;
- gli infortuni entrano nel valore atteso dentro il pack (giornate perse
  stimate dal testo della fonte). Il Copilota li ridurrebbe una seconda volta
  solo se il pack fosse più vecchio delle fonti: oggi non lo è, e lo dichiara.

**Da guardare con occhio critico.** Il modello mette in piano Raimondo
(Frosinone) come titolare e Colombo (Genoa) come secondo attaccante: valori
alti spinti dalle prime tre giornate; l'esperto non è d'accordo su Colombo.
Vlasic e Zaccagni sono giudicati «discontinui». Se condividi il dubbio, usa
«non lo voglio nel piano»: il piano si adatta.

## Tornare alla versione precedente

Il codice di prima delle correzioni della notte è in
`data/_backup_fable_20260910/` (`f10_copilot.py`, `piani.py`,
`fantaoracle_app.py`, `copilot.html`, `f4_eleggibilita.py`, `packs/`,
`processed/`), con le impronte in `IMPRONTE.json`. Il pack del 6 settembre è
`data/_backup_fable_20260910/packs/pack_2026-27.pkl`. Per tornare indietro
copia i file al loro posto; i quattro file di codice vanno ripristinati
insieme.
