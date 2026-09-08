# Indagine sul Livello 2 (cubo TABELLINO) — 7 settembre 2026

> ## RETTIFICHE del 7 settembre 2026 (sera) — LEGGERE PRIMA
>
> Controlli indipendenti hanno trovato quattro errori in questo documento. Le
> parti sbagliate sono segnate qui sotto e nel testo; il documento resta come
> era, con le correzioni accanto, perche' sparire non e' correggere.
>
> **R1. Il modello di partita provato non era quello descritto.**
> `scripts/indagine/l2_modello_partita2.py`, da cui vengono tutti i numeri
> della tabella del pezzo 1, **non contiene la correzione di Dixon e Coles**:
> stima un Poisson penalizzato. Il testo lo descriveva come Dixon-Coles.
>
> **R2. Il modello era mal specificato: mancava il livello generale dei gol.**
> Attacco e difesa erano vincolati a somma zero senza intercetta, il che
> costringe la media dei gol in trasferta vicino a 1. Misurato sui dati veri
> (train 2020-2023): gol in trasferta osservati **1,3132**, stimati **1,1202**,
> cioe' il 14,7% in meno. Con l'intercetta la stima e' esatta (1,3132).
> Inoltre la penalizzazione agiva solo sulle prime n-1 squadre, quindi il
> risultato dipendeva dall'ordine dell'elenco.
>
> **R3. La media riportata per il modello con decadimento e' sbagliata.**
> Il documento scrive 0,1996 per la riga E. La media vera della riga E e'
> **0,2083**. Lo 0,1996 si ottiene prendendo la riga D nel 2023 e la riga E nel
> 2024 e nel 2025, cioe' scegliendo il migliore stagione per stagione: non e'
> il risultato di una strategia fissata prima della prova. Medie corrette:
> B (media storica) 0,20287; C 0,21413; D 0,20047; E 0,20827; F 0,19443.
> Con i numeri giusti, **nessuna configurazione pre-asta batteva la media
> storica**: E era peggiore del 2,7%, D migliore dell'1,2%.
>
> **R4. La metrica non poteva vedere quello che si voleva misurare.**
> La correzione di Dixon e Coles **lascia intatte le marginali** (la somma dei
> quattro scostamenti e' zero per riga e per colonna). Quindi P(la squadra
> ospite non segna) e' identica con e senza correzione, e un Brier sulla porta
> inviolata da' **esattamente lo stesso numero** per i due modelli. Giudicare
> Dixon-Coles con quel Brier era impossibile per costruzione. Fissato in
> `tests/test_l2_partita.py::test_dixon_coles_preserva_marginali`.
>
> **R5. "Fuori campione" era troppo generoso.** Solo il pezzo 1 aveva una vera
> separazione fra addestramento e prova. Le regressioni del pezzo 2 sono
> stimate e valutate sulla stessa stagione: sono **descrittive**. Il pezzo 4 e'
> una scomposizione di varianza sugli stessi dati.
>
> **R6. Numeri esterni ritirati.** "49,3% di accuratezza contro un intervallo
> competitivo del 52-58%" e "batte il Poisson semplice solo nel 40% dei casi"
> non sono confrontabili con questo problema (campionato, periodo,
> informazione, metrica e protocollo diversi) e vengono ritirati.
>
> **R7. Sullo shock di squadra.** Il documento diceva che uno shock unico
> "rende uguali" le correlazioni fra ruoli. Non e' esatto: uno shock condiviso
> introduce una componente comune di covarianza, ma la correlazione dipende
> anche dalle varianze individuali, che sono diverse per ruolo. La misura
> resta valida (il vecchio simulatore produce correlazioni fra 0,10 e 0,16 per
> tutte le coppie di ruoli contro 0,12-0,34 vere), la spiegazione no.
>
> **Che cosa cambia il verdetto.** Rifatto il modello di partita con
> l'intercetta, la penalizzazione simmetrica, la vera correzione di Dixon e
> Coles, il decadimento sul tempo reale e gli iperparametri scelti sulla
> stagione precedente, il modello **batte la media storica in tutte e tre le
> stagioni di prova**, con intervalli che escludono lo zero. Il verdetto
> "guadagno pre-asta dell'1-2%, non conviene prima dell'asta" **e' rovesciato**.
> Numeri e codice in [LIVELLO2.md](LIVELLO2.md) e
> `scripts/l2_banco_partita.py`.


Stesso metodo dell'indagine sui punti aperti: ogni pezzo della proposta viene
stimato davvero sui dati, fuori campione, e confrontato con le alternative
povere che dovrebbe battere. Dove esiste una fonte esterna, e' citata.
**Il Livello 2 non e' stato implementato**: qui si misura solo se reggerebbe.

La proposta (in `reports/ARCHITETTURE_2.0.md`, sezione A) prevede: simulare il
risultato della partita, poi chi gioca e quanti minuti, poi dividere i gol fra
i giocatori in campo, poi assegnare il voto puro dato il tabellino. Da quel
"cubo" di stagioni simulate dovrebbero uscire valore, incertezza, correlazioni
e tetti d'asta.

---

## Pezzo 1 — Il modello di partita: non regge nella versione pre-asta

`scripts/indagine/l2_modello_partita2.py`. Modello stimato per intero (forze di
attacco e difesa per squadra, vantaggio del campo, correzione sui punteggi
bassi), fuori campione, e messo contro le due alternative povere che deve
battere. Metrica: errore quadratico medio sulla probabilita' di porta inviolata
(quella che serve al modificatore e ai portieri).

| | test 2023 | test 2024 | test 2025 |
|---|---|---|---|
| A. stessa probabilita' per tutti | 0,2031 | 0,2020 | 0,2229 |
| B. media storica della squadra | **0,1956** | 0,1958 | 0,2172 |
| C. modello, 3 stagioni | 0,2313 | 0,2018 | 0,2093 |
| D. modello, 1 stagione | 0,1994 | 0,1941 | 0,2079 |
| E. modello con decadimento | 0,2252 | **0,1932** | **0,2064** |

> **Rettifica R1-R3**: le righe C, D, E vengono da un Poisson penalizzato senza
> intercetta, non da Dixon-Coles; la media della riga E e' 0,2083, non 0,1996.

| F. modello aggiornato in stagione | 0,1877 | 0,1894 | 0,2062 |

**Nella configurazione che conta per l'asta** (righe C, D, E: si sa solo quello
che e' successo prima), il modello batte la media storica in due stagioni su
tre e nel 2023 perde. Media sulle tre stagioni: 0,2029 per la media storica,
~~0,1996~~ **0,2083** per il modello con decadimento. ~~Guadagno dell'1,6%~~
**perdita del 2,7%** (vedi rettifica R3).

**Il gate dichiarato nella proposta era "sotto 0,19 contro 0,205 del tasso
base".** Non e' raggiunto in nessuna configurazione pre-asta. Lo si raggiunge
solo con la riga F, che usa le giornate gia' giocate: informazione che
all'asta non c'e', utile semmai al copilota e alla riparazione di gennaio.

**Fonte esterna, coerente.** I limiti misurati sono quelli noti del metodo: le
forze di attacco e difesa sono trattate come costanti mentre non lo sono, e il
decadimento temporale aiuta solo entro un certo peso, oltre il quale peggiora
([dashee87](https://dashee87.github.io/football/python/predicting-football-results-with-statistical-modelling-dixon-coles-and-time-weighting/),
[opisthokonta](https://opisthokonta.net/?cat=48)). In test recenti il modello
puro arriva al 49,3% di accuratezza contro un intervallo competitivo del
52-58%, e in confronti diretti batte il Poisson semplice solo nel 40% circa
delle partite quando si guardano le probabilita' di gol
([penaltyblog](https://pena.lt/y/2021/06/24/predicting-football-results-using-python-and-dixon-and-coles/),
[modelli calibrati sul mercato](https://arxiv.org/pdf/1802.08848)).

**Verdetto sul pezzo 1: il guadagno pre-asta e' dell'ordine dell'1-2% e non
supera il gate che la proposta si era data.** Il valore vero e' in stagione.

---

## Pezzo 2 — Il voto dato il tabellino: funziona, ma meno di quanto dichiarato

Regressione del voto puro (al netto della media individuale del giocatore) sugli
eventi della partita, tre stagioni, ~10.700 righe ciascuna.

| | 2023-24 | 2024-25 | 2025-26 | dichiarato nella proposta |
|---|---|---|---|---|
| 1 gol | +0,83 | +0,84 | +0,86 | +0,88 / +1,01 |
| 2 o piu' gol | +1,39 | +1,43 | +1,43 | +1,5 / +1,9 |
| assist | +0,46 | +0,44 | +0,45 | +0,5 / +0,6 |
| differenza reti | +0,095 | +0,099 | +0,114 | non dichiarato |
| portiere, porta inviolata | +0,14 | +0,06 | +0,10 | +0,16 |
| portiere, 3+ gol subiti | **+0,07** | **+0,08** | **+0,05** | **-0,29** |
| varianza del voto spiegata | 40,1% | 38,9% | 41,8% | non dichiarata |
| scarto residuo | 0,426 | 0,439 | 0,432 | 0,45 |

I coefficienti principali sono confermati e stabili fra stagioni, leggermente
piu' bassi di quelli dichiarati. **Una discordanza vera**: il coefficiente per
il portiere che subisce tre o piu' gol risulta positivo e piccolo, mentre la
proposta lo dava a -0,29. Nel mio modello c'e' anche la differenza reti, che
assorbe quell'effetto: e' un problema di specificazione, non un errore di
qualcuno, ma significa che i due numeri non sono confrontabili e che il
coefficiente citato non e' utilizzabile cosi' com'e'.

**La prova che conta davvero** e' quanta correlazione fra compagni resta dopo
aver condizionato al tabellino: e' questo il motivo per cui il Livello 2
esiste.

| | prima | dopo il tabellino |
|---|---|---|
| portiere-difensori (2023-24) | 0,221 | 0,071 |
| portiere-difensori (2024-25) | 0,165 | 0,027 |
| portiere-difensori (2025-26) | 0,225 | 0,094 |
| fra difensori (2023-24) | 0,308 | 0,183 |
| fra difensori (2024-25) | 0,301 | 0,185 |
| fra difensori (2025-26) | 0,372 | 0,236 |

**Sul modificatore il tabellino funziona**: la correlazione fra portiere e
difensori quasi sparisce, come la proposta sosteneva. **Fra difensori no**:
resta fra 0,18 e 0,24, mentre la proposta dichiarava 0,134. Quindi il cubo non
eliminerebbe la necessita' di uno shock di squadra residuo: lo ridurrebbe di
circa il 40%, non lo sostituirebbe.

---

## Pezzo 3 — La ripartizione dei gol: non dimostrata

La proposta divide i gol della squadra fra i giocatori in campo con pesi
proporzionali a minuti per un tasso individuale, il cui prior verrebbe da
TabPFN e sarebbe aggiornato coi gol storici.

Test sulla stagione 2024/25 (936 gol in 760 squadre-giornata, il 28,8% delle
quali senza gol): quanto bene il tasso storico ordina chi segna, dentro la
stessa partita?

| ordinatore | correlazione media dentro la partita |
|---|---|
| tasso storico per giocatore (con contrazione) | 0,240 |
| **solo il ruolo** (attaccante, centrocampista, difensore) | **0,273** |

**Il tasso individuale non aggiunge nulla al ruolo, anzi fa un po' peggio.**
Il tasso e' disponibile solo per il 69,6% delle righe (chi ha giocato l'anno
prima). Non e' una bocciatura definitiva, perche' il modello vero userebbe
minuti effettivi e un prior migliore, ma il pezzo non ha oggi una prova a
favore, e la proposta ne dava per scontata l'utilita'.

**Rischio gia' segnalato dai giudici e confermato qui**: il prior verrebbe da
covariate che includono i gol delle stagioni precedenti, e poi verrebbe
aggiornato con gli stessi gol. Contarli due volte stringe la distribuzione
oltre il dovuto.

---

## Pezzo 4 — Quanto margine c'e': meno di quanto sembra

La proposta dice che il simulatore attuale ignora il legame fra voto e bonus.
Verificato sui dati 2024/25: la varianza del fantavoto (2,299) si scompone in
voto (0,362), bonus (1,229) e due volte la covarianza (0,708). La covarianza
vale il **30,8%** del totale, con correlazione fra voto e bonus di 0,530: e'
molta.

Ma il simulatore attuale pesca **coppie reali appaiate** (voto e fantavoto
della stessa giornata dello stesso giocatore), quindi quella covarianza e' gia'
dentro per costruzione. Su questo i giudici avevano gia' corretto la proposta,
e la verifica lo conferma: non e' li' il guadagno.

Quello che il simulatore attuale davvero non fa: distinguere la correlazione
fra portiere e difensori (0,17-0,23 nei dati) da quella fra difensori
(0,30-0,37). Lo shock di squadra unico le rende uguali. Il cubo le
distinguerebbe. E' un guadagno reale ma circoscritto al modificatore.

---

## Pezzo 5 — Dati mancanti

| serve | stato |
|---|---|
| voti con tutte le componenti, 5 stagioni | presente, riconciliato al 100% (Livello 1) |
| minuti per partita | presente per 2019-2025 (Transfermarkt) |
| risultato, avversario, calendario storico | presente (`games.csv.gz`, fino alla stagione 2025) |
| forza difensiva da xGA per squadra | presente (Understat, aggregati di stagione) |
| **formazioni titolari** (`game_lineups`) | **assente** |
| **calendario 2026/27** | **assente** |
| **xG per partita** (non aggregato di stagione) | **assente** |
| minuti in Serie B o all'estero per i nuovi | assente, come gia' noto |

Il calendario della stagione in corso e le formazioni titolari sono scaricabili.
L'xG per partita richiede lo scraping per giocatore di Understat, che e' la
parte lunga gia' segnalata nei report precedenti.

Da notare: senza il calendario 2026/27 il cubo **non puo' girare sulla stagione
in corso**, che e' l'unico posto dove servirebbe per l'asta.

---

## Verdetto complessivo

| pezzo | esito della verifica |
|---|---|
| modello di partita | guadagno pre-asta 1-2%, gate dichiarato non raggiunto; funziona bene solo aggiornandolo in stagione |
| voto dato il tabellino | coefficienti confermati; toglie la correlazione portiere-difensori, ne lascia il 60% fra difensori; un coefficiente dichiarato ha segno opposto |
| ripartizione dei gol | nessuna prova a favore: il tasso individuale non batte il solo ruolo |
| margine rispetto a oggi | la covarianza voto-bonus e' gia' catturata; resta il solo guadagno sulle correlazioni per ruolo |
| dati | mancano formazioni titolari, calendario della stagione in corso e xG per partita |
| costo dichiarato | 12-16 settimane-persona (stima dei giudici, non verificabile qui) |

**Lettura.** Il Livello 2 non e' sbagliato: e' un'architettura coerente e ogni
suo pezzo e' verificabile. Ma le prove raccolte spostano il bilancio. Il pezzo
centrale rende poco prima dell'asta e molto durante la stagione; il pezzo che
funziona meglio (voto dato il tabellino) risolve solo una delle due
correlazioni; il pezzo sulla ripartizione dei gol non ha oggi una prova; e il
guadagno che la proposta rivendicava sulla covarianza voto-bonus non esiste
perche' quel legame e' gia' catturato.

**Dove il Livello 2 conviene davvero**, sulla base di queste misure: non come
sostituto del simulatore pre-asta, ma come motore **in stagione** — copilota
dopo le prime giornate, riparazione di gennaio, decisioni di scambio. E' li'
che il modello di partita aggiornato batte tutto il resto (0,188-0,206 contro
0,196-0,217 della media storica) e che il calendario serve davvero.

**Non e' stata scritta una riga del Livello 2.** Le tre misure che
cambierebbero il verdetto, se qualcuno volesse ribaltarlo: un modello di
partita con prior informativo che batta la media storica **anche** pre-asta e
su tutte e tre le stagioni; una ripartizione dei gol che batta il solo ruolo;
una stima di quanto la correlazione residua fra difensori pesi su P(1° posto).
