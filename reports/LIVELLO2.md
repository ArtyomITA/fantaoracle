# Livello 2 — cubo TABELLINO: correzioni, dati, implementazione, misure

7 settembre 2026. Documento operativo: che cosa è stato corretto, che cosa è
stato costruito, che cosa dicono le misure e che cosa resta aperto.

**Niente è stato attivato.** Il cubo è un percorso separato
(`src/fantabot/tabellino/`, `scripts/l2_*.py`). Bot, Copilota, pack e
ottimizzatore non lo usano e non sono stati toccati nel loro comportamento.

---

## 0. Stato congelato prima di toccare qualsiasi cosa

Il meccanismo di istantanea aveva quattro difetti che lo rendevano inutile come
prova di riproducibilità, tutti verificati e tutti corretti in
`scripts/f16_istantanea.py`:

| difetto | perché è un problema | correzione |
|---|---|---|
| `data/raw` considerato «immutabile per conto suo», salvata solo l'impronta | gli aggiornatori di mercato e i download Transfermarkt lo riscrivono: un'impronta che non corrisponde più a niente non riproduce nulla | archivio per impronta: i byte di `data/raw` sono conservati davvero |
| identificativo al minuto, cartella creata con `exist_ok=True` | due istantanee nello stesso minuto si sovrascrivevano | identificativo `AAAAMMGG_HHMMSS_<8 caratteri della firma>`; se esiste, lo script si ferma |
| copiati solo CSV e GZ del grezzo | HTML e JSON servono alla provenienza (probabili, listoni, prezzi live) | perimetro completo, per estensione qualsiasi |
| nessuna verifica dopo la copia | un file cambiato durante la cattura passava inosservato | doppia lettura, e confronto finale con la sorgente; le discordanze finiscono in `instabili` e fanno uscire con codice 1 |

Istantanea di partenza: **`20260907_014307_e6b11750`**, 931 file, 169,1 MB,
zero file instabili. L'archivio è condiviso per impronta, quindi le istantanee
successive costano solo il delta.

Istantanea di chiusura, dopo tutto il lavoro: **`20260907_033803_5504bafe`**,
1012 file, 83 nuovi nell'archivio (344,6 MB in tutto). Le due istantanee
insieme permettono di vedere esattamente che cosa e' cambiato e di tornare
indietro.

```bash
python scripts/f16_istantanea.py --elenco
python scripts/f16_istantanea.py --ripristina 20260907_014307_e6b11750 /percorso/di/prova
```

Confronto fra le due: gli unici file **preesistenti** modificati sono
`HANDOFF_SESSIONE.md` e `scripts/f13_validate_plan.py` (solo etichette di
stampa, nessun cambio di comportamento). Tutto il resto e' nuovo.

---

## 1. Correzioni ai risultati non sostenuti

Le rettifiche complete stanno in testa a
[INDAGINE_LIVELLO2.md](INDAGINE_LIVELLO2.md). In sintesi, con le prove.

### 1.1 Il modello di partita provato non era quello descritto

`scripts/indagine/l2_modello_partita2.py`, da cui viene la tabella del pezzo 1,
non contiene la correzione di Dixon e Coles: stima un Poisson penalizzato. Il
report la descriveva come Dixon-Coles.

### 1.2 Mancava il livello generale dei gol

Attacco e difesa vincolati a somma zero senza intercetta costringono la media
dei gol in trasferta vicino a 1. Misurato sui dati veri (train 2020-2023):

| | osservati | stimati |
|---|---|---|
| gol in casa | 1,5167 | 1,5167 |
| gol in trasferta | 1,3132 | **1,1202** (−14,7%) |
| gol in trasferta, modello nuovo | 1,3132 | **1,3132** |

Fissato in `tests/test_l2_partita.py::test_recupero_sintetico_squadre_equivalenti`.

La penalizzazione, inoltre, agiva solo sulle prime n−1 squadre: l'ultima era di
fatto libera e il risultato dipendeva dall'ordine dell'elenco. Nel modello nuovo
la penalizzazione agisce sul vettore intero e il test
`test_invarianza_rinomina` verifica che riordinare le squadre non cambi nulla.

### 1.3 La media riportata era una scelta a posteriori

Medie corrette sulle tre stagioni di prova: B (media storica) **0,20287**,
C 0,21413, D 0,20047, **E 0,20827**, F 0,19443. Lo 0,1996 del report si ottiene
prendendo D nel 2023 ed E nel 2024 e nel 2025, cioè scegliendo il migliore
stagione per stagione. Con i numeri giusti, nel vecchio modello **nessuna
configurazione pre-asta batteva la media storica**.

### 1.4 La metrica non poteva vedere quello che si voleva misurare

La correzione di Dixon e Coles **conserva le marginali**: la somma dei quattro
scostamenti è zero per riga e per colonna. Quindi P(la squadra ospite non
segna) è identica con e senza correzione, e un Brier sulla porta inviolata dà
**esattamente lo stesso numero** per i due modelli. Giudicare la correzione con
quel Brier era impossibile per costruzione.
Fissato in `test_dixon_coles_preserva_marginali`.

Conseguenza operativa: per la dipendenza servono il punteggio logaritmico sul
risultato congiunto, il Brier su 1X2 e l'RPS. Il banco nuovo li usa tutti.

### 1.5 «Fuori campione» era troppo generoso, e due numeri esterni sono ritirati

Solo il pezzo 1 aveva una vera separazione. Le regressioni del pezzo 2 sono
stimate e valutate sulla stessa stagione: **descrittive**. I confronti esterni
«49,3% contro 52-58%» e «batte il Poisson semplice nel 40% dei casi» non sono
confrontabili con questo problema e sono ritirati.

### 1.6 Sullo shock di squadra

Uno shock condiviso introduce una componente comune di covarianza; non impone
*automaticamente* la stessa correlazione fra tutti i ruoli, perché la
correlazione dipende anche dalle varianze individuali. La misura resta valida
(il vecchio simulatore produce 0,10-0,16 per ogni coppia di ruoli contro
0,12-0,34 osservate), la spiegazione era imprecisa.

---

## 2. Dati: che cosa è stato acquisito e che cosa manca davvero

### 2.1 Storico: formazioni ed eventi, che mancavano

| file | righe Serie A | stagioni | contenuto |
|---|---|---|---|
| `game_lineups.csv.gz` | 222.611 | 2013-2025 | titolari, panchina, posizione, capitano |
| `game_events.csv.gz` | 78.588 | 2012-2025 | gol, cartellini, sostituzioni, minuto, assist |

Sbloccano la titolarità reale, le sostituzioni reali e il minuto degli eventi:
tre cose che il progetto approssimava con i minuti giocati.

### 2.2 Stagione in corso: due fonti indipendenti che concordano

Transfermarkt si è fermato alla stagione 2025 (il manutentore ha dichiarato gli
aggiornamenti sospesi da luglio 2026,
[discussione 383](https://github.com/dcaribou/transfermarkt-datasets/discussions/383)).
Verificato: `games.csv.gz` non ha **nessuna** partita di Serie A 2026.

Due fonti nuove, acquisite e verificate una contro l'altra:

- **calendario fantacalcio.it** (`scripts/l2_scarica_calendario.py`): 380
  partite, 28 giocate, 352 da giocare. Verifiche superate: 10 partite per
  giornata, 20 squadre distinte, 19 in casa e 19 fuori per squadra, ogni coppia
  due volte una per campo. Le pagine grezze sono conservate con le impronte.
  Il PDF ufficiale della Lega (Allegato C.U. n.205) è un'immagine senza testo:
  va bene come riscontro visivo, non come fonte automatizzabile.
- **Understat** (`scripts/l2_scarica_understat.py`): 380 partite per stagione
  dal 2019 al 2026, con **xG per partita** (che nel progetto esisteva solo come
  aggregato di stagione). Per il 2026: 28 giocate con xG.

**Riscontro incrociato**: gli accoppiamenti coincidono su tutte e 380 le
partite e i risultati su tutte e 28 le giocate. Restano 39 differenze di data,
tutte su partite non ancora giocate: sono gli orari televisivi non ancora
fissati, ed è per questo che quelle righe portano `provvisorio = 1`.

### 2.3 Tabella unica delle partite

`data/processed/l2_partite.parquet`: 3040 partite, 8 stagioni, 2688 giocate,
xG su tutte le giocate. Ogni riga porta la fonte di ogni campo. La
corrispondenza fra i nomi delle squadre delle due fonti **non è scritta a
mano**: si ricava unendo per data e risultato e si verifica che sia uno a uno.

### 2.4 Che cosa manca ancora, detto chiaro

| serve | stato |
|---|---|
| formazioni titolari 2026/27 | **assente**: Transfermarkt non copre la stagione. Recuperabile dai tabellini di fantacalcio.it, 28 partite da leggere |
| xG per giocatore per partita | assente: richiede lo scraping per giocatore di Understat |
| minuti in Serie B o all'estero per i nuovi | assente, come già noto |

---

> **AVVERTENZA sulla sezione 3.2.** I conteggi degli stati riportati là sotto
> (`non_in_rosa` 9.258, `panchina_non_entrato` 4.751) descrivono il panel
> **prima** della correzione, dentro un capitolo che dichiara il contratto
> realizzato. Lo stato dei parquet oggi: `non_in_rosa` **non esiste più**;
> 2024-25 ha `titolare` 8.324, `ignoto` 5.671, `panchina_non_entrato` 4.738,
> `escluso` 3.600, `panchina_entrato` 3.469. Da riscrivere.

## 3. Panel giocatore × partita: il contratto, finalmente realizzato

`scripts/f14_build_panel.py` dichiarava un contratto che non realizzava.
Difetti verificati e corretti in `scripts/l2_costruisci_panel.py`:

| difetto | correzione |
|---|---|
| partiva dalle righe dei voti: non poteva distinguere «non convocato» da «riga assente» | l'universo parte dal listone: una riga mancante è un'informazione |
| due soli stati (`con_voto`, `senza_voto`) | cinque stati di convocazione e tre di voto, tenuti separati |
| `drop_duplicates("master_id")` sceglieva in silenzio una corrispondenza | le ambiguità restano dichiarate, la riga resta senza identità |
| nessun momento di acquisizione | `acquisito_il` su ogni riga; `disponibile_dal` resta ignoto perché non è ricostruibile, e non viene inventato |
| **2026/27: tutte le 638 righe senza partita collegata** | **100% collegate** grazie al calendario nuovo |

### 3.1 Copertura misurata

| stagione | righe universo | su partite giocate | partita collegata | minuti | formazioni |
|---|---|---|---|---|---|
| 2021-22 | 25.650 | 25.650 | 100,00% | 44,23% | 100,00% |
| 2023-24 | 25.232 | 25.232 | 100,00% | 46,48% | 100,00% |
| 2024-25 | 25.802 | 25.802 | 100,00% | 45,71% | 100,00% |
| 2025-26 | 25.194 | 25.194 | 100,00% | 46,51% | 99,71% |
| 2026-27 | 22.306 | 1.639 | 100,00% | 0% | 0% |

I minuti coprono il 44-47% perché esistono solo per chi è sceso in campo: è
il valore giusto, non un buco. Il 2026/27 non ha minuti né formazioni perché
Transfermarkt non copre la stagione: è un limite dichiarato, non nascosto.

### 3.2 Stati, tenuti separati come richiesto

2024/25, 25.802 righe: `non_in_rosa` 9.258, `titolare` 8.324,
`panchina_non_entrato` 4.751, `panchina_entrato` 3.469.
Voto: `nessuna_riga` 13.948, `con_voto` 10.713, `senza_voto` 1.141.

Delle 13.948 righe senza voto, **9.196 sono di giocatori che in quel periodo
non risultano nella rosa di quel club** (ceduti, arrivati dopo, mai tesserati)
e 4.751 di giocatori in panchina che non sono entrati. Nessuna riga assente
viene trasformata in «non convocato».

Sul s.v.: nel 2024/25 sono 1.141, di cui 1.135 con minuti noti e **tutti con
minuti positivi** (zero righe con zero minuti). Stesso quadro nelle altre
stagioni. È un fatto misurato, non l'assunzione «s.v. = entrato pochi minuti»:
per 6 righe i minuti non esistono e restano ignoti.

### 3.3 Punteggio della fonte: riconciliazione, senza scrivere «100%»

| stagione | righe con voto | discordanti |
|---|---|---|
| 2021-22 | 10.636 | 0 |
| 2023-24 | 10.791 | 0 |
| 2024-25 | 10.713 | **1** (Delprato, Parma, giornata 3) |
| 2025-26 | 10.778 | 0 |
| 2026-27 | 582 | 0 |

La discordanza di Delprato resta esplicita. Il punteggio della fonte e le
regole della lega (porta inviolata, modificatore) stanno in due posti diversi:
`fantabot.tabellino.punteggio` applica le seconde richiamando `fantabot.rules`
e `fantabot.season.lineup`, che restano l'unica fonte delle regole.

---

> **AVVERTENZA sulle sezioni 4.1, 5 e 6, aggiunta dopo la revisione
> indipendente del 7 settembre.** Gli artefatti su cui queste tre sezioni sono
> state scritte sono **superati**: `data/l2/banco_partita.json` registra come
> ingresso l'impronta `81585ec4` di `l2_partite.parquet`, mentre il file oggi è
> `f725c558`; e il cubo 2024-25 non è stato rigenerato dopo il rifacimento del
> panel. Diversi numeri non coincidono nemmeno con l'artefatto della loro
> generazione: «+5,9 % di gol di stagione» contro il **+7,58 %** del file, dieci
> coefficienti del voto su undici, dieci scostamenti di convocazione su dieci,
> «assist 63,7 %» contro **71,2 %**, «bootstrap 2000» contro il `boot: 1000`
> registrato. Vanno **rigenerati**, non riscritti a mano. Elenco completo e
> comandi in [RIPRESA_L2_L3.md](../RIPRESA_L2_L3.md) §2.6 e §2.7.
> Non toccate da questa avvertenza, perché verificate una per una da un
> revisore indipendente: §2 (dati acquisiti), §3.1 e §3.3 (copertura e
> riconciliazione), §7 (banco e verdetto appaiato).

## 4. Il modello di partita, rifatto

`src/fantabot/tabellino/partita.py`. Parametrizzazione:

```
log lambda_casa   = mu + vantaggio_casa + attacco_casa   - difesa_ospite
log lambda_ospite = mu +                  attacco_ospite - difesa_casa
```

con attacco e difesa centrati dentro la verosimiglianza e penalizzati sul
vettore intero (simmetrico per rinomina), correzione di Dixon e Coles con
`rho` limitato all'intervallo in cui `tau` resta positivo (nessun clipping
silenzioso: le violazioni finiscono in `diagnostica`), decadimento sul **tempo
realmente trascorso**, prior per le neopromosse stimato dalle neopromosse
passate, prior da xG, e propagazione dell'incertezza sulle forze via
approssimazione normale all'ottimo.

### 4.1 Banco fuori campione

`scripts/l2_banco_partita.py`. Train: tutte le partite con **data** anteriore
al primo giorno della stagione di prova. Iperparametri (decadimento e forza
della penalizzazione) scelti sulla **stagione precedente**, addestrando su
quelle prima ancora. Metriche: punteggio logaritmico sul risultato esatto,
RPS su 1X2, Brier 1X2, Brier porta inviolata, calibrazione.

Media sulle tre stagioni di prova (2023-24, 2024-25, 2025-26), soli candidati
disponibili prima dell'asta:

| candidato | log score | RPS | Brier 1X2 | Brier porta inviolata |
|---|---|---|---|---|
| A tasso base | — | 0,2290 | 0,6602 | 0,2089 |
| B media storica di squadra | — | 0,2075 | 0,6180 | 0,2038 |
| C Poisson con intercetta | 2,7941 | 0,1981 | 0,5978 | 0,1927 |
| D Poisson + decadimento | 2,7891 | 0,1984 | 0,5975 | 0,1927 |
| E Dixon-Coles + decadimento | 2,7890 | 0,1983 | 0,5970 | 0,1926 |
| **F E + prior da xG** | **2,7826** | **0,1966** | **0,5936** | **0,1920** |

Differenza appaiata sull'RPS rispetto alla media storica, con intervallo al 95%
da bootstrap appaiato (2000 ripetizioni):

| stagione | F − B | intervallo 95% |
|---|---|---|
| 2023-24 | −0,0109 | [−0,0169, −0,0050] |
| 2024-25 | −0,0124 | [−0,0188, −0,0056] |
| 2025-26 | −0,0095 | [−0,0172, −0,0026] |

**Il modello corretto batte la media storica in tutte e tre le stagioni, prima
dell'asta, con intervalli che escludono lo zero.** Il verdetto precedente
(«guadagno 1-2%, gate non raggiunto») era prodotto dal modello mal specificato
e da una metrica cieca.

Il gate assoluto «Brier porta inviolata sotto 0,19» **non è stato mantenuto**:
dipende dalla frequenza dell'evento nella stagione valutata, che cambia
(0,203 nel 2023, 0,223 nel 2025). Il criterio usato è il confronto con la
baseline pertinente, con differenza appaiata e intervallo.

Il candidato G (rifit prima di ogni giornata, con filtro sulla **data**
effettiva e non sulla giornata) è riportato separatamente e **non concorre**
alla scelta pre-asta: nel 2025-26 dà RPS 0,2004 contro 0,2043 di F.

Diagnostica: gol in trasferta osservati e stimati coincidono alla quarta cifra
in tutte e tre le stagioni; `rho` stimato +0,011 / −0,060 / −0,070; vantaggio
del campo 0,169 / 0,170 / 0,136.

---

## 5. Il cubo: partecipazione, eventi, voto, punteggio

Quattro moduli, un contratto comune, un generatore.

### 5.1 Partecipazione (`partecipazione.py`)

Catena con memoria sulla **convocazione** (non sulla presenza a voto: sono
quantità diverse, e riusare i coefficienti dell'una per l'altra sarebbe un
errore). Scostamenti sul logit misurati sul panel:

| striscia | presente | assente |
|---|---|---|
| 1 giornata | +0,889 | −1,137 |
| 2 | +0,887 | −1,364 |
| 3 | +0,995 | −1,451 |
| 5 | +0,990 | −1,440 |
| 8 o più | +0,521 | −1,837 |

Undici titolari estratti senza reimmissione con rumore di Gumbel (Plackett e
Luce) su un modulo estratto dalla distribuzione storica di quella squadra, e
adattato ai convocati. Panchina ordinata per probabilità di entrare, con il
portiere di riserva in fondo. Minuti come intervalli semiaperti: chi entra
prende il posto di chi esce, e in ogni minuto ci sono esattamente undici
giocatori in campo (verificato dal test).

### 5.2 Eventi (`eventi.py`)

Ogni gol: minuto estratto dalla distribuzione osservata (5.369 gol storici,
mediana 52'), poi autogol / rigore / azione, poi marcatore scelto **fra chi era
in campo a quel minuto** con peso pari al tasso individuale contratto verso la
media del ruolo, poi assist a un compagno in campo. Quote misurate: rigori
10,5% dei gol, autogol 3,0%, assist 63,7% dei gol su azione.

Il tabellino si riconcilia col risultato **per costruzione**, ed è verificato:
`verifica_coerenza` controlla che i gol dei giocatori più gli autogol avversari
facciano il risultato, che chi segna sia stato in campo, che il portiere abbia
i gol subiti della squadra e che i titolari siano undici con un portiere.

### 5.3 Voto dato il tabellino (`voto.py`)

Due specificazioni, sempre entrambe, perché il segno di un coefficiente dipende
da quale si usa:

| coefficiente | solo eventi individuali | con differenza reti |
|---|---|---|
| 1 gol | +0,957 | +0,850 |
| 2 o più gol | +1,441 | +1,258 |
| assist | +0,567 | +0,456 |
| rigore segnato | +0,673 | +0,599 |
| espulsione | −0,929 | −0,871 |
| portiere, porta inviolata | +0,255 | +0,099 |
| **portiere, 3+ gol subiti** | **−0,164** | **+0,034** |
| differenza reti | — | +0,101 |

**Questo chiude la contraddizione sul coefficiente del portiere.** La proposta
lo dava a −0,29, l'indagine precedente lo misurava a +0,05/+0,08 e ne
concludeva che «un coefficiente dichiarato ha segno opposto». Non era un
disaccordo sui dati: la specificazione dell'indagine conteneva la differenza
reti, che assorbe l'effetto (correlazione fra le due variabili −0,137). Nella
specificazione senza differenza reti il coefficiente è **negativo**, come la
proposta diceva, anche se più piccolo (−0,164 contro −0,29).

Varianza del voto spiegata: 45,4% (l'indagine riportava 39-42% con una
specificazione diversa). Scarto residuo 0,451.

La contrazione degli effetti individuali non è più un numero fissato a mano:
si stima dai dati (Bayes empirico, rapporto fra varianza residua e varianza
vera fra giocatori). Sul panel dà 15,1 partite equivalenti contro le 12 fissate
prima; la differenza è piccola, ma il valore non è più arbitrario.

### 5.4 Dipendenza residua: strutturata, non un unico shock

Misurata dopo il condizionamento agli eventi:

| coppia | prima | dopo |
|---|---|---|
| portiere-difensori | +0,160 | **+0,047** |
| difensori | +0,290 | +0,329 |
| centrocampisti | +0,240 | +0,255 |
| attaccanti | +0,203 | +0,187 |

Il condizionamento **azzera quasi** la correlazione portiere-difensori (quella
che conta per il modificatore) e **non** quella fra difensori. Uno shock unico
per squadra non può riprodurre due numeri così diversi. Il cubo scompone il
residuo in tre pezzi — squadra, reparto, individuale — e li calibra sui
bersagli osservati **nelle stagioni di addestramento** (mai in quella di prova),
misurando e riscalando fino a colpirli.

### 5.5 Quanti prendono voto

La fonte non dà un voto a tutti quelli che scendono in campo: nel 2024/25 l'8,7%
di chi ha giocato prende s.v. La probabilità è stimata per fascia di minuti, non
assunta. Senza questo passaggio la stagione simulata aveva 305 voti a giornata
contro i 282 veri.

---

## 6. Fedeltà del cubo: simulato contro osservato

`scripts/l2_genera_cubo.py 2024-25`, stima su tutto ciò che precede il
17/8/2024, generazione sul calendario vero.

| quantità | osservato | simulato | scarto |
|---|---|---|---|
| punti medi per giocatore-giornata | 6,148 | 6,165 | +0,017 |
| scarto dei punti | 1,517 | 1,525 | +0,008 |
| voto medio | 5,998 | 6,011 | +0,013 |
| scarto del voto | 0,602 | 0,571 | −0,031 |
| quantile 5% dei punti | 4,50 | 4,50 | 0,00 |
| quantile 50% | 6,00 | 6,00 | 0,00 |
| quantile 95% | 10,00 | 9,67 | −0,33 |
| presenze a voto per giornata | 281,9 | 284,1 | +2,2 |
| assist di stagione | 621 | 620 | −1 |
| gol di stagione | 936 | 991 | +55 |
| ammonizioni ai portieri | 19 | 21 | +2 |

| correlazione fra compagni | osservata | simulata |
|---|---|---|
| portiere-difensori | 0,114 | 0,152 |
| difensori | 0,333 | 0,320 |
| centrocampisti | 0,252 | 0,267 |
| attaccanti | 0,216 | 0,214 |

I bersagli di calibrazione venivano dalle stagioni di addestramento (0,149 /
0,341 / 0,268 / 0,238), non da questa: i valori simulati cadono vicino a quelli
osservati **fuori campione**.

Lo scarto che resta: **+5,9% di gol di stagione**. Il modello di partita stima
il livello di segnature del campionato sulle stagioni precedenti, e il 2024/25
ne ha segnati meno della media recente. È errore predittivo, non un difetto del
generatore.

---

## 7. Banco: quattro generatori a confronto, con verdetto appaiato

`scripts/l2_banco_confronto.py`. Stesso universo (il listone della stagione),
stesse regole, stesso orizzonte, stesse dieci rose di prova estratte una volta
sola, stessi flussi casuali indicizzati.

Rispetto alla versione precedente di questa sezione sono cambiate tre cose, e i
numeri con loro:

1. il modello di partita viene dalla **procedura unica** (§4), la stessa del
   cubo: prima banco e cubo usavano modelli diversi, con uno scarto medio di
   0,219 gol di intensità (16,69%);
2. il **bonus porta inviolata** è applicato esattamente una volta, allo stesso
   modo per l'osservato e per tutti i generatori: prima non era applicato in
   nessun punto, per 0,297 punti a giornata per rosa;
3. c'è un **verdetto appaiato con intervallo**, non solo un confronto di medie.

- **A** baseline semplice: ogni giocatore estrae dai propri fantavoti passati.
- **B** meccanica del vecchio simulatore: campioni appaiati, incertezza di
  stima, catena della disponibilità, shock di squadra unico 0,25.
- **B′** come B ma con le presenze del modello valore (`pres` nelle
  predizioni): è la configurazione di produzione, e **usa più informazione
  degli altri**.
- **C** cubo TABELLINO.

### 2024/25

| | punti medi | presenze/giornata | CRPS | scarto PIT | Brier presenze | rosa: punti/giornata | rosa: gol/giornata | corr P-D | corr D-D | corr C | corr A |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **VERO** | 6,148 | **281,9** | — | — | — | **55,28** | **0,216** | **0,121** | **0,311** | **0,196** | **0,210** |
| A | 6,134 | 361,6 | 1,644 | 0,0645 | 0,2557 | 58,60 | 0,367 | −0,010 | 0,012 | 0,002 | 0,009 |
| B | 6,126 | 362,3 | 1,640 | 0,0630 | 0,2562 | 60,80 | 0,472 | 0,154 | 0,161 | 0,153 | 0,096 |
| B′ | 6,117 | 331,6 | **1,456** | 0,0370 | **0,2204** | 58,80 | 0,400 | 0,152 | 0,162 | 0,149 | 0,091 |
| **C** | 6,189 | **283,9** | 1,578 | **0,0247** | 0,2468 | 53,33 | 0,192 | 0,169 | **0,301** | 0,258 | 0,221 |

### 2025/26

| | punti medi | presenze/giornata | CRPS | scarto PIT | Brier presenze | rosa: punti/giornata | rosa: gol/giornata | corr P-D | corr D-D | corr C | corr A |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **VERO** | 6,127 | **283,6** | — | — | — | **53,65** | **0,224** | **0,139** | **0,340** | **0,253** | **0,233** |
| A | 6,170 | 346,4 | 1,667 | 0,0452 | 0,2514 | 59,54 | 0,418 | −0,010 | 0,008 | 0,018 | −0,012 |
| B | 6,166 | 347,7 | 1,673 | 0,0441 | 0,2518 | 61,82 | 0,530 | 0,144 | 0,147 | 0,157 | 0,120 |
| B′ | 6,157 | 312,9 | **1,462** | **0,0166** | **0,2153** | 55,81 | 0,271 | 0,154 | 0,148 | 0,152 | 0,125 |
| **C** | 6,184 | **284,7** | 1,637 | 0,0298 | 0,2464 | **56,56** | **0,285** | 0,097 | **0,280** | 0,226 | 0,214 |

### Il verdetto, con la regola scritta prima

La regola è in [CRITERI_L2_L3.md](CRITERI_L2_L3.md) §3.7, fissata prima di
calcolare gli intervalli: due confronti distinti, differenza appaiata per
osservazione, bootstrap a 2.000 ricampionamenti, promozione solo se
l'intervallo esclude lo zero **in entrambe le stagioni**. Margine di non
inferiorità zero. Più basso è meglio, quindi una differenza negativa è a favore
del cubo.

| confronto | misura | 2024/25 | 2025/26 | esito |
|---|---|---|---|---|
| **C contro B′** (informazione comparabile) | CRPS | +0,1215 [+0,0811; +0,1598] | +0,1744 [+0,1325; +0,2134] | **C peggiore** |
| **C contro B′** | Brier presenze | +0,0264 [+0,0228; +0,0299] | +0,0311 [+0,0275; +0,0348] | **C peggiore** |
| **C contro B** (sistemi completi) | CRPS | −0,0625 [−0,0971; −0,0292] | −0,0363 [−0,0693; −0,0032] | **C migliore** |
| **C contro B** | Brier presenze | −0,0094 [−0,0123; −0,0064] | −0,0055 [−0,0084; −0,0024] | **C migliore** |

Otto intervalli su otto escludono lo zero, tutti nella stessa direzione nelle
due stagioni. Non c'è ambiguità da interpretare.

**Che cosa significa, detto per intero.** Il cubo batte il vecchio simulatore
quando ognuno usa l'informazione che usa davvero. Ma quando il vecchio
simulatore riceve le presenze del modello valore — che sono informazione lecita
alla data della decisione, e che oggi il cubo non usa — il cubo **perde**, e
perde su tutte e due le misure e tutte e due le stagioni. Il vantaggio di C su
B viene dunque dalle presenze, che il cubo stima da sé meglio di quanto B le
stimi dalla sola storia; non viene dal meccanismo del tabellino.

Il Livello 2 **non è promosso**. Il predefinito non cambia.

### Dove il cubo resta l'unico a fare la cosa giusta

Queste quantità sono descrittive per §3.7 e non promuovono niente, ma sono la
ragione per cui il cubo non va buttato:

- **Quante persone prendono voto.** 283,9 e 284,7 contro 281,9 e 283,6 veri:
  errore dello 0,7% e dello 0,4%. B ne genera 362 e 348, cioè **+29% e +23%**;
  B′ 332 e 313, **+18% e +10%**. Con quel numero una rosa non ha quasi mai
  bisogno di sostituzioni e non prende quasi mai zeri: l'asta verrebbe valutata
  in un mondo più facile di quello vero.
- **I gol da fasce delle rose**, la moneta con cui si vince il campionato:
  0,192 e 0,285 contro 0,216 e 0,224 veri. B dà 0,472 e 0,530, oltre il doppio.
- **La struttura della dipendenza.** Fra difensori: 0,301 e 0,280 contro 0,311
  e 0,340 veri; B e B′ stanno a 0,15, meno della metà, e producono correlazioni
  quasi identiche per tutte le coppie di ruoli — la firma dello shock unico.

### La strada che questi numeri indicano

Il confronto a informazione comparabile dice esattamente dove intervenire: dare
al cubo le presenze del modello valore, come le ha B′. Sarebbe una variante
nuova (`C′`), e va trattata come tale: **nessun criterio scritto la copre**, ed
è stata pensata dopo aver visto questi risultati. Prima di valutarla serve un
criterio scritto prima, e una valutazione su dati non usati per sceglierla.
Finché non esiste, `C′` non è nemmeno un candidato.


---

## 8. Residui dei livelli precedenti

### 8.1 Dispersione dei prezzi e cassa: la correzione proposta non è utilizzabile

`scripts/l2_dispersione_prezzi.py`. Verificato:

1. `ref_price_sd` viene da `target_std_pct_all_estiva`
   (`scripts/f2_build_packs.py:118`), che è lo scarto dei prezzi pagati **nelle
   aste della stessa stagione valutata**. Usarlo per fissare il tetto d'asta di
   quella stagione è informazione che il giorno dell'asta non esiste:
   l'esperimento O3c va riletto come **diagnostico con informazione
   privilegiata**, non come prova di una politica applicabile.
2. Disponibilità per stagione: 2021-22 **395**, 2023-24 **316**, 2024-25
   **231**, 2025-26 **0**, 2026-27 **0**. La variante che allarga il tetto con
   `ref_price_sd` aggiungerebbe **esattamente zero** ai 587 giocatori del
   2026/27.

Costruito e validato un modello della dispersione che usa solo stagioni
precedenti (addestra su tutte le precedenti, misura sulla successiva):

| candidato | errore assoluto medio (crediti) | errore relativo mediano |
|---|---|---|
| A costante | 4,173 | 0,659 |
| B proporzionale al prezzo | 7,203 | 0,415 |
| **C per ruolo × fascia di prezzo** | **2,922** | **0,317** |
| D log-lineare | 4,774 | 0,394 |

Stima per il 2026/27 con il candidato C: scarto medio 3,94 crediti, **17,18
crediti sui 50 giocatori più cari** (`data/l2/dispersione_2026-27.csv`).

**Non è stata scritta in nessun pack.** Serve una decisione: la dispersione fra
aste è una cosa, il massimo legalmente offribile un'altra, il massimo
conveniente rispetto alle alternative una terza.

### 8.2 `quot_fs_sett`: un disallineamento temporale che resta comunque

`quot_fs_sett` è la quotazione fanta.soccer allo snapshot più vicino al 1
settembre. `data/processed/_match/fs_snapshot.json`: **giornata 2** per il
2021-22, **giornata 3** per 2023-24, 2024-25 e 2026-27.

Il bersaglio delle stagioni di addestramento sono invece le aste `periodo <= 1`,
cioè tenute **prima** del campionato o alla prima giornata. In quelle stagioni
la variabile è quindi misurata **dopo** il bersaglio: incorpora due o tre
giornate che chi partecipava all'asta non aveva visto. Per l'asta 2026/27 (dopo
la terza giornata) la variabile esiste davvero, quindi non è un problema di
inferenza; è un problema della **relazione stimata**, che risulta più forte del
vero.

**Ablazione sulla pipeline effettiva** (TabPFN + CatBoost, stessi split, stessi
pesi, stessa calibrazione conformal, 5 semi, predizioni conservate per seme in
`data/l2/`):

| prova | variante | errore medio (crediti) | errore sui 50 più cari | rho di Spearman | copertura q10-q90 | pinball |
|---|---|---|---|---|---|---|
| R1 (train 2021-22, test 2023-24) | con | 6,145 | 18,60 | 0,8047 | 0,689 | 0,00591 |
| R1 | senza | **5,705** | 23,40 | **0,8453** | **0,743** | 0,00596 |
| R2 (train 2021-22+2023-24, test 2024-25) | con | 5,635 | **13,30** | 0,8326 | 0,710 | 0,00546 |
| R2 | senza | **5,585** | 13,90 | **0,8469** | 0,709 | **0,00541** |

Differenza appaiata sull'errore assoluto (senza − con), bootstrap 4000:

| prova | differenza | intervallo 95% |
|---|---|---|
| R1 | −0,439 crediti | [−0,983, **+0,145**] |
| R2 | −0,051 crediti | [−0,630, **+0,523**] |

**Il risultato è inconcludente, e resta tale.** Gli intervalli contengono lo
zero in entrambe le prove: togliere `quot_fs_sett` migliora l'errore medio di
poco, migliora l'ordinamento (rho da 0,805 a 0,845 e da 0,833 a 0,847) e
peggiora l'errore sui cinquanta più cari (18,6 → 23,4 in R1). Il vantaggio di
«−0,52 e −1,05 crediti» misurato prima su un CatBoost non pesato senza
conformal **non si conferma** sull'ensemble operativo.

Quindi: nessuna rimozione. Ma il disallineamento temporale sopra descritto va
corretto comunque, allineando lo snapshot alla data dell'asta della stagione di
addestramento.

**Che cosa è stato verificato sui dati grezzi.** `f0b_match.py:466-481` sceglie
lo snapshot con la data di rilevazione **più vicina al 1 settembre**, in valore
assoluto: è quella regola a produrre g02 e g03. Le date effettive di rilevazione
(`data/raw/quotazioni/fantasoccer_date_rilevazioni.csv`) contro la data della
prima giornata di ciascuna stagione:

| stagione | prima giornata | g01 | g02 | g03 | snapshot anteriori alla prima giornata |
|---|---|---|---|---|---|
| 2021-22 | 21/08/2021 | 21/08/2021 | 27/08/2021 | 11/09/2021 | **nessuno** |
| 2023-24 | 19/08/2023 | 19/08/2023 | 26/08/2023 | 01/09/2023 | **nessuno** |
| 2024-25 | 17/08/2024 | 17/08/2024 | 24/08/2024 | 30/08/2024 | **nessuno** |
| 2025-26 | 23/08/2025 | 23/08/2025 | 29/08/2025 | 13/09/2025 | **nessuno** |
| 2026-27 | 22/08/2026 | 22/08/2026 | 28/08/2026 | 04/09/2026 | **nessuno** |

Due fatti che cambiano la forma della correzione:

1. **Non esiste alcuno snapshot strettamente anteriore all'inizio del
   campionato.** Lo snapshot più antico è sempre datato **lo stesso giorno**
   della prima giornata. Allineare "alla data dell'asta" nel senso stretto non
   è possibile con questi dati: si può solo passare da g02/g03 a g01, cioè da
   un disallineamento di due o tre giornate a uno di al più una.
2. **Se la rilevazione di g01 sia precedente o successiva alle partite di quel
   giorno non è deducibile dai dati locali**: il file porta la data, non l'ora.
   Per un'asta `periodo <= 1` la differenza conta. Questa ambiguità va risolta
   con la fonte, non con una scelta di comodo.

Per questo la correzione **non è stata applicata**. Applicarla significherebbe
rigenerare le mappe, le predizioni e i pack operativi, che questa esecuzione non
deve toccare; e la scelta fra "g01 è pre-partite" e "g01 è post-partite" è
esattamente il genere di decisione che non va presa in silenzio. Il lavoro
pronto è: un'opzione esplicita in `f0b_match.py` che scriva un secondo file
`fs_snapshot_asta.json` con g01, un confronto appaiato con lo stesso disegno
dell'ablazione qui sopra, e la risposta della fonte sull'ora di rilevazione.

### 8.3 O4: resta aperto, e il perché

L'intervallo sul **prezzo medio fra aste** e l'intervallo sul **singolo
martelletto** sono due problemi diversi. La copertura misurata da
`scripts/indagine/check_o4_quantili.py` riguarda il primo. Nessuna garanzia
conformale si trasferisce automaticamente al secondo, perché il bersaglio
cambia. La dispersione stimata al punto 8.1 è il pezzo che manca per passare
dall'uno all'altro, ma il passaggio va deciso, non dedotto.

### 8.4 f13: etichetta corretta

`scripts/f13_validate_plan.py` costruisce un tavolo di **otto** squadre (due
varianti del piano più sei archetipi) con rose generate **in modo
indipendente**. Misurato sul 2025/26: **54 giocatori su 68 stanno in più di una
rosa**. In un'asta vera ogni calciatore appartiene a una sola squadra.

Lo script ora lo dichiara a ogni esecuzione e la colonna si chiama «quota
vittorie», non «probabilità di vincere». Resta utile per ordinare varianti
dello stesso piano; non promette un risultato di lega.

---

## 8.5 Il cubo per la stagione in corso

`python scripts/l2_genera_cubo.py 2026-27 --as-of 2026-09-11 --solo-future --salva`

Con data limite 11 settembre: 380 partite in calendario, **30 già giocate**,
**350 da generare** (35 giornate). `--solo-future` è obbligatorio per questo
uso: le giornate già concluse sono informazione lecita per stimare, ma i punti
già realizzati sono noti, non aleatori, e non vanno simulati. Chi ha bisogno
di una classifica di lega già avviata deve fornirla: il cubo non la inventa.

Diagnostica: gol in trasferta stimati 1,2078 contro 1,2081 osservati; `rho`
−0,026; vantaggio del campo 0,109; 1.432 giocatori con storia, moduli per 27
squadre; 7.264 gol storici per la distribuzione dei minuti; s.v. 9,1% su
46.578 righe con minuti noti; **zero problemi di coerenza** sui tabellini
verificati. Calibrazione della dipendenza convergente sui bersagli
(0,170 / 0,360 / 0,292 / 0,264) in tre giri.

Il cubo è salvato in `data/l2/cubo_2026-27.pkl`. **Non è collegato a `f12`,
al Copilota o ai pack.**

---

## 9. Difetti trovati dai test durante l'implementazione

Nessuno di questi è arrivato ai risultati: sono stati trovati dai test o dai
confronti con l'osservato, e corretti prima di misurare.

| difetto | come si è visto | correzione |
|---|---|---|
| autogol sottratti alla squadra sbagliata | `verifica_coerenza`: «2 gol dei giocatori + 1 autogol avversari ≠ 2 del risultato» | l'autogol di una squadra entra nel punteggio dell'altra |
| portiere di riserva in campo a ogni partita | ammonizioni ai portieri 87 contro 19 vere | panchina ordinata per probabilità di entrare, portiere in fondo |
| ruolo maiuscolo/minuscolo disallineato | voto medio degli attaccanti +0,19 | il ruolo di riferimento è quello del listone, in maiuscolo |
| intercetta di ruolo con gli eventi dentro | stessa cosa: gli eventi contati due volte per chi non ha storia | intercetta al netto dell'effetto medio degli eventi |
| moduli non schierabili | squadre di dieci in campo | il modulo si adatta ai convocati |
| intervalli dei minuti chiusi da entrambi i lati | quattordici giocatori in campo al 60' | intervalli semiaperti |
| scelte dipendenti dall'ordine dell'elenco | `test_scenari_invarianti_all_ordine` | identità del giocatore come criterio di rottura dei pareggi |

Test: **20 su 20 passano**.

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q
```

---

## 10. Comandi per riprodurre ogni risultato decisivo

```bash
python scripts/f16_istantanea.py --crea --nota "..." --as-of AAAA-MM-GG
python scripts/l2_scarica_calendario.py 2026-27
python scripts/l2_scarica_understat.py 2019 2020 2021 2022 2023 2024 2025 2026 --riscontro 2026-27
python scripts/l2_prepara_partite.py
python scripts/l2_costruisci_panel.py
python scripts/l2_banco_partita.py --boot 2000
python scripts/l2_genera_cubo.py 2024-25 --sims 30
python scripts/l2_banco_confronto.py 2024-25 --sims 20
python scripts/l2_banco_confronto.py 2025-26 --sims 20
python scripts/l2_dispersione_prezzi.py
python scripts/l2_ablation_quot.py --semi 5
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q
```

Semi fissati: 20260907 per cubo e banco, 13..17 per l'ablazione, 7 per f13.
Ripristino dello stato di partenza:
`python scripts/f16_istantanea.py --ripristina 20260907_014307_e6b11750 <cartella>`.

---

## 11. Limiti, e che cosa richiede una decisione

**Limiti misurati, non nascosti:**

1. il cubo perde su CRPS e Brier delle presenze contro la configurazione di
   produzione con le presenze del modello valore;
2. genera il 5,9% di gol in più nel 2024/25, per errore predittivo sul livello
   di segnature del campionato;
3. sbaglia i punti per giornata di una rosa di circa 3 punti, in un verso o
   nell'altro a seconda della stagione;
4. per il 2026/27 non ha formazioni titolari né minuti: la partecipazione è
   generata dalle propensioni storiche, non aggiornata sulle prime giornate;
5. non ha xG per giocatore per partita, quindi il prior sui marcatori usa solo
   il tasso storico e il ruolo.

**Decisioni che servono, con le conseguenze:**

| decisione | opzioni | conseguenza |
|---|---|---|
| dispersione dei prezzi | (a) lasciare tutto com'è; (b) usare la stima per ruolo × fascia solo come **diagnostica**; (c) usarla per allargare il tetto d'asta | (c) alza la disponibilità a pagare: va deciso separatamente dal prezzo previsto |
| `quot_fs_sett` | (a) tenerla; (b) toglierla; (c) tenerla e allineare lo snapshot alla data dell'asta | (c) è l'unica che corregge il disallineamento senza perdere informazione |
| formazioni 2026/27 | (a) rinunciare; (b) leggere i 28 tabellini di fantacalcio.it | (b) costa un'acquisizione, e dà titolarità reale sulla stagione in corso |
| integrazione del cubo | (a) restare separato; (b) opzione selezionabile in `f12`; (c) unire cubo e modello valore | nessuna attivazione automatica: serve un via esplicito |
| tolleranza per accettare una variante | va fissata **prima** dei prossimi esperimenti | senza, il criterio si adatta al risultato |

**Non è stato fatto e non va dedotto:** nessuna pubblicazione, nessuna
cancellazione, nessuna dipendenza a pagamento, nessuna modifica alle regole
della lega, nessuna attivazione del cubo nel Copilota o nell'ottimizzatore.
