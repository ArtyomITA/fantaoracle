# Indagine sui sei punti aperti — 7 settembre 2026

Ogni punto con: che cosa si sapeva, che cosa dice la prova, che cosa resta da
decidere. Le fonti esterne sono citate per esteso. Nessuna modifica al modello
e' stata applicata in questa indagine: dove emerge un candidato a correzione,
e' scritto e basta.

---

## 1 e 3 insieme — il residuo di cassa e gli intervalli di prezzo sono lo stesso problema

Erano due voci separate. La prova dice che sono la stessa cosa vista da due
lati.

**Che cosa si sapeva.** Il bot lascia 74-121 crediti in cassa. L'86% degli
obiettivi persi viene battuto sopra il suo tetto. Alzare il peso del
prezzo-ombra da 0,5 a 1,0 non serve a niente (O3b: cassa -1,2 crediti, contro i
-30 richiesti).

**La prova nuova.** Il tetto dei titolari parte dal q90, e il q90 e'
calibrato sul prezzo **medio** fra aste diverse. Ma in asta si paga il prezzo
di **quella** asta. Misurato sui 1.141 acquisti reali di periodo estivo della
stagione 2024/25 (303 giocatori, 5 aste):

| bersaglio | copertura dell'intervallo q10-q90 |
|---|---|
| prezzo medio fra aste (quello su cui il modello e' calibrato) | 67,5% |
| **prezzo della singola asta** (quello che si paga davvero) | **53,2%** |

Del singolo prezzo, il 31,9% cade sotto il q10 e il 14,9% sopra il q90. Quindi
un tetto fissato al q90 viene superato circa una volta su sette, e su un
listone di 25 obiettivi significa perderne parecchi.

Quanto manca all'intervallo per coprire il singolo prezzo:

| allargamento (volte la dispersione fra aste) | copertura |
|---|---|
| 0 (oggi) | 53,2% |
| 0,25 | 63,8% |
| 0,50 | 72,6% |
| 0,75 | 78,4% |
| **1,00** | **82,8%** |

La dispersione del prezzo fra aste dello stesso giocatore e' gia' nel pack
(`ref_price_sd`), non va stimata: ha scarto pari al 48% della media.

**Conseguenza.** La domanda di O4 ("ensemble o inviluppo?") era mal posta:
nessuna combinazione dei due modelli puo' coprire un bersaglio diverso da
quello su cui e' calibrata. Il problema non e' come si mescolano i quantili, e'
che il target e' il prezzo medio mentre serve il prezzo singolo.

Nota metodologica, verificata anche in letteratura: la garanzia della
calibrazione conformale e' **marginale**, cioe' vale in media sulla
popolazione di test, e non si trasferisce a un bersaglio diverso da quello su
cui e' stata costruita ([BBVA AI Factory](https://www.bbvaaifactory.com/conformal-prediction-an-introduction-to-measuring-uncertainty/),
[studio comparativo sui metodi conformali](https://arxiv.org/pdf/2405.02082)).
Qui il cambio di bersaglio e' esattamente il punto.

**Candidato a correzione, non applicato.** Tetto dei titolari
`q90 + 0.5 * prezzo-ombra + k * dispersione fra aste`, con k da scegliere: k=1
porta la copertura del singolo prezzo all'82,8%. Attenzione: piu' copertura
non significa che convenga pagare di piu'. Il prezzo che ci si aspetta e il
massimo che conviene offrire restano due cose diverse; il tetto deve restare
legato al valore del giocatore per la rosa, non solo al prezzo atteso.

---

## 2 — Il soffitto del banco: risolto, e il primo risultato e' netto

**Il problema.** Contro qualunque tavolo provato (torneo, informativo) B vince
il 99-100%: nessun confronto puo' misurare una politica d'asta, perche' non
c'e' spazio per migliorare. Il suo vantaggio viene dal modello valore e nessun
avversario disponibile lo usa.

**La soluzione.** Due seggi B nella stessa asta, con la stessa testa e una sola
differenza nel modo di offrire. Si contendono gli stessi giocatori, quindi uno
dei due deve per forza perdere: il soffitto sparisce per costruzione.
`scripts/indagine/o3c_due_seggi.py`.

**Risultato su 20 aste** (k = 0,5 sulla dispersione fra aste), criteri
fissati prima: la variante deve vincere piu' scontri diretti con intervallo che
esclude la parita', e lasciare almeno 20 crediti in meno.

| misura | attuale | variante | differenza | IC95 appaiato |
|---|---|---|---|---|
| cassa lasciata | 76,8 | **14,2** | **-62,5** | [-81,6 , -41,3] |
| punti stagione | 2837,3 | 2860,5 | +23,1 | [-8,5 , +52,4] |
| vittorie | 37,4% | 62,5% | +25,1% | [-3,6% , +50,7%] |
| posizione media | 1,6 | 1,4 | -0,2 | [-0,5 , +0,1] |

**Cassa: criterio superato con ampio margine.** Il residuo passa da 77 a 14
crediti e l'intervallo sta tutto sotto la soglia. Questo e' il problema che si
voleva risolvere, ed e' risolto: la variante spende quello che il piano aveva
previsto di spendere.

**Scontri diretti: inconcludente.** La variante vince il 62,5% contro il 37,4%,
ma l'intervallo di confidenza va da -3,6% a +50,7% e tocca la parita': con 20
aste non si puo' dire che vinca davvero. Su 20 aste ne perde 3 (in due lascia
piu' cassa dell'altra). Per dimezzare l'incertezza servirebbero circa 80 aste.
Non ho spostato il criterio dopo aver visto il numero.

**Il soffitto e' effettivamente sparito**: qui i due seggi stanno al 37% e al
62%, non piu' al 99%. Il banco ora discrimina, che era lo scopo.

**Avvertenza.** Questo banco misura quale politica prevale **fra due copie
dello stesso bot**. Non dice come andrebbe contro persone competenti, e non
sostituisce un tavolo realistico: dice solo, in modo pulito, se una regola di
offerta batte l'altra a parita' di tutto il resto.

---

## 4 — L'effetto squadra: le due misure erano la stessa, il codice era gia' giusto

**Il problema apparente.** Il report precedente misurava il 13-20% della
varianza, il banco nuovo il 25-29%, e il valore nel codice
(`TEAM_SHOCK_SD = 0.25`) sembrava sotto il bersaglio.

**La prova.** Sulla stagione 2024/25, 10.713 voti, 20 squadre, 38 giornate,
con in media 14,1 giocatori per squadra-giornata:

| modo di calcolare | quota della varianza | scarto tipo |
|---|---|---|
| scarto dalla media individuale, lordo | 25,4% | 0,284 |
| voto grezzo, lordo | 26,4% | 0,309 |
| **scarto dalla media, al netto del rumore di campionamento** | **19,7%** | **0,250** |

Le medie di squadra-giornata sono calcolate su ~14 giocatori: una parte della
loro variabilita' e' solo rumore di campionamento, non vero effetto squadra.
Tolto quello, restano 0,250 di scarto tipo, **esattamente il valore nel
codice**, e il 19,7% coincide con il 13-20% dei report precedenti.

**Verdetto: niente da correggere.** Il mio allarme precedente confrontava una
misura lorda con una depurata. Chiuso.

---

## 5 — Lo snapshot del 4 settembre: piccolo problema, ma ne emerge uno piu' grosso

**Il problema.** La quotazione fanta.soccer usata come feature e' quella della
rilevazione piu' vicina al 1° settembre **in valore assoluto**: per le stagioni
di addestramento cade prima (27/8, 1/9, 30/8, 29/8), per il listone 2026/27
cade **dopo** (4/9).

**Quanto pesa la differenza fra le due rilevazioni.** Confrontando la
rilevazione del 28/8 con quella del 4/9 sui 545 giocatori appaiati per codice:
il 20% delle quotazioni cambia, di 1-3 crediti al massimo, con correlazione
0,9975. Fra i giocatori che cambiano ci sono pero' nomi della rosa proposta
(Malen, Raimondo, Palmisani, Ekkelenkamp, tutti +3).

**Il problema piu' grosso, emerso mentre misuravo.** `quot_fs_sett` e' la
**seconda feature per importanza** del modello prezzo (8,0%, dietro solo alla
quotazione ufficiale al 50,6%). Ho provato a toglierla, con quattro semi per
ciascuna delle due prove:

| test | errore medio con la feature | senza | differenza |
|---|---|---|---|
| 2023-24 (n=336) | 6,47 ± 0,14 | 5,96 ± 0,03 | **-0,52 cr** |
| 2024-25 (n=255) | 6,79 ± 0,13 | 5,74 ± 0,07 | **-1,05 cr** |

**Togliendola il modello prezzo migliora**, in tutte e due le stagioni, con
scarti fra semi molto piu' piccoli della differenza. Spiegazione plausibile
(non verificata): e' quasi la stessa informazione della quotazione ufficiale,
ma con rumore in piu', mancante nel 12-23% dei casi e rilevata in date diverse
da una stagione all'altra.

**Candidato a correzione, non applicato**: togliere `quot_fs_sett` dalle
feature del prezzo, oppure fissare una data di riferimento esplicita e
prendere solo rilevazioni precedenti. Sono due rimedi diversi e vanno decisi
separatamente.

---

## 6 — Le tre regole mai confermate: cosa dice la fonte

Consultati il regolamento delle leghe private di fantacalcio.it e le guide
ufficiali della piattaforma.

**Modificatore di difesa — il codice e' conforme.** La regola ufficiale: si
applica quando "il portiere (qualora incluso) e almeno 4 difensori portano
punteggio alla squadra"; si calcola sulla media dei voti puri del portiere e
dei **3 migliori difensori**, scartando il piu' basso; si attiva solo con
almeno 4 difensori schierati, vale anche con 5, non vale con 3. Il codice fa
esattamente questo, e usa i giocatori che hanno portato punteggio dopo le
sostituzioni. Unica ambiguita': la fonte dice "in campo" senza precisare se
prima o dopo i cambi, ma il vincolo "portano punteggio" indica il dopo.
([guida modificatori](https://leghe.fantacalcio.it/guide-leghe-fantacalcio/gestione-lega/impostazione-delle-opzioni-modificatori-90),
[fantacalcio-online](https://www.fantacalcio-online.com/it/regole/guida-modificatore-difesa))

**Sostituzioni — il codice implementa una delle tre modalita' ufficiali.** Nel
Classic esistono tre impostazioni: *Traditional* (cambi solo fra pari ruolo,
mai cambio modulo), *Hybrid* (prima pari ruolo, poi eventuale cambio modulo),
*Dynamic* (priorita' al cambio modulo, entra il primo a voto in ordine di
panchina che formi un modulo valido). Il codice implementa **Traditional**.
Non e' un errore, e' una scelta: va confermato quale usa la tua lega, perche'
con Hybrid o Dynamic la panchina rende di piu' e il valore dei giocatori
cambia. ([opzioni sostituzioni](https://leghe.fantacalcio.it/guide-leghe-fantacalcio/gestione-lega/impostazione-delle-opzioni-sostituzioni-88),
[Magic Leghe](https://leghe.fantacalcio-online.com/it/regole/sostituzioni-automatiche-come-funzionano-fantacalcio))

**Spareggio — il codice usa uno dei criteri ufficiali.** Il regolamento delle
leghe private elenca fra i criteri disponibili: somma dei fantapunti totali,
gol fatti, gol subiti, differenza reti, classifica avulsa sugli scontri
diretti. Il codice usa punti in classifica e poi somma dei fantapunti: e' fra
quelli previsti, ma la scelta e' della lega.
([regolamento leghe private](https://www.fantacalcio.it/regolamenti/leghe-private))

**Soglie dei gol — confermate.** "La soglia goal universale e' a quota 66
punti"; per le fasce successive "di norma non si scende sotto i 4 punti e non
si sale oltre i 6". Il codice usa 66 e poi uno ogni 6: dentro il range, al
limite alto. Anche questa e' un'opzione di lega.

**Da confermare da te, tre cose:** la modalita' di sostituzione (Traditional,
Hybrid o Dynamic), il criterio di spareggio, e il passo delle fasce gol (6 e'
il massimo abituale; se la tua lega usa 4 o 5, cambiano tutti i calcoli di
P(1° posto)).

---

## Sintesi: che cosa e' cambiato dopo l'indagine

| punto | prima | dopo |
|---|---|---|
| residuo di cassa | causa nel tetto, correzione ovvia fallita | causa precisata: il tetto e' tarato sul prezzo medio, non sul singolo; misurato quanto manca |
| soffitto del banco | nessun tavolo discrimina | risolto con due seggi B nella stessa asta |
| O4 quantili | aperto: ensemble o inviluppo? | domanda mal posta: e' il bersaglio a essere sbagliato |
| effetto squadra | sospetto di valore sbagliato nel codice | falso allarme: 0,250 e' corretto, chiuso |
| snapshot 4/9 | asimmetria di date | quantificata (piccola), ma la feature stessa peggiora il modello |
| tre regole | mai confermate | due conformi alla fonte, tre opzioni di lega da confermare con te |
