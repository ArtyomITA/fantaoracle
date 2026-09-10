# Banco prezzi di mercato: politiche del bot B contro un tavolo che paga il mercato

Generato il 2026-09-10 06:37 - semi 36 (0..35) - politiche P0, P1, P2, P3, P4 - time_limit MILP 5 s - aste totali 180 - minuti totali 13.4

Pack di lavoro `pack.pkl` (copia locale), impronta sha256 `db2584ea408b...`: coincide con quella attesa `db2584ea408b`, il pack non e' cambiato durante il banco. Pool: 524 giocatori (pack meno i 63 fuori Serie A), di cui 378 con prezzo di mercato di riferimento.

Nota: alla generazione di questo report il pack del progetto `data/packs/pack_2026-27.pkl` ha impronta `202c4299d98c...`, **diversa** da quella su cui il banco ha girato. La catena di rigenerazione lo ha sostituito mentre le aste erano in corso: e' esattamente il motivo per cui il banco lavora su una copia congelata. Tutte e 180 le aste hanno visto lo stesso pack `db2584ea408b`, quindi il confronto fra politiche e' valido; i valori assoluti vanno riferiti a quel pack, non a quello nuovo.

## Disegno

Tavolo di 10 squadre: noi (bot B, variante in prova) + 6 bot di mercato (valutazione privata = prezzo di mercato x lognormale(0, 0.25); senza prezzo di mercato max(1, q50*1.3) x lognormale(0, 0.35); disciplina di reparto: riempiti 2/3 degli slot di un ruolo la valutazione su quel ruolo si dimezza; nomination a caso fra i 25 con valutazione piu' alta del ruolo corrente) + 3 CBot con hint_prices = prezzi di mercato (profili informato, stars_scrubs, medio). Pool = giocatori del pack meno i 63 esclusi fuori Serie A. Stessi semi per tutte le politiche; il seme fissa il motore e gli avversari, il nostro bot usa un Random separato.

Politiche: P0 attuale; P1 prezzi del piano = prezzo di mercato dove esiste; P2 = P1 + heat calcolato solo sui q50 >= 15; P3 = P2 + tetto sui target del piano alzato a 1.05 x prezzo di mercato x heat; P4 = prezzi del piano 0.5 mercato + 0.5 q50*heat, heat come P2, tetti come P0.

## Medie per politica (media +/- errore standard)

| politica | objective | somma value | residuo | slot vuoti | spesa top3 | target persi | rank obj | heat finale | rose incomplete |
|---|---|---|---|---|---|---|---|---|---|
| P0 | 3438.3 +/- 7.9 | 5079.3 +/- 20.8 | 23.9 +/- 4.1 | 0.0 +/- 0.0 | 179.9 +/- 7.9 | 15.9 +/- 0.3 | 1.0 +/- 0.0 | 1.0 +/- 0.0 | 0 |
| P1 | 3435.6 +/- 6.5 | 5063.5 +/- 16.4 | 46.4 +/- 5.5 | 0.0 +/- 0.0 | 172.4 +/- 5.1 | 13.4 +/- 0.3 | 1.0 +/- 0.0 | 1.0 +/- 0.0 | 0 |
| P2 | 3444.4 +/- 6.4 | 5083.4 +/- 14.7 | 27.9 +/- 4.2 | 0.0 +/- 0.0 | 179.1 +/- 4.7 | 13.8 +/- 0.3 | 1.0 +/- 0.0 | 1.0 +/- 0.0 | 0 |
| P3 | 3436.2 +/- 6.9 | 5075.4 +/- 16.6 | 19.4 +/- 3.9 | 0.0 +/- 0.0 | 178.6 +/- 4.6 | 13.2 +/- 0.3 | 1.0 +/- 0.0 | 1.0 +/- 0.0 | 0 |
| P4 | 3427.3 +/- 7.0 | 5055.6 +/- 16.3 | 37.8 +/- 6.3 | 0.0 +/- 0.0 | 168.6 +/- 6.4 | 14.8 +/- 0.3 | 1.0 +/- 0.0 | 1.0 +/- 0.0 | 0 |

## Differenze appaiate contro P0 (stesso seme)

| politica | d objective | 2xSE | d residuo | d spesa top3 | d target persi | verdetto |
|---|---|---|---|---|---|---|
| P1 | -2.7 +/- 10.8 | 21.6 | +22.4 +/- 5.7 | -7.5 +/- 7.1 | -2.5 +/- 0.4 | non distinguibile |
| P2 | +6.1 +/- 8.3 | 16.6 | +3.9 +/- 5.7 | -0.8 +/- 9.3 | -2.1 +/- 0.4 | non distinguibile |
| P3 | -2.2 +/- 10.2 | 20.5 | -4.6 +/- 6.0 | -1.3 +/- 9.3 | -2.8 +/- 0.4 | non distinguibile |
| P4 | -11.1 +/- 9.8 | 19.5 | +13.9 +/- 7.2 | -11.3 +/- 9.5 | -1.1 +/- 0.3 | non distinguibile |

Criterio (fissato prima di guardare i numeri): una politica e' migliore di P0 solo se la media delle differenze appaiate di objective supera 2 volte il suo errore standard, con residuo medio non superiore a quello di P0 di oltre 10 crediti e zero rose incomplete. Altrimenti 'non distinguibile' (media dentro +/- 2 SE) o 'peggiore' (media sotto -2 SE).

### Verdetto

**Nessuna delle politiche in prova supera P0 secondo il criterio.** Le differenze di objective stanno tutte dentro +/- 2 errori standard, e nemmeno il segno e' concorde. Non e' un pareggio dimostrato: e' un confronto che questo banco non riesce a decidere, con la differenza vera - se esiste - piu' piccola dell'incertezza residua.

## P0: si realizza il rischio di strapagare le stelle?

heat finale medio P0: 0.997 +/- 0.002

| seme | 1o acquisto | prezzo | q50 | mercato | 2o | prezzo | 3o | prezzo |
|---|---|---|---|---|---|---|---|---|
| 0 | Dimarco | 86 | 66 | 63 | Zaccagni | 53 | De Ketelaere | 46 |
| 1 | Dimarco | 62 | 66 | 63 | Rabiot | 60 | Zaccagni | 50 |
| 2 | Malen | 110 | 138 | 163 | Zaccagni | 44 | Da Cunha | 42 |
| 3 | De Bruyne | 66 | 39 | 47 | Ramos G. | 42 | Kolo Muani | 41 |
| 4 | Da Cunha | 53 | 35 | 35 | Zaccagni | 49 | Vlasic | 37 |
| 5 | Zaccagni | 49 | 35 | 36 | Da Cunha | 43 | Frattesi | 35 |
| 6 | Ramos G. | 96 | 106 | 118 | Da Cunha | 46 | Wesley | 44 |
| 7 | Ramos G. | 85 | 106 | 118 | Da Cunha | 43 | Zaccagni | 43 |
| 8 | Malen | 184 | 138 | 163 | Thuram | 58 | Zaccagni | 50 |
| 9 | Ramos G. | 117 | 106 | 118 | De Bruyne | 59 | Zaccagni | 50 |
| 10 | Ramos G. | 67 | 106 | 118 | Da Cunha | 55 | Kean | 52 |
| 11 | Malen | 193 | 138 | 163 | Ramos G. | 52 | Zaccagni | 49 |
| 12 | Zaccagni | 45 | 35 | 36 | Simeone | 44 | Da Cunha | 42 |
| 13 | Da Cunha | 53 | 35 | 35 | Barella | 52 | Kean | 50 |
| 14 | Malen | 183 | 138 | 163 | Da Cunha | 42 | Vlasic | 38 |
| 15 | Thuram | 63 | 113 | 89 | De Ketelaere | 51 | Zaccagni | 44 |
| 16 | De Bruyne | 58 | 39 | 47 | Vlasic | 42 | Frattesi | 32 |
| 17 | Malen | 165 | 138 | 163 | De Bruyne | 49 | Kean | 42 |
| 18 | Zaccagni | 52 | 35 | 36 | Vlasic | 40 | Da Cunha | 37 |
| 19 | Kolo Muani | 52 | 104 | 80 | Wesley | 44 | Vlasic | 41 |
| 20 | De Bruyne | 57 | 39 | 47 | Zaccagni | 48 | Kean | 42 |
| 21 | De Bruyne | 56 | 39 | 47 | Da Cunha | 52 | Kolo Muani | 50 |
| 22 | De Bruyne | 62 | 39 | 47 | Ramos G. | 62 | Zaccagni | 41 |
| 23 | De Bruyne | 60 | 39 | 47 | Kolo Muani | 55 | Da Cunha | 40 |
| 24 | Wesley | 45 | 35 | 36 | Da Cunha | 43 | Zaccagni | 43 |
| 25 | De Bruyne | 61 | 39 | 47 | Zaccagni | 43 | Kean | 39 |
| 26 | Ramos G. | 71 | 106 | 118 | De Bruyne | 48 | Zaccagni | 47 |
| 27 | Dimarco | 85 | 66 | 63 | Kolo Muani | 55 | Da Cunha | 50 |
| 28 | Ramos G. | 88 | 106 | 118 | De Bruyne | 61 | Zaccagni | 44 |
| 29 | Malen | 169 | 138 | 163 | Da Cunha | 44 | Zaccagni | 43 |
| 30 | Malen | 142 | 138 | 163 | Kolo Muani | 58 | Da Cunha | 51 |
| 31 | Hojlund | 78 | 125 | 105 | Zaccagni | 47 | Da Cunha | 47 |
| 32 | De Bruyne | 51 | 39 | 47 | Laurientè | 41 | Vlasic | 35 |
| 33 | Kolo Muani | 56 | 104 | 80 | Zaccagni | 52 | Barella | 49 |
| 34 | Malen | 99 | 138 | 163 | Zaccagni | 43 | Da Cunha | 39 |
| 35 | Malen | 141 | 138 | 163 | Frattesi | 37 | Laurientè | 34 |

| politica | prezzo pagato / mercato sui 3 acquisti piu' cari (mediana) |
|---|---|
| P0 | 1.19 |
| P1 | 1.26 |
| P2 | 1.24 |
| P3 | 1.26 |
| P4 | 1.22 |

## Primario a 12 semi, poi estensione a 36

Il banco dichiarato prima di guardare i numeri era di 12 semi (0..11). Il suo esito e' salvato in `sim_mercato_risultati_12semi.json` / `.md`: tutte e quattro le varianti sopra P0 di segno positivo, nessuna oltre 2 errori standard, quindi quattro "non distinguibile". Vista la spesa di calcolo (7 minuti per 60 aste) il banco e' stato **esteso a 36 semi (0..35), criterio invariato**, per avere la potenza di separare un effetto dell'ordine dell'1%. L'estensione e' stata decisa dopo aver visto un risultato inconcludente: e' un test sequenziale, e un test sequenziale gonfia un po' il rischio di falso positivo. Va letto per quello che e': una misura piu' precisa dello stesso confronto, non una conferma indipendente.

| politica | d objective a 12 semi | 2xSE | esito a 12 semi |
|---|---|---|---|
| P1 | +34.8 +/- 20.7 | 41.5 | sotto soglia |
| P2 | +27.4 +/- 18.4 | 36.8 | sotto soglia |
| P3 | +22.1 +/- 19.9 | 39.9 | sotto soglia |
| P4 | +21.8 +/- 16.0 | 32.0 | sotto soglia |

## Che fine fa l'ipotesi di partenza

L'ipotesi era: se il tavolo paga i prezzi di mercato, il heat globale sale a circa 1.21 e gonfia anche i tetti sulle stelle. **Il banco non lo vede**: con un tavolo che paga il mercato per costruzione, il heat finale di P0 resta 0.997. La ragione e' aritmetica: in una lega da 10 squadre e 500 crediti il tavolo puo' spendere in tutto 5000 crediti, e la somma dei q50 dei ~250 giocatori che vengono davvero venduti e' dello stesso ordine. Il rapporto prezzi/q50 puo' cambiare forma (fascia bassa strapagata, stelle pagate meno di q50) senza spostare quasi nulla del suo totale, che e' quello che il heat misura. Il sottoprezzo della fascia bassa e' reale, ma **non passa dal heat**: se va corretto, va corretto nei prezzi del piano, non nel moltiplicatore globale.

L'unica differenza che il banco separa davvero dal rumore non e' l'objective: sono i **target del piano persi**. Tutte e quattro le varianti ne perdono meno di P0, di uno-tre target, con errori standard di 0.3-0.4: un piano costruito ai prezzi di mercato regge l'urto del tavolo invece di essere rifatto da capo a ogni martelletto. Ma la rosa che ne esce non vale di piu': objective, somma dei value e spesa sui 3 acquisti piu' cari restano dentro il rumore. E due varianti lasciano piu' crediti non spesi a fine asta (P1 e P4): pagare il mercato nel piano rende il MILP piu' prudente, e i crediti che restano in tasca sono valore buttato. Un piano che si conferma non e' un piano migliore: e' solo un piano piu' stabile.

La posizione fra le 10 squadre non discrimina nulla: in tutte le aste del banco la nostra rosa e' prima per objective, con qualunque politica. Contro questi avversari il margine e' cosi' largo che la metrica e' satura; serve solo a dire che nessuna variante ci fa perdere il primo posto.

## Limiti del banco

- Avversari sintetici: i bot di mercato pagano per costruzione i prezzi di riferimento; un tavolo reale ha correlazioni, bluff e tempi che qui mancano.
- I prezzi di mercato sono medie aggregate di aste reali: non hanno la variabilita' per lega ne' l'aggiornamento dell'ultimo minuto (infortuni).
- 36 semi: differenze di objective sotto ~1% della media restano sotto la soglia di rilevabilita'.
- L'objective finale usa i value/value_up del NOSTRO pack anche per le altre 9 squadre: e' un metro comune, non una previsione della classifica reale.
- L'appaiamento fissa il seme (seating, rumore avversari), ma cambiando i nostri rilanci cambia anche chi vince i lotti successivi: le differenze restano rumorose per costruzione.
- _replan e' una copia fedele del sorgente con un solo punto di variazione (i prezzi del piano): se bot_b.py cambia, la copia va riallineata. Il controllo P0copy verifica che la copia riproduca P0 seme per seme.
- I bot di mercato rilanciano sempre di +1 e non fanno mai salti: le aste salgono a gradini, e un bot con un tetto alto vince spesso per un solo credito in piu'. Un tavolo vero salta, e i tetti si pagano piu' spesso per intero.
- La posizione fra le 10 squadre e' satura (sempre prima): non serve a ordinare le politiche, solo a escludere disastri.
- L'estensione da 12 a 36 semi e' stata decisa dopo aver visto il primario inconcludente: test sequenziale, quindi il rischio di falso positivo e' un po' piu' alto di quello nominale del criterio.

## Ripetere

```
cd "C:\Users\Administrator\AppData\Local\Temp\claude\E--claudecode-pesante\5ff20539-b495-4ac4-bed4-79eabbf8a8b7\scratchpad\w2"
python sim_mercato.py --smoke --tl 5          # una asta P0, misura i tempi
python sim_mercato.py --fedelta --tl 5        # P0 vs P0copy: la copia di _replan e' fedele
python sim_mercato.py --semi 12 --procs 4 --tl 5   # banco primario
python sim_mercato.py --semi 36 --procs 4 --tl 5   # banco esteso
python sim_mercato.py --report                # rigenera solo il .md dal .json
```

Il banco legge SOLO le copie locali `pack.pkl` e `elig.json` in questa cartella: la catena di rigenerazione del pack che gira in parallelo non puo' cambiargli i dati sotto i piedi a meta' corsa.
