# Punto di ripresa corrente — FantaOracle

**Aggiornato il 9 settembre 2026, fine del ciclo di correzioni.** Questo è il
puntatore corrente. `RIPRESA_L2_L3.md` descrive la pausa del 7 settembre ed è
conservato come storico: alcune sue conclusioni sono state ritrattate, e sono
marcate lì.

Regole della sessione che restano valide: criteri scritti **prima** degli
esperimenti; un test fallito non si risolve indebolendo il test; una soglia non
si sposta dopo aver visto i risultati; pack operativi, Copilota, bot
predefinito e mirror GitHub non si toccano; niente push senza permesso.

---

## 1. Dove siamo

| fase | stato | dove leggerlo |
|---|---|---|
| R1 contratto temporale | conclusa | `reports/PROTOCOLLO_v2.md` §16.1 |
| R2 adattatore delle presenze | conclusa | §16.2 |
| R3 distribuzione campionata | conclusa | §16.3 |
| R4 inferenza del fattoriale | conclusa e verificata | §18, §19, §20 |
| ciclo del 9/9: correzioni ai difetti riprodotti | concluso | `reports/CICLO_20260909.md` |
| progressivo | **percorso verificato, esperimento non concluso** | `CICLO_20260909.md` §2, §5 |
| L3, L4 | **sospesi** | — |

Suite, comando completo — servono tutti e tre i pezzi:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONIOENCODING=utf-8 PYTHONPATH=src python -m pytest tests/ -q
```

Senza `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` un plugin di terze parti (`fugue_test`)
esplode all'autoload perché manca `pkg_resources`; senza `PYTHONPATH=src` e
senza il target `tests/` la collezione fallisce con 28 errori. Non è un problema
del progetto, ma il comando va scritto per intero.

---

## 2. Il risultato corrente del banco

A informazione comparabile **il cubo perde**. Non è un margine incerto: gli
intervalli two-way escludono lo zero su entrambe le stagioni, entrambe le
misure, entrambi i punteggi.

| confronto | 2024-25 | 2025-26 |
|---|---:|---:|
| `C1 − I1`, CRPS empirico | +0,097268 | +0,050467 |
| `C1 − I1`, CRPS equo | +0,105028 | +0,058438 |
| interazione, CRPS empirico | +0,160866 | +0,071504 |

L'interazione positiva significa: **il cubo trae meno dalle presenze del
modello** di quanto ne tragga il simulatore per giocatore.

Il Livello 2 resta **non promosso**.

### Comandi che li riproducono

```bash
PYTHONPATH=src python scripts/l2_banco_confronto.py 2024-25 --sims 30 --semi 8
PYTHONPATH=src python scripts/l2_banco_confronto.py 2025-26 --sims 30 --semi 8
PYTHONPATH=src python scripts/l2_inferenza_banco.py --verifica
```

Il terzo comando rifà l'inferenza dalle sole osservazioni conservate, senza
rigenerare: scarto massimo `0,00e+00`.

### Artefatti, con impronte

| sha256[:16] | file |
|---|---|
| `8c05747139050052` | `data/l2/banco_verdetto_2024-25.csv` |
| `8225b4d811ea0aa4` | `data/l2/banco_verdetto_2025-26.csv` |
| `e4d52aebeebab653` | `data/l2/banco_osservazioni_2024-25.parquet` |
| `96e72925fb5459d8` | `data/l2/banco_osservazioni_2025-26.parquet` |
| `6165d893f5739e8a` | `data/l2/banco_semi_2024-25.json` |
| `1f5f420600985ad0` | `data/l2/banco_semi_2025-26.json` |

**Provenienza incompleta**, dichiarata: sono stati scritti prima del contratto
delle esecuzioni e non portano un identificativo di esecuzione. Le impronte
identificano i byte, non certificano l'esperimento. Si chiuderebbe solo
rigenerandoli, che è un'esecuzione lunga e non autorizzata in questo ciclo.

---

## 3. Che cosa è cambiato il 9 settembre

Dettaglio in `reports/CICLO_20260909.md`. In breve:

- **verificatore**: 12 alterazioni che davano `RIPRODOTTO` ed exit 0 adesso
  falliscono. Prove scritte prima della correzione;
- **destinazioni**: ogni esecuzione ha la sua cartella, le prove hanno una
  radice separata, una destinazione occupata è rifiutata, la scrittura è
  atomica, il puntatore `corrente` si aggiorna solo dopo una verifica passata;
- **progressivo**: la prima origine viene davvero rigenerata (prima il
  controllo era una tautologia, e la correzione dichiarata nella sessione
  precedente non era mai stata scritta su disco); finestre per data effettiva;
  filtro del panel in un punto solo — ma il tempo entra anche da
  `costruisci_modello_partita` e `partite_di_addestramento`, e adesso e'
  dichiarato; campionamento proporzionale alle finestre; previsioni conservate;
- **affermazioni statistiche**: gli scenari sono incorrelati (verificato
  empiricamente), il rumore è ricampionabile, e c'è un emendamento prospettico
  sulla precisione computazionale che non tocca i verdetti pubblicati;
- **diagnosi delle presenze**: il bersaglio ha errore assoluto medio 0,1453
  contro l'osservato, il cubo lo porta a **0,1749**, mentre senza bersaglio sta
  a 0,2530. I tre numeri sono nel blocco `contro_osservato` di
  `presenze_diagnosi_2024-25.json`, marcato come **diagnostico**: usa la
  stagione valutata e non entra in nessun fit;
- **revisione indipendente**: 16 rilievi, tutti accolti — 11 corretti nel codice
  con 15 prove nuove, 5 nel testo. Elenco in `reports/CICLO_20260909.md`
  §Revisione.

---

## 4. Da dove ripartire, in ordine

1. **Decidere sulla calibrazione congiunta delle presenze.**
   `reports/PROPOSTA_CALIBRAZIONE_PRESENZE.md` ha forma, costo stimato, cinque
   criteri di accettazione fissati prima e tre decisioni che non sono mie. La
   prima è quella che conta: se il bersaglio è più accurato del cubo sulle
   presenze, a che cosa serve il cubo.
2. **Se si vuole concludere l'esperimento del progressivo**: il percorso è
   verificato, mancano le risorse. Con 8 scenari e 2 semi l'esito è «non
   misurabile». Serve dimensionare `R` e `m` **prima**, con
   `repliche_necessarie_prospettiche`.
3. **Se si vuole un progressivo che sia una previsione operativa**: serve
   condizionare le catene sullo stato osservato all'origine. Oggi
   `generatore.genera` risimula il passato con il nuovo fit. È un meccanismo
   che non esiste.
4. **L3 e L4** restano sospesi. Le vecchie conclusioni L3 sono ritrattate:
   vedi il blocco registrato nel manifesto.

### Prove piccole, per ricominciare senza impegnarsi

```bash
PYTHONPATH=src python scripts/l2_diagnosi_presenze.py 2024-25 --sims 12 --semi 3 --prova
PYTHONPATH=src python scripts/l2_progressivo.py 2024-25 --origini 1,20 --sims 8 --semi 2 --righe 1200 --prova
```

Entrambe scrivono sotto `data/l2/prove/`, che è una radice separata da quella
dei risultati: non possono toccare niente di pubblicato.

---

## 5. Che cosa NON è vero, e va detto

- **«Non c'è differenza» non è «sono equivalenti».** Nessun margine di
  equivalenza è stato dichiarato, e non è mio da dichiarare.
- **La diagnosi delle presenze non dimostra da sola perché `C1` perda.** Mostra
  un meccanismo misurato e coerente; non ha isolato il contributo delle altre
  componenti.
- **Il refit a origini mobili non è una previsione progressiva operativa**:
  è un confronto fra due refit incondizionati, e i bracci si chiamano così.
- **Il ciclo del 9 settembre non ha prodotto nessun risultato nuovo sul
  merito**: ha corretto strumenti e misurato un meccanismo. Il verdetto del
  banco è quello di R4, invariato.
- **Il puntatore `corrente` esiste ma non è collegato**: nessuno script chiama
  `promuovi_a_corrente`, e sul disco non ci sono né `data/l2/corrente` né
  `data/l2/esecuzioni`. Gli artefatti correnti stanno ancora ai nomi piatti.
- **Il controllo della prima finestra, sul percorso reale, è un test di
  determinismo del generatore**, non del contratto temporale: confronta
  `genera(X, s)` con `genera(X, s)`. La prova che può fallire usa un generatore
  alterato, ed è a un livello più debole.
