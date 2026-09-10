# Caccia ai difetti — lente DATI (bundle, eleggibilità, pack)

Sessione di sola lettura sul progetto `fantabot`, 10 settembre 2026.
Porta di prova usata: 8795, sempre con `--ledger` esplicito; nessun processo lasciato vivo.
Sessioni vere (`ledger_1788290734.json`, `ledger_1788548783.json`) mai aperte.

Artefatti letti:

- `scripts/f4_eleggibilita.py`
- `data/copilot/eleggibilita_2026-27.json` (costruito il 2026-09-10T01:21:04)
- bundle `...\fonti_preasta\20260909T223517Z\parsed\*.csv` (acquisito 2026-09-09T22:35:18Z)
- `data/packs/pack_2026-27.pkl` — impronta `db2584ea408b…`, 587 giocatori; **coincide** con l'impronta registrata dentro l'eleggibilità (verificato con sha256)
- `data/raw/voti/voti_2026-27.csv`, `data/raw/calendario/calendario_2026-27.csv`
- per il collegamento con l'uso in asta: `scripts/f10_copilot.py`, `viz/copilot.html`

Script di riproduzione (ognuno autonomo, esce 1 se il difetto c'è):
`repro_dati_1.py` … `repro_dati_6.py` nella stessa cartella. Tutti e sei eseguiti: **exit 1**.

---

## Riepilogo dei rilievi

| # | rilievo | gravità | tipo | prova |
|---|---|---|---|---|
| D1 | infortunati mai segnalati sul giocatore: entrano nel piano e ricevono «rilancia» | alta | riprodotto | `repro_dati_2.py` |
| D2 | i 7 attivi del listone assenti dal pack non si possono martellare: budget avversari sbagliati | alta | riprodotto | `repro_dati_1.py` |
| D3 | 37 «prezzi di mercato» su 379 sono dell'asta 2025-26, indistinguibili | media | riprodotto | `repro_dati_5.py` |
| D4 | 54 giocatori con prezzo atteso del piano ≤ 1/3 del mercato, tutti nella fascia media | media | riprodotto | `repro_dati_6.py` |
| D5 | `GIORNATA_CORRENTE = 4` fisso: due stime di rientro bollate come «giornata già giocata» quando la 4ª comincia l'11/9 | media | riprodotto | `repro_dati_4.py` |
| D6 | pack senza i voti della 3ª giornata (4-7/9), già giocata | bassa | riprodotto | `repro_dati_3.py` |

---

## D1 — Gli infortunati non si vedono (alta)

`viz/copilot.html` contiene **zero** riferimenti al campo `indisponibile` del singolo giocatore
(regex `\.indisponibile(_nota)?\b` → 0 occorrenze). L'unica riga che ne parla è la 792:

```
if(el.indisponibili) righe.push(`<b>indisponibili oggi</b> ${el.indisponibili} (restano comprabili)`);
```

cioè il solo conteggio complessivo (54). `GUIDA_ASTA.md` riga 52 promette il contrario:
«Un giocatore **indisponibile** resta comprabile e viene segnalato».

Eseguito con tavolo da 10 squadre e 500 crediti (`repro_dati_2.py`):

```
/copilot/plan: 25 target, 3 indisponibili:
  ruolo=D Solet       prezzo_atteso=19.8 titolare_di_piano=True  rientro=None
  ruolo=C Locatelli   prezzo_atteso=11.9 titolare_di_piano=False rientro=2027-01
  ruolo=A Varela G.   prezzo_atteso=5.7  titolare_di_piano=False rientro=2026-10-05
/copilot/advice McTominay: azione=rilancia max_consigliato=38 indisponibile_nel_json=True
/copilot/advice Locatelli: azione=rilancia max_consigliato=13 indisponibile_nel_json=True
```

Testi della fonte:

- Solet (6956, UDI, D): «il 7 settembre contro la Lazio costretto al cambio per un problema muscolare… Di certo out per lunedì»; **titolare di piano a 19.8 crediti**;
- Locatelli (827, JUV, C): «rottura del menisco esterno del ginocchio. Verrà operato… Lungo stop», stima rientro **gennaio 2027**;
- McTominay (4777, NAP, C): rientro stimato **15/10**, mercato 59.95, il Copilota dice `rilancia` fino a 38.

Il pack è del 6 settembre: le previsioni non conoscono nessuno di questi infortuni, che arrivano
solo dal bundle del 9. Il dato c'è nell'API e muore prima dello schermo.

## D2 — I 7 attivi fuori dal pack non sono registrabili (alta)

| id | nome | sq | ruolo | qt_a | fvm | mercato | probabili G4 |
|---|---|---|---|---|---|---|---|
| 795 | El Shaarawy | GEN | C | 7.0 | 20.0 | 11.66 | panchina 35 % |
| 6047 | Ehizibue | GEN | D | 4.0 | 10.0 | – | ballottaggio 55 % |
| 7628 | Sierro | PAR | C | 1.0 | 1.0 | – | ballottaggio 60 % |
| 6319 | Leite | LAZ | D | 6.0 | 14.0 | – | panchina 25 % |
| 2169 | Rodriguez R. | TOR | D | 5.0 | 12.0 | – | panchina 25 % |
| 7627 | Enem | BOL | A | 2.0 | 4.0 | – | panchina 15 % |
| 7626 | Pompei | ATA | P | 1.0 | 1.0 | – | panchina 1 % |

Nessuno dei sette esiste nel pack con un altro identificativo (cercati per nome: 0 riscontri).
Che restino fuori dai consigli è dichiarato in `RIPRESA_ASTA.md`; **che non si possano registrare
non lo è**. Riprodotto:

```
POST /copilot/hammer player_id=795 price=12 -> {'ok': False, 'err': 'giocatore inesistente'}
GET  /copilot/players?q=Shaarawy              -> []
budget di B1 dopo l'acquisto reale da 12: 500 (atteso 488)
```

`f10_copilot.py:715` rifiuta ogni `player_id` non presente in `PACK.players`, e la pagina martella
solo ciò che la ricerca (`pool()`) restituisce: nessuna scorciatoia manuale. Se un avversario li
compra, il suo budget e i suoi slot restano sbagliati per il resto della serata — e ogni
`max_bid` calcolato su quel budget è sbagliato con lui.

## D3 — Prezzi di mercato di due stagioni mescolati (media)

`f4_eleggibilita.py` copia `p500_10sq` ignorando la colonna `stagione_prezzo`:

| stagione dichiarata dalla fonte | righe con prezzo e player_id |
|---|---|
| 2026-27 | 342 |
| 2025-26 | 37 |
| totale esposto in `prezzo_mercato_10sq_500` | 379 |

I 37 più cari fra quelli vecchi:

| id | nome | sq | ruolo | prezzo esposto (asta 2025-26) |
|---|---|---|---|---|
| 4970 | Messias | GEN | C | 25.03 |
| 5319 | Sohm | VEN | C | 21.41 |
| 333 | Cataldi | LAZ | C | 20.72 |
| 4349 | Nicolussi Caviglia | PAR | C | 19.99 |
| 7318 | Gandelman | LEC | C | 19.11 |
| 5007 | Ilic | LEC | C | 19.08 |
| 7127 | Addai | COM | C | 15.83 |
| 7146 | Touré I. | MON | C | 15.43 |
| 6170 | Gineitis | TOR | C | 14.84 |
| 7068 | Vitik | BOL | D | 14.57 |
| 6054 | Moro N. | BOL | C | 14.31 |
| 6629 | Dele-Bashiru | LAZ | C | 14.31 |
| 6917 | Masini | FRO | C | 14.13 |
| 6005 | Ilkhan | TOR | C | 10.60 |
| 7255 | Britschgi | PAR | D | 7.31 |

La nota `semantica_prezzo` spiega l'aggregazione per numero di squadre e budget, **non** dice che
qualche prezzo è dell'anno prima (`'2025' in semantica_prezzo` → False).
Oggi il valore esce da `/copilot/advice`, `/copilot/state` e `/copilot/export` ma la pagina non lo
stampa: il danno immediato è limitato a chi legge l'export.

Distribuzione dei 379 prezzi: min 0.50, q25 4.69, mediana 14.42, q75 21.31, max 163.06 (Malen),
somma 6715 crediti. Fasce: <5 → 102, 5-15 → 94, 15-30 → 127, 30-60 → 42, 60-120 → 12, ≥120 → 2.
146 acquistabili non hanno prezzo di mercato.

## D4 — Prezzo atteso del piano contro prezzo di mercato (media)

Il piano usa `q50 × calore` come prezzo atteso (`f10_copilot.py:457`). Su 378 acquistabili con
prezzo di mercato, **54** hanno mercato ≥ 3× il q50; solo **3** il contrario
(Trepy 0.53 vs 2.15, Aboukhlal 0.50 vs 1.73, Candé 0.53 vs 1.65). I 20 scarti maggiori:

| id | nome | ruolo | sq | q50 | mercato | rapporto |
|---|---|---|---|---|---|---|
| 4970 | Messias | C | GEN | 1.55 | 25.03 | 16.15 |
| 5007 | Ilic | C | LEC | 1.38 | 19.08 | 13.83 |
| 333 | Cataldi | C | LAZ | 1.78 | 20.72 | 11.64 |
| 6170 | Gineitis | C | TOR | 1.37 | 14.84 | 10.83 |
| 4349 | Nicolussi Caviglia | C | PAR | 1.92 | 19.99 | 10.41 |
| 5319 | Sohm | C | VEN | 2.22 | 21.41 | 9.64 |
| 7318 | Gandelman | C | LEC | 2.02 | 19.11 | 9.46 |
| 6054 | Moro N. | C | BOL | 1.63 | 14.31 | 8.78 |
| 22 | De Roon | C | ROM | 1.45 | 12.71 | 8.77 |
| 7198 | Piotrowski | C | UDI | 1.90 | 15.45 | 8.13 |
| 6917 | Masini | C | FRO | 1.87 | 14.13 | 7.56 |
| 7127 | Addai | C | COM | 2.10 | 15.83 | 7.54 |
| 2528 | Matic | C | SAS | 1.68 | 11.17 | 6.65 |
| 6005 | Ilkhan | C | TOR | 1.62 | 10.60 | 6.54 |
| 5036 | Caqueret | C | COM | 2.06 | 13.45 | 6.53 |
| 7146 | Touré I. | C | MON | 2.45 | 15.43 | 6.30 |
| 5504 | Coulibaly L. | C | LEC | 1.99 | 12.45 | 6.26 |
| 7469 | Bracaglia | D | FRO | 2.27 | 14.08 | 6.20 |
| 6827 | Njie | C | FIO | 1.49 | 9.01 | 6.05 |
| 6020 | Ellertsson | C | GEN | 1.78 | 10.60 | 5.96 |

Non è un errore di scala: la somma dei 250 q50 più alti vale 5091 crediti contro i 5000 della lega
(P 430, D 974, C 1698, A 1990), quindi il modello è calibrato **in totale** e sposta i crediti
verso l'alto della lista. Effetto pratico: il piano corrente mette a bilancio Coulibaly L. a
2.0 crediti mentre il mercato dice 12.45; quando la fascia media costa dieci volte tanto, gli slot
di riempimento mangiano budget che il piano aveva già promesso altrove. 20 dei 54 sono
dell'insieme D3 (prezzo 2025-26), quindi una parte dello scarto è un artefatto della stagione
sbagliata, non del modello.

## D5 — «giornata già giocata» applicata a una giornata futura (media)

`f4_eleggibilita.py`: `GIORNATA_CORRENTE = 4  # le probabili del bundle sono della 4a`, e ogni
stima `G≤4` viene marcata «quasi certamente il parser ha letto la giornata dell'evento».
Il calendario dice però che la 4ª giornata comincia l'**11/9/2026**: al 10/9 le giornate concluse
sono tre.

| id | nome | stima | 1ª partita di quella giornata | testo della fonte | giudizio |
|---|---|---|---|---|---|
| 2766 | Zaniolo | G1 | 2026-08-22 | «nella 1a giornata contro il Como è uscito… stop di circa 25 giorni» | marcatura **corretta** |
| 4364 | Gaetano | G4 | 2026-09-11 | «squalificato nella 4a giornata di campionato» | falso allarme: G4 non è giocata |
| 5888 | Casadei | G4 | 2026-09-11 | «fuori causa contro Fiorentina e Sassuolo… da valutare in vista di lunedì contro la Roma» | falso allarme |

Gaetano (209.1 di `value`, top-100) è squalificato **per** la 4ª: l'informazione utile all'asta è
esatta e il Copilota la presenta come inattendibile.

## D6 — Il pack non ha i voti della 3ª giornata (bassa, limite già dichiarato)

| giornata | date (calendario) | giocata al 10/9 | voti nel pack |
|---|---|---|---|
| 1 | 22-24/8 | sì | sì (290 voti) |
| 2 | 28-31/8 | sì | sì (292 voti) |
| 3 | 4-7/9 | sì | **no** |
| 4 | 11-14/9 | no | no |

`data/raw/voti/voti_2026-27.csv` contiene 638 righe, solo G1 e G2; `pack.votes_by_g` e
`pack.voti_by_g` hanno le stesse due giornate piene su 38.
`RIPRESA_ASTA.md` e `GUIDA_ASTA.md` dichiarano «voti fermi al 1° settembre»: il difetto non è
nascosto, ma sono comunque 10 partite su 30 assenti dal modello che stasera fissa i tetti.

---

## Risposte alle domande poste

### (1) I 63 esclusi «fuori Serie A»: falsi positivi? — **nessuno**

Confronto fuzzy (difflib, ratio ≥ 0.85) di ciascuno dei 63 contro i 531 attivi: 4 riscontri, tutti
persone diverse.

| escluso | riscontro fuzzy | ratio | verdetto |
|---|---|---|---|
| 5672 Dia (LAZ, A) | 6967 Diao (COM, A) | 0.857 | omonimia parziale, giocatori distinti |
| 7164 Perez M. (LEC, D) | 6994 Perez K. (VEN, C) | 0.857 | iniziali diverse |
| 7468 Gelli J. (FRO, D) | 6241 Gelli F. (FRO, C) | 0.857 | due Gelli nello stesso club, iniziali diverse |
| 7470 Oyono J. (FRO, D) | 6238 Oyono A. (FRO, D) | 0.857 | due Oyono nello stesso club, iniziali diverse |

Tre controlli incrociati confermano l'esclusione dei 63, senza uscire dal bundle:

- **0** dei 63 compare in `probabili.csv` (471 righe, 4ª giornata, 20 squadre);
- **0** compare in `indisponibili.csv`;
- **0** ha un prezzo in `prezzi_identita.csv`; il fornitore di prezzi li elenca con squadra
  «Estero» (verificato per LEAO, LUKAKU, MORATA, GIMENEZ, DI GREGORIO, ROMAGNOLI, DJIMSITI,
  ANGELINO in `prezzi_asta_2026-27.csv`).

`coerenza_bundle` è vuota in entrambe le voci (nessun id marcato fuori e insieme attivo, nessun id
del completo né attivo né fuori). Il filtro è sano: 63 esclusi = 594 − 531.

### (2) I 7 «attivi_senza_previsione» — vedi D2

Rilevanti stasera: El Shaarawy (mercato 11.66), Sierro (ballottaggio 60 %), Ehizibue
(ballottaggio 55 %). Nessuno è un titolare da fascia alta, ma tutti e tre verranno chiamati.

### (3) Coerenza identificativi

| confronto | valore |
|---|---|
| id nel pack | 587 |
| id nel listone completo | 594 |
| id nel listone attivi | 531 |
| attivi **non** nel pack | 7 |
| pack **non** nel listone completo | 0 |
| pack non fra gli attivi | 63 (esattamente i fuori Serie A) |
| pool acquistabile (attivi ∩ pack) | 524 |

Cioè: `587 = 524 + 63`, `594 = 531 + 63`, `531 = 524 + 7`. I `player_id` del bundle sono le stesse
chiavi di `pack.players` (nessuna normalizzazione necessaria). L'impronta del pack registrata
nell'eleggibilità coincide con il file su disco.

Unica sbavatura: `conteggi.con_prezzo_di_mercato` vale 378, ma `prezzo_mercato_10sq_500` espone
379 voci — la differenza è El Shaarawy (795), che ha un prezzo di mercato e non è acquistabile.

### (4) I 54 indisponibili

Ordinati per `value` del pack; «TOP100» = fra i primi 100 acquistabili per `value`.

| id | nome | ruolo | sq | tipo | rientro (euristica) | value | top100 |
|---|---|---|---|---|---|---|---|
| 4777 | McTominay | C | NAP | infortunio | 2026-10-15 | 249.7 | TOP100 |
| 7351 | Santos A. | A | NAP | infortunio | – | 232.9 | TOP100 |
| 827 | Locatelli | C | JUV | infortunio | 2027-01 | 224.7 | TOP100 |
| 2766 | Zaniolo | C | UDI | infortunio | G1 (sospetta) | 221.7 | TOP100 |
| 7523 | Varela G. | A | MON | infortunio | 2026-10-05 | 215.9 | TOP100 |
| 2167 | Orsolini | C | BOL | infortunio | 2026-09-25 | 215.5 | TOP100 |
| 6666 | Bernabé | C | PAR | infortunio | – | 215.3 | TOP100 |
| 6956 | Solet | D | UDI | infortunio | – | 215.3 | TOP100 |
| 4364 | Gaetano | C | ATA | **squalifica** | G4 (marcata sospetta, ma G4 è futura) | 209.1 | TOP100 |
| 572 | Meret | P | NAP | infortunio | – | 194.9 | TOP100 |
| 5735 | Volpato | C | SAS | infortunio | 2026-10-05 | 191.3 | |
| 7198 | Piotrowski | C | UDI | infortunio | 2026-10-25 | 183.9 | |
| 5029 | Geubbels | A | LEC | infortunio | – | 168.6 | |
| 7253 | Bella-Kotchap | D | VEN | infortunio | 2026-10-05 | 167.5 | |
| 2188 | Marusic | D | LAZ | infortunio | 2026-10-05 | 167.1 | |
| 6434 | Yildiz | A | JUV | infortunio | – | 162.6 | |
| 5888 | Casadei | C | TOR | infortunio | G4 (marcata sospetta, ma G4 è futura) | 160.7 | |
| 7036 | Bakola | C | SAS | infortunio | – | 160.4 | |
| 2832 | Boga | A | JUV | infortunio | – | 159.0 | |
| 4459 | Rovella | C | LAZ | infortunio | 2026-10-08 | 152.8 | |
| 6629 | Dele-Bashiru | C | LAZ | infortunio | 2026-09-15 | 150.5 | |
| 6925 | Palma | D | UDI | infortunio | 2026-09-15 | 136.4 | |
| 5562 | Thuram K. | C | JUV | infortunio | 2027-01 | 128.4 | |
| 7536 | Diallo O. | C | PAR | infortunio | G5 | 122.7 | |
| 2741 | Pessina | C | MON | infortunio | 2026-11-05 | 111.5 | |
| 4374 | Walukiewicz | D | SAS | infortunio | 2026-09-20 | 105.4 | |
| 6225 | El Azzouzi O. | C | BOL | infortunio | 2026-09-20 | 104.8 | |
| 4349 | Nicolussi Caviglia | C | PAR | infortunio | 2026-11 | 104.0 | |
| 333 | Cataldi | C | LAZ | infortunio | 2026-09-15 | 99.4 | |
| 4401 | Gabbia | D | MIL | infortunio | – | 97.2 | |
| 6717 | Koné I. | C | SAS | infortunio | 2026-12 | 97.1 | |
| 2724 | Buongiorno | D | NAP | infortunio | 2026-11-15 | 88.8 | |
| 7478 | Franjic | D | VEN | infortunio | 2026-12-15 | 82.8 | |
| 7260 | Ziolkowski | D | MON | infortunio | G5 | 81.6 | |
| 5527 | Zanoli | D | UDI | infortunio | 2026-10 | 73.9 | |
| 5449 | Parisi | D | FIO | infortunio | 2026-11 | 71.1 | |
| 6046 | Hien | D | ATA | infortunio | 2026-10-05 | 64.5 | |
| 7127 | Addai | C | COM | infortunio | 2026-09-20 | 59.7 | |
| 6822 | Ekhator | A | JUV | infortunio | 2026-10-25 | 57.9 | |
| 7312 | Arizala | D | UDI | infortunio | 2026-10-08 | 55.4 | |
| 4387 | Adorante | A | VEN | infortunio | 2026-10 | 43.8 | |
| 6985 | Candé | D | SAS | infortunio | 2026-09-15 | 41.8 | |
| 6673 | Sverko | D | VEN | infortunio | 2026-10-25 | 37.5 | |
| 5918 | Sulemana K. | A | ATA | infortunio | 2026-10-05 | 34.3 | |
| 6640 | Felici | C | CAG | infortunio | 2027-03 | 32.2 | |
| 5880 | Ciurria | C | MON | infortunio | – | 30.3 | |
| 6980 | Venturino | C | GEN | infortunio | – | 26.8 | |
| 6219 | Boloca | C | SAS | infortunio | – | 26.8 | |
| 7162 | Giovane | A | NAP | infortunio | 2026-10-05 | 25.7 | |
| 6809 | Marianucci | D | NAP | infortunio | 2026-11-09 | 21.7 | |
| 7125 | Idrissi R. | D | CAG | infortunio | 2026-10-25 | 15.2 | |
| 7156 | Pieragnolo | D | SAS | infortunio | 2026-10 | 13.6 | |
| 6039 | Cabal | D | JUV | infortunio | 2026-09-20 | 13.0 | |
| 7317 | Trepy | A | CAG | infortunio | G5 | 11.8 | |

Dieci dei 54 sono nella top-100 per `value`; 53 infortuni e una squalifica (Gaetano).
Le tre stime marcate sospette sono Zaniolo (G1, marcatura giusta), Gaetano e Casadei (G4,
falsi allarmi: vedi D5).

### (5) `prezzo_mercato_10sq_500` — vedi D3 e D4

### (6) Date e giornate

- Calendario `data/raw/calendario/calendario_2026-27.csv`, 380 partite, acquisito il 2026-09-07:
  G1 22-24/8, G2 28-31/8, G3 4-7/9, G4 11-14/9, G5 18-20/9, poi salto a G6 10-12/10 (sosta).
- **Giornate concluse al 10/9/2026: tre** (G1, G2, G3). Nell'istantanea del 7/9 la colonna
  `giocata` segna 10, 10 e 8 partite: le due della sera del 7 non erano ancora registrate.
- Voti nel pack e in `data/raw/voti/voti_2026-27.csv`: **solo G1 e G2** (638 righe, 290 + 292 con voto).
- Le probabili del bundle sono della **4ª**, coerenti con il calendario (comincia l'11/9).
  È il `GIORNATA_CORRENTE = 4` di `f4_eleggibilita.py` a essere fuori posto, non le probabili.

---

## Scartati (visti, non riportati come rilievo)

- `ELEGGIBILITA` non viene ricaricata quando il ledger impone una stagione diversa da quella della riga di comando (`f10_copilot.py` ~866: ricarica solo `PACK`): stasera la stagione è una sola.
- `conteggi.con_prezzo_di_mercato` = 378 contro 379 prezzi esposti (El Shaarawy, non acquistabile): cosmetico.
- 51 collegamenti su 379 hanno `source_roles_disagree = True`: il ruolo Classic del listone resta quello usato, la discordia riguarda solo il fornitore dei prezzi.
- 63 esclusi invisibili anche alla ricerca `/copilot/players`: se uno venisse davvero chiamato all'asta la UI non lo troverebbe, ma sono fuori dal listone del banditore e il martelletto via API li accetta comunque.
- `exp_points` ha 438 valori distinti su 587 con code piatte (118.0 ripetuto 60 volte): non entra nei tetti, che usano `q10/q50/value`.
- Somma dei prezzi di mercato dei 250 più alti = 6273 crediti contro i 5000 della lega: conferma che la colonna del fornitore non è confrontabile uno a uno, cosa già scritta in `semantica_prezzo`.
- `data/copilot/prove/ledger_w1_8795.json` creato dal server di prova (comando fornito dall'orchestratore); nessun altro file del progetto toccato.
