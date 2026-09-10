# Check O3 e O4 — 6 settembre 2026

Solo misure. Codice operativo, pack e configurazione non sono stati toccati:
gli unici file nuovi sono i due script diagnostici e i loro esiti.

- `scripts/indagine/check_o3_cassa.py` → `data/livello0/check_o3_cassa.json`, `data/livello0/check_o3.log`
- `scripts/indagine/check_o4_quantili.py` → `data/livello0/check_o4_quantili.json`, `data/livello0/check_o4.log`

---

## O4 — come combinare i quantili dei due modelli di prezzo

Tre modi a confronto, tutti fuori campione, con il train fatto di stagioni
precedenti, la calibrazione ricavata dal train e il test mai guardato per
scegliere niente. La mediana q50 e' identica in tutti e tre (verificato: stessa
riga, differenza massima 0.00 crediti), quindi cambia solo la larghezza della
banda.

**Test 2023-24** (336 giocatori, 69 nuovi; train 2021-22, 428 righe; 82 s)

| combinazione | copertura | sotto q10 | sopra q90 | nuovi | vecchi | pinball q10 | pinball q90 | ampiezza |
|---|---|---|---|---|---|---|---|---|
| A ensemble attuale | 0.75 ± 0.02 | 0.13 | 0.12 | 0.87 | 0.72 | 1.25 | 1.62 | 9.9 cr |
| B inviluppo min/max | **0.80 ± 0.02** | 0.12 | 0.08 | 0.91 | 0.78 | **1.22** | **1.43** | 12.8 cr |
| C ensemble calibrato | 0.70 ± 0.03 | 0.15 | 0.14 | 0.83 | 0.67 | 1.30 | 1.64 | 8.6 cr |
| TabPFN da solo | 0.69 ± 0.03 | 0.16 | 0.15 | 0.78 | 0.67 | 1.22 | 1.48 | 7.7 cr |
| CatBoost da solo | 0.71 ± 0.03 | 0.14 | 0.15 | 0.84 | 0.68 | 1.33 | 2.20 | 10.9 cr |

**Test 2024-25** (255 giocatori, 43 nuovi; train 2021-22 + 2023-24, 764 righe; 209 s)

| combinazione | copertura | sotto q10 | sopra q90 | nuovi | vecchi | pinball q10 | pinball q90 | ampiezza |
|---|---|---|---|---|---|---|---|---|
| A ensemble attuale | 0.68 ± 0.03 | 0.23 | 0.09 | 0.84 | 0.64 | 1.35 | **1.40** | 10.7 cr |
| B inviluppo min/max | **0.89 ± 0.02** | 0.06 | 0.06 | 0.91 | 0.89 | **1.31** | 1.72 | 14.3 cr |
| C ensemble calibrato | 0.69 ± 0.03 | 0.22 | 0.09 | 0.84 | 0.66 | 1.35 | 1.40 | 10.7 cr |
| TabPFN da solo | 0.86 ± 0.02 | 0.06 | 0.08 | 0.81 | 0.87 | 1.32 | 1.73 | 12.9 cr |
| CatBoost da solo | 0.48 ± 0.03 | 0.37 | 0.14 | 0.72 | 0.43 | 2.68 | 1.72 | 7.5 cr |

**Letture.**

- L'inviluppo e' l'unico che arriva all'obiettivo dichiarato: 0.80 e 0.89
  contro 0.75 e 0.68 dell'ensemble attuale. Lo paga con una banda piu' larga
  del 29-34%.
- Non e' pero' meglio su tutto, come segnalato: nel 2024-25 il tetto q90
  dell'ensemble attuale e' piu' affilato (pinball 1.40 contro 1.72). Se il q90
  serve come massimo da offrire in asta, l'inviluppo lo alza e rende il tetto
  meno informativo. Il q10 invece migliora sempre con l'inviluppo.
- Conformalizzare l'ensemble dopo averlo formato (C) **non aiuta**: nel 2023-24
  peggiora (0.70) e nel 2024-25 e' identico all'attuale, perche' l'ensemble
  formato sbaglia meno sulla calibrazione e la correzione che ne esce e' quasi
  nulla.
- La coda alta e quella bassa non sono simmetriche e cambiano fra stagioni: nel
  2024-25 l'ensemble attuale lascia fuori il 23% sotto il q10 e solo il 9%
  sopra il q90. Il problema e' quasi tutto sul q10, cioe' sul pavimento.
- Il crollo dell'ensemble nel 2024-25 viene dal CatBoost (copertura 0.48, con
  il 37% dei prezzi sotto il suo q10): mediare un modello ben tarato con uno
  storto porta giu' anche il primo.
- I nuovi restano meglio coperti dei vecchi in tutte le combinazioni: conferma
  ulteriore che allargare la banda ai soli nuovi era il contrario di quel che
  serve.

**Limiti dichiarati.** Solo due stagioni di test, con campioni di 336 e 255
righe: l'errore standard sulla copertura e' 0.02-0.03, quindi la differenza fra
A e B nel 2024-25 e' reale, ma con due sole annate non si puo' dire che
l'inviluppo sia stabilmente migliore. Nessuna garanzia teorica dell'80%: la
correzione conformal e' stimata su un modello addestrato sull'80% del train e
applicata a un modello riaddestrato sul 100%, e calibrazione e test sono
stagioni diverse, quindi non scambiabili. Il target e' il prezzo MEDIO fra le
aste di quella stagione: per il prezzo di una singola asta va aggiunta la
dispersione fra leghe (coefficiente di variazione mediano 0.63), che questi
intervalli non contengono.

---

## O3 — cassa a fine asta, col codice e i pack di oggi

20 aste per stagione, tavolo e seed del torneo ufficiale (1B + 2A + 7C,
seed 10000-10019), pack attuali. Stagione 2024/25 = validazione (prezzi di
riferimento da aste reali per il 90% dei crediti del piano); 2025/26 =
diagnostica (nessun prezzo d'asta osservato).

| | 2024/25 (validazione) | 2025/26 (diagnostica) |
|---|---|---|
| cassa finale di B, media | **73.9 cr** | **121.3 cr** |
| mediana / massimo | 81.5 / 143 | 122.5 / 240 |
| rose complete | 20 su 20 | 20 su 20 |
| spesa prevista dal piano | 500 cr | 494 cr |
| spesa sostenuta | 426 cr | 379 cr |
| target del piano persi | 13.3 su 25 (per 237 cr) | 12.8 su 25 (per 282 cr) |
| punti di B | 2919.9 | 2875.3 |
| vittorie di B | 99.3% ± 0.4% | 99.9% ± 0.1% |
| cassa degli avversari (mediana) | 0 cr per 8 su 9 | 0-75 cr |

**Il residuo c'e' ancora col codice di oggi**: 74 crediti nella stagione di
validazione, 121 in quella diagnostica. Gli 88 crediti dei vecchi log erano
nell'ordine di grandezza giusto, ma venivano da codice e pack di agosto: ora la
misura e' fatta con quelli attuali.

**La causa non e' nei cap in quanto tali, ma nei target persi.** B parte con un
piano che impegna quasi tutto il budget (500 e 494 crediti previsti), ma **ne
perde oltre la meta'**: 13 giocatori su 25, che finiscono agli avversari per
237-282 crediti complessivi. Quello che resta in cassa e' la differenza fra
quanto aveva pianificato di spendere su quei nomi e quanto gli e' costato
ripiegare su alternative piu' economiche. La rosa si completa sempre (20 su 20
in entrambe le stagioni): non e' un problema di slot vuoti.

**Quanto costa in vittorie: non misurabile su questo tavolo.** B vince il 99.3%
e il 99.9% degli scontri diretti: contro questa composizione non c'e' spazio
per migliorare, quindi il confronto non puo' dire se i 74 crediti valgano
qualcosa. La correlazione fra cassa lasciata e risultato, dentro le 20 aste,
cambia segno fra le due stagioni (punti +0.11 nel 2024/25 e -0.52 nel 2025/26;
vittorie +0.08 e -0.27), il che conferma che con questi dati non si conclude
nulla: e' comunque una correlazione, non una causa. Per misurare il costo
servirebbe un tavolo dove B non domini (avversari informati, o piu' seggi A+),
oppure un controfattuale esplicito: stessa asta, stessi seed, con e senza una
politica che spenda il residuo.

**Parita' fra bot B e Copilota: verificata.** Entrambi costruiscono
`BBot(rng, pack.b_predictions, objective=pack.b_objective)`
(`src/fantabot/tournament.py:60-64` e `scripts/f10_copilot.py:101-110`); il
Copilota chiede il massimo da offrire a `ADVISOR._max_bid_for()` e usa la
stessa formula del prezzo d'occasione di `bot_b.py`; il calore di mercato si
aggiorna nello stesso modo (somma dei prezzi battuti diviso somma dei q50, con
la stessa soglia). L'unica differenza e' che il Copilota tronca il consiglio
all'offerta massima legale. Stessa politica.

**Nessun cap e' stato modificato.**

---

## Opzione proposta

**O3b — controfattuale appaiato prima di scegliere qualsiasi politica.**
Rigiocare le stesse 20 aste (stessi seed, stesso tavolo) su un tavolo dove B
non domini, confrontando la politica attuale con una che rialzi il massimo per
lotto quando il piano ha accumulato risparmio. Solo cosi' si misura quanto
valgono davvero i 74 crediti, invece di supporlo.

Motivazione: i due numeri che servivano non ci sono ancora. Il primo e' quanto
costa il residuo in vittorie, e su questo tavolo non e' misurabile per effetto
soffitto. Il secondo e' se il residuo si riduca alzando i cap o solo spostando
la spesa: dato che nasce dal perdere 13 target su 25, alzare i cap potrebbe
farne recuperare qualcuno oppure solo far pagare di piu' gli stessi. Sono due
esiti opposti e vanno separati prima di toccare il codice.

Su O4, se serve una decisione subito: l'inviluppo e' l'unico che raggiunge la
copertura dichiarata (0.80 e 0.89 contro 0.75 e 0.68), ma allarga la banda del
30% e nel 2024/25 rende il tetto q90 meno affilato. Con due sole stagioni di
test non e' una scelta che consiglio di chiudere ora.

Nessuna modifica applicata. In attesa.
